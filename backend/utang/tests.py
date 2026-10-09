from django.test import TestCase
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError

from config.testkit import client_for, make_candy, make_cashier, make_customer, make_owner, open_shift
from core.services import set_credit_limit_mode, set_default_credit_limit
from sales.models import Receipt, Sale
from shifts.models import Shift, ShiftReport
from shifts.reports import build_report_data
from utang.models import Customer, UtangPayment

# Create your tests here.
class UtangBase(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.cashier = make_cashier()
        self.shift = open_shift(self.cashier, '1000.00')
        self.api = client_for(self.cashier)
        self.owner_api = client_for(self.owner)
        self.candy, self.piece = make_candy()     
        self.nena = make_customer()

    def charge(self, qty='7', confirm=None, api=None, **extra):
        body = {'items': [{'product_unit': self.piece.id, 'quantity': qty}],
                'payment_type': 'utang', 'customer': self.nena.id}
        if confirm is not None:
            body['confirm_over_limit'] = confirm
        body.update(extra)
        return (api or self.api).post('/api/sales/', body, format='json')

    def pay(self, amount, customer=None, api=None):
        return (api or self.api).post(
            '/api/utang/payments/', {'customer': customer or self.nena.id, 'amount': amount}, format='json')

    def balance(self):
        self.nena.refresh_from_db()
        return self.nena.balance


class UtangSaleTests(UtangBase):
    def test_a_utang_sale_raises_the_balance_and_moves_no_cash(self):
        response = self.charge('7')
        self.assertEqual(response.status_code, 201)
        receipt = response.data['receipt']
        self.assertEqual(Decimal(receipt['total']), Decimal('5'))
        self.assertEqual(receipt['customer'], {'name': 'Aling Nena'})
        self.assertEqual(Decimal(receipt['balance_after']), Decimal('5'))
        self.assertEqual(Decimal(receipt['cash_received']), 0)
        self.assertEqual(Decimal(receipt['change']), 0)
        self.assertEqual(self.balance(), Decimal('5'))
        sale = Sale.objects.get()
        self.assertEqual((sale.payment_type, sale.customer, sale.cashier, sale.shift),
                         ('utang', self.nena, self.cashier, self.shift))
        self.candy.refresh_from_db()
        self.assertEqual(self.candy.stock_qty, Decimal('93'))      

    def test_a_customer_is_required_and_must_exist(self):
        base = {'items': [{'product_unit': self.piece.id, 'quantity': '1'}], 'payment_type': 'utang'}
        for body in (base, {**base, 'customer': 999999}, {**base, 'customer': None}):
            with self.subTest(body=body):
                self.assertEqual(self.api.post('/api/sales/', body, format='json').status_code, 400)
        self.assertEqual(Sale.objects.count(), 0)

    def test_an_inactive_customer_cannot_take_utang(self):
        Customer.objects.filter(pk=self.nena.pk).update(is_active=False)
        self.assertEqual(self.charge().status_code, 400)
        self.assertEqual(Sale.objects.count(), 0)

    def test_utang_also_needs_an_open_shift(self):
        other = client_for(make_cashier('cash2'))
        self.assertEqual(self.charge(api=other).status_code, 400)
        self.assertEqual(self.balance(), 0)

    def test_over_the_limit_asks_for_confirmation_and_saves_nothing_meanwhile(self):
        Customer.objects.filter(pk=self.nena.pk).update(balance=Decimal('8'), credit_limit=Decimal('10'))
        first = self.charge('7')                                 
        self.assertEqual(first.status_code, 409)
        self.assertEqual(first.data['code'], 'over_limit')
        self.assertEqual(Decimal(first.data['balance']), Decimal('8'))
        self.assertEqual(Decimal(first.data['would_be']), Decimal('13'))
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(self.balance(), Decimal('8'))
        again = self.charge('7', confirm=True)
        self.assertEqual(again.status_code, 201)
        self.assertEqual(again.data['receipt']['receipt_no'], 'SR-000001')   # the refused try used no number
        self.assertEqual(self.balance(), Decimal('13'))

    def test_block_mode_refuses_even_when_confirmed(self):
        set_credit_limit_mode('block', None)
        Customer.objects.filter(pk=self.nena.pk).update(balance=Decimal('8'), credit_limit=Decimal('10'))
        for confirm in (None, True):
            with self.subTest(confirm=confirm):
                response = self.charge('7', confirm=confirm)
                self.assertEqual(response.status_code, 400)
                self.assertIn('customer', response.data)
        self.assertEqual(self.balance(), Decimal('8'))

    def test_exactly_at_the_limit_is_allowed(self):
        Customer.objects.filter(pk=self.nena.pk).update(balance=Decimal('5'), credit_limit=Decimal('10'))
        self.assertEqual(self.charge('7').status_code, 201)       

    def test_the_store_default_applies_when_the_customer_has_no_limit(self):
        set_default_credit_limit(Decimal('4'), None)
        self.assertEqual(self.charge('7').status_code, 409)       # P5 > P4

    def test_a_browser_cannot_set_the_cash_on_a_utang_sale(self):
        response = self.charge('7', cash_received='999')
        self.assertEqual(Decimal(response.data['receipt']['cash_received']), 0)

    def test_the_shift_expected_cash_ignores_utang_sales_but_counts_payments(self):
        self.charge('7')                      
        self.pay('2')                         
        closed = self.api.post('/api/shifts/end/', {'counted_cash': '1002'}, format='json')
        shift = closed.data['shift']
        self.assertEqual(Decimal(shift['expected_cash']), Decimal('1002'))  
        self.assertEqual(Decimal(shift['variance']), 0)
        self.assertEqual(Decimal(closed.data['utang_given']), Decimal('5'))
        self.assertEqual(Decimal(closed.data['utang_collected']), Decimal('2'))

    def test_the_report_lists_utang_by_customer(self):
        self.charge('7')
        self.pay('2')
        closed = self.api.post('/api/shifts/end/', {'counted_cash': '1002'}, format='json')
        self.assertIsNotNone(closed.data['report'])
        self.assertEqual(ShiftReport.objects.count(), 1)
        data = build_report_data(Shift.objects.get(), owner=False, report_no='X')
        self.assertEqual(data['utang_given'], [{'customer': 'Aling Nena', 'amount': Decimal('5.00')}])
        self.assertEqual(data['utang_collected'], [{'customer': 'Aling Nena', 'amount': Decimal('2.00')}])
        self.assertEqual(data['sales_total'], Decimal('5.00'))
        self.assertEqual(data['cash_sales'], 0)


class PaymentTests(UtangBase):
    def test_a_partial_payment(self):
        self.charge('7')                                   # SR-000001, owes 5
        response = self.pay('2')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.balance(), Decimal('3'))
        payment = UtangPayment.objects.get()
        self.assertEqual((payment.shift, payment.received_by, payment.receipt_no),
                         (self.shift, self.cashier, 'SR-000002'))
        self.assertEqual(payment.balance_after, Decimal('3'))
        receipt = response.data['receipt']
        self.assertEqual((receipt['kind'], receipt['customer']['name']), ('utang_payment', 'Aling Nena'))
        self.assertEqual(Decimal(receipt['balance_after']), Decimal('3'))
        self.assertEqual(Receipt.objects.get(receipt_no='SR-000002').source, 'utang_payment')

    def test_a_full_payment_clears_the_balance(self):
        self.charge('7')
        self.assertEqual(self.pay('5').status_code, 201)
        self.assertEqual(self.balance(), 0)

    def test_more_than_the_balance_is_refused_and_uses_no_receipt_number(self):
        self.charge('7')
        response = self.pay('5.01')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.balance(), Decimal('5'))
        self.assertEqual(UtangPayment.objects.count(), 0)
        self.assertEqual(self.pay('1').data['receipt']['receipt_no'], 'SR-000002')

    def test_bad_amounts_and_customers(self):
        self.charge('7')
        for amount in ('0', '-1', 'abc', '1.234', ''):
            with self.subTest(amount=amount):
                self.assertEqual(self.pay(amount).status_code, 400)
        self.assertEqual(self.pay('1', customer=999999).status_code, 404)
        self.assertEqual(UtangPayment.objects.count(), 0)

    def test_a_customer_who_owes_nothing_cannot_pay(self):
        self.assertEqual(self.pay('1').status_code, 400)

    def test_payments_need_the_cashiers_own_open_shift(self):
        self.charge('7')
        other = client_for(make_cashier('cash2'))
        self.assertEqual(self.pay('1', api=other).status_code, 400)
        self.assertEqual(self.balance(), Decimal('5'))

    def test_payments_are_append_only(self):
        self.charge('7')
        self.pay('1')
        payment = UtangPayment.objects.get()
        with self.assertRaises(PermissionError):
            payment.delete()
        payment.amount = Decimal('9')
        with self.assertRaises(PermissionError):
            payment.save()

    def test_the_payment_receipt_can_be_viewed_reprinted_and_listed(self):
        self.charge('7')
        number = self.pay('2').data['receipt']['receipt_no']
        view = self.api.get(f'/api/receipts/{number}/')
        self.assertEqual(view.data['kind'], 'utang_payment')
        self.assertFalse(view.data['is_copy'])
        copy = self.api.post(f'/api/receipts/{number}/reprint/')
        self.assertTrue(copy.data['is_copy'])
        self.assertEqual(Receipt.objects.get(receipt_no=number).printed_count, 1)
        kinds = {r['receipt_no']: r['kind'] for r in self.api.get('/api/sales/recent/').data}
        self.assertEqual(kinds, {'SR-000001': 'sale', number: 'utang_payment'})
        for text in (view.content.decode().lower(), copy.content.decode().lower()):
            self.assertNotIn('cost', text)
            self.assertNotIn('profit', text)


class CustomerApiTests(UtangBase):
    def test_register_a_customer(self):
        response = self.api.post('/api/customers/', {'name': 'Mang Ben', 'contact': 'Purok 3'}, format='json')
        self.assertEqual(response.status_code, 201)
        customer = Customer.objects.get(name='Mang Ben')
        self.assertEqual((customer.balance, customer.created_by), (0, self.cashier))
        self.assertEqual(response.data['credit_limit'], '500.00')       # the store default

    def test_a_browser_cannot_set_the_balance_or_limit(self):
        self.api.post('/api/customers/', {'name': 'Mang Ben', 'contact': 'x',
                                          'balance': '999', 'credit_limit': '99999'}, format='json')
        customer = Customer.objects.get(name='Mang Ben')
        self.assertEqual((customer.balance, customer.credit_limit), (0, None))

    def test_bad_and_duplicate_registrations(self):
        for body in ({'name': '', 'contact': 'x'}, {'name': 'Ben', 'contact': ''},
                     {'name': 'Ben'}, {'contact': 'x'}):
            with self.subTest(body=body):
                self.assertEqual(self.api.post('/api/customers/', body, format='json').status_code, 400)
        again = self.api.post('/api/customers/', {'name': 'aling nena', 'contact': '0917 000 0000'}, format='json')
        self.assertEqual(again.status_code, 400)

    def test_search_and_safe_fields(self):
        make_customer('Mang Ben', 'Purok 3')
        found = self.api.get('/api/customers/', {'q': 'nena'}).data
        self.assertEqual([c['name'] for c in found], ['Aling Nena'])
        self.assertEqual(set(found[0]), {'id', 'name', 'contact', 'balance', 'credit_limit'})
        self.assertEqual(len(self.api.get('/api/customers/').data), 2)
        self.assertEqual(len(self.api.get('/api/customers/', {'q': 'purok'}).data), 1)

    def test_the_customer_page_shows_balance_and_history(self):
        self.charge('7')
        self.pay('2')
        data = self.api.get(f'/api/customers/{self.nena.id}/').data
        self.assertEqual(Decimal(data['customer']['balance']), Decimal('3'))
        self.assertEqual([h['kind'] for h in data['history']], ['payment', 'charge'])

    def test_customers_cannot_be_deleted(self):
        self.assertEqual(self.api.delete(f'/api/customers/{self.nena.id}/').status_code, 405)
        with self.assertRaises(PermissionError):
            self.nena.delete()


class UtangIntegrityTests(UtangBase):
    def run_check(self):
        out = StringIO()
        call_command('check_integrity', stdout=out)
        return out.getvalue()

    def test_the_books_add_up_then_a_wrong_balance_is_caught(self):
        self.charge('7')
        self.pay('2')
        self.assertIn('OK', self.run_check())
        Customer.objects.filter(pk=self.nena.pk).update(balance=Decimal('999'))
        with self.assertRaises(CommandError):
            self.run_check()