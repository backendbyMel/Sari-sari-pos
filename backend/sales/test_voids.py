from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from config.testkit import (
    client_for, make_candy, make_cashier, make_customer, make_marlboro, make_owner, open_shift,
)
from inventory.models import Product, StockMovement
from sales.models import Sale, VoidRequest
from shifts.models import CashMovement, Shift
from shifts.reports import build_report_data


class VoidBase(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.cashier = make_cashier()
        self.shift = open_shift(self.cashier, '1000.00')
        self.api = client_for(self.cashier)
        self.owner_api = client_for(self.owner)
        self.marlboro, self.stick, self.pack = make_marlboro()      # 400 sticks
        self.candy, self.piece = make_candy()                       # 100 pieces, 7 = P5

    def sell(self, unit, qty, cash='500'):
        r = self.api.post('/api/sales/', {'items': [{'product_unit': unit.id, 'quantity': qty}],
                                          'cash_received': cash}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return r.data['receipt']['receipt_no']

    def ask(self, no, reason='Customer returned it', api=None):
        return (api or self.api).post(f'/api/sales/{no}/void-request/', {'reason': reason}, format='json')

    def approve(self, vid, note='', api=None):
        return (api or self.owner_api).post(f'/api/voids/{vid}/approve/', {'note': note}, format='json')

    def reject(self, vid, note='Not allowed', api=None):
        return (api or self.owner_api).post(f'/api/voids/{vid}/reject/', {'note': note}, format='json')

    def end(self, counted):
        return self.api.post('/api/shifts/end/', {'counted_cash': counted}, format='json')

    def start(self, cash):
        return self.api.post('/api/shifts/start/', {'opening_cash': cash}, format='json')

    def run_check(self):
        out = StringIO()
        call_command('check_integrity', stdout=out)
        return out.getvalue()

    def stock(self, product):
        product.refresh_from_db()
        return product.stock_qty


class RequestTests(VoidBase):
    def test_a_request_changes_nothing_until_the_owner_decides(self):
        no = self.sell(self.pack, '1')
        r = self.ask(no)
        self.assertEqual(r.status_code, 201)
        self.assertEqual((r.data['status'], r.data['receipt_no'], r.data['total']), ('pending', no, '190.00'))
        self.assertEqual(Sale.objects.get().status, 'completed')
        self.assertEqual(self.stock(self.marlboro), Decimal('380'))
        self.assertEqual(VoidRequest.objects.get().requested_by, self.cashier)

    def test_bad_requests(self):
        no = self.sell(self.piece, '7', cash='10')
        for body in ({}, {'reason': ''}, {'reason': '   '}):
            self.assertEqual(self.api.post(f'/api/sales/{no}/void-request/', body, format='json').status_code, 400)
        self.assertEqual(self.ask('SR-999999').status_code, 404)
        self.assertEqual(self.ask(no).status_code, 201)
        self.assertEqual(self.ask(no).status_code, 400)                     # already waiting
        self.assertEqual(VoidRequest.objects.count(), 1)

    def test_load_and_payment_receipts_are_not_sales(self):
        nena = make_customer()
        self.api.post('/api/sales/', {'items': [{'product_unit': self.piece.id, 'quantity': '7'}],
                                      'payment_type': 'utang', 'customer': nena.id}, format='json')
        pay = self.api.post('/api/utang/payments/', {'customer': nena.id, 'amount': '1'}, format='json')
        self.assertEqual(self.ask(pay.data['receipt']['receipt_no']).status_code, 404)

    def test_a_cashier_cannot_decide(self):
        vid = self.ask(self.sell(self.piece, '7', cash='10')).data['id']
        self.assertEqual(self.approve(vid, api=self.api).status_code, 403)
        self.assertEqual(self.reject(vid, api=self.api).status_code, 403)
        self.assertEqual(VoidRequest.objects.get().status, 'pending')

    def test_my_requests_show_only_my_own_and_only_safe_fields(self):
        vid = self.ask(self.sell(self.piece, '7', cash='10')).data['id']
        self.reject(vid, 'Not allowed')
        mine = self.api.get('/api/voids/mine/').data
        self.assertEqual(set(mine[0]), {'id', 'receipt_no', 'total', 'reason', 'status',
                                        'decision_note', 'requested_at', 'decided_at'})
        self.assertEqual((mine[0]['status'], mine[0]['decision_note']), ('rejected', 'Not allowed'))
        self.assertEqual(client_for(make_cashier('cash2')).get('/api/voids/mine/').data, [])


class ApproveTests(VoidBase):
    def test_a_cash_sale_in_the_open_shift(self):
        no = self.sell(self.pack, '1')
        vid = self.ask(no).data['id']
        r = self.approve(vid, 'OK')
        self.assertEqual(r.status_code, 200, r.data)
        sale = Sale.objects.get()
        self.assertEqual(sale.status, 'voided')
        self.assertIsNotNone(sale.voided_at)
        self.assertEqual(self.stock(self.marlboro), Decimal('400'))
        line = StockMovement.objects.get(type='void')
        self.assertEqual((line.quantity, line.balance_after, line.user, line.reason),
                         (Decimal('20'), Decimal('400'), self.owner, f'Void {no}'))
        self.assertEqual(CashMovement.objects.count(), 0)                    # nothing to refund separately
        void = VoidRequest.objects.get()
        self.assertEqual((void.status, void.decided_by, void.refund_amount, void.refund_shift),
                         ('approved', self.owner, Decimal('0'), None))
        self.assertEqual(self.api.get('/api/sales/recent/').data[0]['status'], 'voided')
        self.assertTrue(self.api.post(f'/api/receipts/{no}/reprint/').data['is_void'])
        closed = self.end('1000')                                           # the voided sale no longer counts
        self.assertEqual((Decimal(closed.data['shift']['expected_cash']), closed.data['sales_count']), (Decimal('1000'), 0))
        report = build_report_data(Shift.objects.get(), owner=False, report_no='X')
        self.assertEqual((report['voided_count'], report['void_rows'][0]['receipt_no']), (1, no))
        self.assertIn('OK', self.run_check())

    def test_a_sale_from_a_closed_shift_is_refunded_from_the_open_shift(self):
        no = self.sell(self.piece, '7', cash='10')                          # P5
        self.assertEqual(Decimal(self.end('1005').data['shift']['variance']), 0)
        shift1 = Shift.objects.get(pk=self.shift.pk)
        saved = shift1.expected_cash
        self.assertEqual(self.start('1005').status_code, 201)
        vid = self.ask(no).data['id']
        self.assertEqual(self.approve(vid).status_code, 200)
        shift2 = Shift.objects.get(status='open')
        move = CashMovement.objects.get()
        self.assertEqual((move.shift, move.type, move.amount, move.recorded_by),
                         (shift2, 'out', Decimal('5'), self.owner))
        self.assertIn(no, move.reason)
        void = VoidRequest.objects.get()
        self.assertEqual((void.refund_amount, void.refund_shift), (Decimal('5'), shift2))
        shift1.refresh_from_db()
        self.assertEqual(shift1.expected_cash, saved)                       # yesterday is untouched
        old = build_report_data(shift1, owner=False, report_no='X')
        self.assertEqual((old['sales_count'], old['sales_total'], old['voided_count']), (1, Decimal('5.00'), 0))
        self.assertIn('OK', self.run_check())
        closed = self.end('1000')                                           # 1005 - 5 refunded
        self.assertEqual(Decimal(closed.data['shift']['variance']), 0)
        new = build_report_data(Shift.objects.get(pk=shift2.pk), owner=False, report_no='Y')
        self.assertEqual((new['voided_count'], new['payouts_total']), (1, Decimal('5.00')))
        self.assertIn('OK', self.run_check())

    def test_a_cash_refund_needs_an_open_shift(self):
        no = self.sell(self.piece, '7', cash='10')
        self.end('1005')
        vid = self.ask(no).data['id']
        r = self.approve(vid)
        self.assertEqual(r.status_code, 400)
        self.assertIn('shift', r.data)
        self.assertEqual((VoidRequest.objects.get().status, Sale.objects.get().status), ('pending', 'completed'))
        self.assertEqual(self.stock(self.candy), Decimal('93'))
        self.start('1005')
        self.assertEqual(self.approve(vid).status_code, 200)

    def test_a_utang_sale_lowers_the_balance_and_needs_no_shift(self):
        nena = make_customer()
        self.api.post('/api/sales/', {'items': [{'product_unit': self.piece.id, 'quantity': '7'}],
                                      'payment_type': 'utang', 'customer': nena.id}, format='json')
        self.end('1000')
        vid = self.ask('SR-000001').data['id']
        self.assertEqual(self.approve(vid).status_code, 200)
        nena.refresh_from_db()
        self.assertEqual(nena.balance, 0)
        self.assertEqual(self.stock(self.candy), Decimal('100'))
        self.assertEqual((CashMovement.objects.count(), VoidRequest.objects.get().refund_amount), (0, Decimal('0')))
        self.assertIn('OK', self.run_check())

    def test_a_utang_void_is_refused_when_the_customer_already_paid_too_much(self):
        nena = make_customer()
        self.api.post('/api/sales/', {'items': [{'product_unit': self.piece.id, 'quantity': '7'}],
                                      'payment_type': 'utang', 'customer': nena.id}, format='json')
        self.api.post('/api/utang/payments/', {'customer': nena.id, 'amount': '2'}, format='json')   # owes 3
        vid = self.ask('SR-000001').data['id']
        r = self.approve(vid)
        self.assertEqual(r.status_code, 400)
        self.assertIn('void', r.data)
        nena.refresh_from_db()
        self.assertEqual((nena.balance, Sale.objects.get(receipt_no='SR-000001').status), (Decimal('3'), 'completed'))

    def test_a_sale_with_several_lines_of_one_product(self):
        r = self.api.post('/api/sales/', {'items': [{'product_unit': self.pack.id, 'quantity': '1'},
                                                    {'product_unit': self.stick.id, 'quantity': '3'}],
                                          'cash_received': '500'}, format='json')
        self.assertEqual(self.stock(self.marlboro), Decimal('377'))
        vid = self.ask(r.data['receipt']['receipt_no']).data['id']
        self.approve(vid)
        self.assertEqual(self.stock(self.marlboro), Decimal('400'))
        self.assertEqual(StockMovement.objects.filter(type='void').count(), 2)
        self.assertIn('OK', self.run_check())

    def test_deciding_twice_and_voiding_twice_are_refused(self):
        no = self.sell(self.piece, '7', cash='10')
        vid = self.ask(no).data['id']
        self.assertEqual(self.approve(vid).status_code, 200)
        self.assertEqual(self.approve(vid).status_code, 400)
        self.assertEqual(self.reject(vid).status_code, 400)
        self.assertEqual(self.ask(no).status_code, 400)
        self.assertEqual(self.stock(self.candy), Decimal('100'))            # restored once
        self.assertEqual(self.approve(999999).status_code, 404)

    def test_voided_sales_leave_the_dashboard_and_reports(self):
        no = self.sell(self.piece, '7', cash='10')
        self.approve(self.ask(no).data['id'])
        dash = self.owner_api.get('/api/owner/dashboard/').data
        self.assertEqual((dash['today']['sales_total'], dash['voids']['pending_count']), ('0.00', 0))
        self.assertEqual(dash['voids']['recent'][0]['receipt_no'], no)
        self.assertEqual(self.owner_api.get('/api/owner/reports/sales/').data['rows'], [])


class RejectAndListTests(VoidBase):
    def test_reject_keeps_the_sale_and_allows_a_new_request(self):
        no = self.sell(self.piece, '7', cash='10')
        vid = self.ask(no).data['id']
        for note in ('', '   '):
            self.assertEqual(self.reject(vid, note).status_code, 400)
        self.assertEqual(self.reject(vid, 'Customer kept it').status_code, 200)
        void = VoidRequest.objects.get()
        self.assertEqual((void.status, void.decided_by), ('rejected', self.owner))
        self.assertEqual((Sale.objects.get().status, self.stock(self.candy)), ('completed', Decimal('93')))
        self.assertEqual(self.ask(no).status_code, 201)

    def test_the_owner_list_and_its_filter(self):
        a = self.ask(self.sell(self.piece, '7', cash='10')).data['id']
        self.ask(self.sell(self.piece, '7', cash='10'))
        self.approve(a)
        data = self.owner_api.get('/api/voids/').data
        self.assertEqual((data['pending_count'], len(data['requests'])), (1, 1))
        self.assertEqual(len(self.owner_api.get('/api/voids/?status=all').data['requests']), 2)
        row = self.owner_api.get('/api/voids/?status=approved').data['requests'][0]
        self.assertEqual((row['status'], row['decided_by'], row['sold_by'], row['requested_by']), ('approved', 'boss', 'cash', 'cash'))
        self.assertEqual(self.owner_api.get('/api/voids/?status=bad').status_code, 400)
        self.assertEqual(self.api.get('/api/voids/').status_code, 403)

    def test_decided_requests_are_final(self):
        vid = self.ask(self.sell(self.piece, '7', cash='10')).data['id']
        self.approve(vid)
        void = VoidRequest.objects.get(pk=vid)
        void.reason = 'changed'
        with self.assertRaises(PermissionError):
            void.save()
        with self.assertRaises(PermissionError):
            void.delete()


class IntegrityTests(VoidBase):
    def test_tampering_with_a_voided_sale_is_caught(self):
        from django.core.management.base import CommandError
        no = self.sell(self.piece, '7', cash='10')
        self.approve(self.ask(no).data['id'])
        Product.objects.filter(pk=self.candy.pk).update(stock_qty=Decimal('50'))
        with self.assertRaises(CommandError):
            self.run_check()