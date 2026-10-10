from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from config.testkit import (
    client_for, fund_ewallet, fund_wallet, make_candy, make_cashier, make_customer,
    make_gcash, make_load, make_owner,
)
from sales.models import Receipt
from shifts.models import Shift
from shifts.reports import build_report_data
from wallets.models import Wallet


class Phase3DayTests(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.ana, self.ben = make_cashier('ana'), make_cashier('ben')
        self.owner_api, self.ana_api, self.ben_api = client_for(self.owner), client_for(self.ana), client_for(self.ben)
        self.candy, self.piece = make_candy()                 # P1 each, 3 for P2
        _, self.load_product = make_load()                    # Smart, Load 50: sells P52, rebate 4%
        make_gcash()                                          # fees: P1-500 = P10, P501-1000 = P20
        fund_wallet(self.owner, '1000')
        fund_ewallet(self.owner, '2000')
        self.nena = make_customer()
        self.load_wallet = Wallet.objects.get(type='load')
        self.gcash = Wallet.objects.get(type='ewallet')
        self.n = 0

    def ref(self):
        self.n += 1
        return f'REF{self.n:07d}'

    def balances(self, load, gcash):
        return {str(self.load_wallet.id): load, str(self.gcash.id): gcash}

    def start(self, api, cash, load, gcash):
        return api.post('/api/shifts/start/', {
            'opening_cash': cash, 'wallet_balances': self.balances(load, gcash)}, format='json')

    def sell(self, api, qty, cash):
        return api.post('/api/sales/', {
            'items': [{'product_unit': self.piece.id, 'quantity': qty}], 'cash_received': cash}, format='json')

    def sell_on_utang(self, api, qty):
        return api.post('/api/sales/', {
            'items': [{'product_unit': self.piece.id, 'quantity': qty}],
            'payment_type': 'utang', 'customer': self.nena.id}, format='json')

    def send_load(self, api):
        return api.post('/api/load/send/', {
            'product': self.load_product.id, 'mobile_no': '0917 123 4567', 'reference_no': self.ref()}, format='json')

    def gcash_tx(self, api, kind, amount):
        return api.post(f'/api/ewallet/{kind}/', {
            'amount': amount, 'mobile_no': '0917 123 4567', 'reference_no': self.ref()}, format='json')

    def report_status(self, api, shift_id, copy='cashier'):
        response = api.get(f'/api/shifts/{shift_id}/report/?copy={copy}')
        if getattr(response, 'streaming', False):
            b''.join(response.streaming_content)
        return response.status_code

    def run_check(self):
        out = StringIO()
        call_command('check_integrity', stdout=out)
        return out.getvalue()

    def test_a_whole_store_day_reconciles(self):
        # ===== Ana's shift =====
        started = self.start(self.ana_api, '1000', '1000', '2000')
        self.assertEqual(started.status_code, 201)
        self.assertEqual(self.start(self.ben_api, '1000', '1000', '2000').status_code, 400)   # one shift at a time

        self.assertEqual(self.sell(self.ana_api, '7', '10').status_code, 201)       # P5 cash, SR-000001
        self.assertEqual(self.sell_on_utang(self.ana_api, '7').status_code, 201)    # P5 utang, SR-000002
        pay = self.ana_api.post('/api/utang/payments/', {'customer': self.nena.id, 'amount': '2'}, format='json')
        self.assertEqual(pay.status_code, 201)                                    

        self.assertEqual(self.send_load(self.ana_api).status_code, 201)          
        second = self.send_load(self.ana_api)                                   
        self.assertEqual(second.status_code, 201)
        failed = self.ana_api.post(f"/api/load/{second.data['load_id']}/fail/", {'note': 'Provider error'}, format='json')
        self.assertEqual(failed.status_code, 200)                               

        self.assertEqual(self.gcash_tx(self.ana_api, 'cash-in', 500).status_code, 201)    
        self.assertEqual(self.gcash_tx(self.ana_api, 'cash-out', 200).status_code, 201)   
        self.assertEqual(self.ana_api.post('/api/shifts/payouts/', {
            'amount': '50', 'reason': 'Bought ice'}, format='json').status_code, 201)

        self.assertEqual(Wallet.objects.get(type='load').balance, Decimal('950'))     # 1000 - 50
        self.assertEqual(Wallet.objects.get(type='ewallet').balance, Decimal('1700'))  # 2000 - 500 + 200

        closed = self.ana_api.post('/api/shifts/end/', {
            'counted_cash': '1329', 'wallet_balances': self.balances('950', '1700')}, format='json')
        self.assertEqual(closed.status_code, 200)
        shift = closed.data['shift']
        self.assertEqual((Decimal(shift['expected_cash']), Decimal(shift['variance'])), (Decimal('1329'), 0))
        self.assertEqual((closed.data['load_sales'], closed.data['load_count'], closed.data['load_failed_count']),
                         ('52.00', 1, 1))
        self.assertEqual((closed.data['utang_given'], closed.data['utang_collected']), ('5.00', '2.00'))
        self.assertEqual((closed.data['ewallet_in'], closed.data['ewallet_out']), ('510.00', '190.00'))
        for row in closed.data['wallet_checks']:
            self.assertEqual(Decimal(row['gap']), 0)
        self.assertIsNotNone(closed.data['report'])

        self.nena.refresh_from_db()
        self.assertEqual(self.nena.balance, Decimal('3'))                        
        self.candy.refresh_from_db()
        self.assertEqual(self.candy.stock_qty, Decimal('86'))                      
        self.assertEqual(Receipt.objects.count(), 7)                               

        ben = self.start(self.ben_api, '1329', '900', '1700')                         # the system expected 950
        self.assertEqual(ben.status_code, 201)
        self.assertNotIn('difference', ben.content.decode().lower())                  # Ben sees no comparison
        ben_shift = Shift.objects.get(cashier=self.ben)

        owner_close = self.owner_api.post(f'/api/shifts/{ben_shift.id}/close/', {
            'counted_cash': '1329', 'reason': 'Ben went home sick',
            'wallet_balances': self.balances('900', '1700')}, format='json')
        self.assertEqual(owner_close.status_code, 200)
        self.assertTrue(owner_close.data['shift']['closed_on_behalf'])

        
        rows = {r['id']: r for r in self.owner_api.get('/api/shifts/').data}
        ana_id = Shift.objects.get(cashier=self.ana).id
        self.assertEqual(Decimal(rows[ben_shift.id]['opening_difference']), 0)        
        load_check = {w['wallet']: w for w in rows[ben_shift.id]['wallet_checks']}['Load wallet']
        self.assertEqual(Decimal(load_check['start_gap']), Decimal('-50'))
        flagged = [r['id'] for r in self.owner_api.get('/api/shifts/?variance=1').data]
        self.assertEqual(flagged, [ben_shift.id])                                    

        self.assertEqual(self.report_status(self.ana_api, ana_id), 200)
        self.assertEqual(self.report_status(self.ana_api, ana_id, 'owner'), 403)
        self.assertEqual(self.report_status(self.ben_api, ana_id), 404)
        self.assertEqual(self.report_status(self.ben_api, ben_shift.id), 200)
        self.assertEqual(self.report_status(self.owner_api, ana_id, 'owner'), 200)

        ana_shift = Shift.objects.get(pk=ana_id)
        cashier_copy = str(build_report_data(ana_shift, owner=False, report_no='X')).lower()
        for secret in ('rebate', 'profit', 'cost', 'margin', 'override', 'fee', 'start_gap'):
            self.assertNotIn(secret, cashier_copy)
        owner_copy = build_report_data(ana_shift, owner=True, report_no='X')
        self.assertEqual(owner_copy['load_profit'], Decimal('4'))                  
        self.assertEqual(owner_copy['fee_income'], Decimal('20'))                   
        self.assertEqual(owner_copy['total_profit'], Decimal('3.00'))              

        self.assertIn('OK', self.run_check())