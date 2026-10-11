from django.test import TestCase

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from config.testkit import (
    client_for, fund_ewallet, fund_wallet, make_candy, make_cashier, make_customer, make_gcash,
    make_load, make_marlboro, make_owner, open_shift,
)
from inventory.models import Product, ProductUnit
from sales.models import Sale
from wallets.models import Wallet

URL = '/api/owner/dashboard/'

# Create your tests here.
class DashboardBase(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.cashier = make_cashier()
        self.shift = open_shift(self.cashier, '1000.00')
        self.api = client_for(self.cashier)
        self.owner_api = client_for(self.owner)
        self.marlboro, self.stick, self.pack = make_marlboro()     # cost P8 per stick
        self.candy, self.piece = make_candy()                      # P1 each, 3 for P2, cost P0.50

    def sell(self, unit, qty, cash='500'):
        response = self.api.post('/api/sales/', {
            'items': [{'product_unit': unit.id, 'quantity': qty}], 'cash_received': cash}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def utang_sale(self, customer, qty='7'):
        response = self.api.post('/api/sales/', {
            'items': [{'product_unit': self.piece.id, 'quantity': qty}],
            'payment_type': 'utang', 'customer': customer.id}, format='json')
        self.assertEqual(response.status_code, 201, response.data)

    def get(self):
        response = self.owner_api.get(URL)
        self.assertEqual(response.status_code, 200)
        return response.data


class TodayTests(DashboardBase):
    def test_todays_numbers_add_up(self):
        self.sell(self.piece, '7')                       # P5.00, cost 3.50, profit 1.50
        self.sell(self.pack, '1')                        # P190.00, cost 160.00, profit 30.00
        _, load = make_load()                            # P52 sale, P50 sent, 4% rebate = P2
        fund_wallet(self.owner, '1000')
        self.api.post('/api/load/send/', {'product': load.id, 'mobile_no': '09171234567',
                                          'reference_no': 'REF00001'}, format='json')
        make_gcash()
        fund_ewallet(self.owner, '2000')
        self.api.post('/api/ewallet/cash-in/', {'amount': 500, 'mobile_no': '09171234567',
                                                'reference_no': 'GC00000001'}, format='json')
        today = self.get()['today']
        self.assertEqual((today['sales_count'], today['sales_total']), (2, '195.00'))
        self.assertEqual(today['goods_profit'], '31.50')
        self.assertEqual((today['load_sales'], today['load_profit']), ('52.00', '4.00'))
        self.assertEqual((today['ewallet_count'], today['ewallet_fees']), (1, '10.00'))
        self.assertEqual(today['profit'], '45.50')       # 31.50 + 4.00 + 10.00

    def test_voided_failed_and_reversed_records_do_not_count(self):
        self.sell(self.piece, '7')
        Sale.objects.update(status='voided')
        _, load = make_load()
        fund_wallet(self.owner, '1000')
        sent = self.api.post('/api/load/send/', {'product': load.id, 'mobile_no': '09171234567',
                                                 'reference_no': 'REF00001'}, format='json')
        self.api.post(f"/api/load/{sent.data['load_id']}/fail/", {'note': 'Provider error'}, format='json')
        make_gcash()
        fund_ewallet(self.owner, '2000')
        tx = self.api.post('/api/ewallet/cash-in/', {'amount': 500, 'mobile_no': '09171234567',
                                                     'reference_no': 'GC00000001'}, format='json')
        self.owner_api.post(f"/api/owner/ewallet/{tx.data['tx_id']}/reverse/", {'note': 'Cancelled'}, format='json')
        today = self.get()['today']
        self.assertEqual((today['sales_count'], today['sales_total'], today['profit']), (0, '0.00', '0.00'))
        self.assertEqual((today['load_sales'], today['ewallet_fees']), ('0.00', '0.00'))

    def test_other_days_do_not_count(self):
        self.sell(self.piece, '7')
        Sale.objects.update(timestamp=timezone.now() - timedelta(days=2))
        today = self.get()['today']
        self.assertEqual((today['sales_total'], today['goods_profit']), ('0.00', '0.00'))

    def test_a_price_change_does_not_rewrite_todays_profit(self):
        self.sell(self.pack, '1')
        self.owner_api.patch(f'/api/units/{self.pack.id}/', {'selling_price': '300.00'}, format='json')
        self.owner_api.post('/api/restocks/', {
            'product': self.marlboro.id, 'product_unit': self.pack.id,
            'quantity': '10', 'unit_cost': '220'}, format='json')           # the cost changes too
        self.assertEqual(self.get()['today']['goods_profit'], '30.00')

    def test_utang_counts_as_a_sale_and_the_write_off_is_a_separate_line(self):
        nena = make_customer()
        self.utang_sale(nena)     
        data = self.get()
        self.assertEqual((data['today']['sales_total'], data['today']['utang_sales_total']), ('5.00', '5.00'))
        self.assertEqual(data['today']['goods_profit'], '1.50')
        self.owner_api.post(f'/api/owner/customers/{nena.id}/write-off/',
                            {'amount': '2', 'reason': 'Moved away'}, format='json')
        today = self.get()['today']
        self.assertEqual((today['writeoffs'], today['profit']), ('2.00', '1.50'))   # not subtracted

    def test_best_sellers_are_ranked_by_amount(self):
        self.sell(self.piece, '7')                       # candy: P5
        self.sell(self.pack, '1')                        # marlboro: P190
        self.sell(self.stick, '2')                       # marlboro: P20
        best = self.get()['best_sellers']
        self.assertEqual([b['product'] for b in best], ['Marlboro Red', 'Candy Test'])
        self.assertEqual((best[0]['amount'], best[0]['quantity'], best[0]['unit']), ('210.00', '22', 'stick'))
        self.assertEqual((best[1]['amount'], best[1]['quantity']), ('5.00', '7'))

#     def test_an_empty_store(self):
#         Shift.objects.all().delete if False else None    
#         data = DashboardEmpty.fetch()
#         self.assertEqual(data['today']['profit'], '0.00')


# class DashboardEmpty:
#     @staticmethod
#     def fetch():
#         owner = make_owner('boss2')
#         return client_for(owner).get(URL).data

class EmptyStoreTests(TestCase):
    def test_an_empty_store(self):
        data = client_for(make_owner()).get(URL).data
        self.assertEqual((data['today']['sales_count'], data['today']['profit']), (0, '0.00'))
        self.assertEqual((data['open_shift'], data['last_shift'], data['wallets'], data['best_sellers']),
                         (None, None, [], []))
        self.assertEqual((data['low_stock']['count'], data['utang']['total_unpaid']), (0, '0.00'))

class ShiftCardTests(DashboardBase):
    def test_the_open_shift(self):
        card = self.get()['open_shift']
        self.assertEqual((card['cashier'], card['opening_cash']), ('cash', '1000.00'))
        self.assertIsNone(self.get()['last_shift'])

    def test_the_last_shift_and_its_variance(self):
        self.api.post('/api/shifts/end/', {'counted_cash': '990'}, format='json')    # expected 1000
        data = self.get()
        self.assertIsNone(data['open_shift'])
        last = data['last_shift']
        self.assertEqual((last['cashier'], last['variance'], last['closed_on_behalf']), ('cash', '-10.00', False))

    def test_closed_on_behalf_is_flagged(self):
        self.owner_api.post(f'/api/shifts/{self.shift.id}/close/',
                            {'counted_cash': '1000', 'reason': 'Went home sick'}, format='json')
        self.assertTrue(self.get()['last_shift']['closed_on_behalf'])

    def test_wallet_differences_are_counted_on_the_last_shift(self):
        fund_wallet(self.owner, '1000')
        self.api.post('/api/shifts/end/', {'counted_cash': '1000'}, format='json')
        wallet = Wallet.objects.get(type='load')
        balances = {str(wallet.id): '900'}                                          
        self.api.post('/api/shifts/start/', {'opening_cash': '1000', 'wallet_balances': balances}, format='json')
        self.api.post('/api/shifts/end/', {'counted_cash': '1000', 'wallet_balances': balances}, format='json')
        self.assertEqual(self.get()['last_shift']['wallet_flags'], 1)


class LowStockTests(DashboardBase):
    def product(self, name, stock, level, units=True, active=True):
        p = Product.objects.create(name=name, base_unit='pack', stock_qty=Decimal(stock),
                                   low_stock_level=Decimal(level), is_active=active)
        if units:
            ProductUnit.objects.create(product=p, unit_name='pack', pieces_per_unit=Decimal('1'),
                                       selling_price=Decimal('10'))
        return p

    def test_only_sellable_active_items_at_or_below_their_level(self):
        self.product('Chips', '3', '10')
        self.product('Soap', '0', '5')
        self.product('Plenty', '50', '10')                        # fine
        self.product('No unit', '0', '5', units=False)            # cannot be sold
        self.product('Retired', '0', '5', active=False)           # inactive
        low = self.get()['low_stock']
        self.assertEqual(low['count'], 2)
        self.assertEqual([(i['name'], i['status']) for i in low['items']], [('Soap', 'out'), ('Chips', 'low')])

    def test_items_needing_a_recount(self):
        Product.objects.filter(pk=self.candy.pk).update(needs_recount=True)
        self.assertEqual(self.get()['low_stock']['recount_count'], 1)


class UtangAndWalletTests(DashboardBase):
    def test_unpaid_and_overdue_utang(self):
        nena = make_customer()
        self.utang_sale(nena)
        utang = self.get()['utang']
        self.assertEqual((utang['total_unpaid'], utang['owing_count'], utang['overdue_count']), ('5.00', 1, 0))
        Sale.objects.filter(payment_type='utang').update(timestamp=timezone.now() - timedelta(days=40))
        utang = self.get()['utang']
        self.assertEqual((utang['overdue_count'], utang['overdue_days']), (1, 30))

    def test_wallet_balances_and_the_low_flag(self):
        fund_wallet(self.owner, '100')                           
        make_gcash()
        fund_ewallet(self.owner, '2000')
        wallets = {w['provider']: w for w in self.get()['wallets']}
        self.assertEqual((wallets['Load wallet']['balance'], wallets['Load wallet']['is_low']), ('100.00', True))
        self.assertEqual((wallets['GCash']['balance'], wallets['GCash']['is_low']), ('2000.00', False))


class DashboardSecurityTests(DashboardBase):
    def test_only_the_owner_can_see_it(self):
        self.assertEqual(self.api.get(URL).status_code, 403)
        self.assertEqual(client_for().get(URL).status_code, 401)

    def test_money_is_text_never_a_float(self):
        self.sell(self.piece, '7')
        today = self.get()['today']
        for key in ('sales_total', 'goods_profit', 'profit', 'load_sales', 'ewallet_fees', 'writeoffs'):
            self.assertIsInstance(today[key], str)