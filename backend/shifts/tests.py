from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from config.testkit import client_for, make_cashier, make_owner, open_shift
from shifts.models import Shift

# Create your tests here.
def closed_shift(cashier, counted='1500.00'):
    return Shift.objects.create(
        cashier=cashier, opening_cash=Decimal('1000'), status='closed',
        end_time=timezone.now(), counted_cash=Decimal(counted),
    )


class StartShiftTests(TestCase):
    def setUp(self):
        self.cashier = make_cashier()
        self.api = client_for(self.cashier)

    def start(self, cash, api=None):
        return (api or self.api).post('/api/shifts/start/', {'opening_cash': cash}, format='json')

    def test_start_a_shift(self):
        response = self.start('1000.00')
        self.assertEqual(response.status_code, 201)
        shift = Shift.objects.get()
        self.assertEqual(shift.status, 'open')
        self.assertEqual(shift.cashier, self.cashier)   # from the login
        self.assertEqual(shift.opening_cash, Decimal('1000.00'))

    def test_bad_amounts_refused(self):
        for bad in ('-5', 'abc', ''):
            with self.subTest(amount=bad):
                self.assertEqual(self.start(bad).status_code, 400)
        self.assertEqual(self.api.post('/api/shifts/start/', {}, format='json').status_code, 400)
        self.assertEqual(Shift.objects.count(), 0)

    def test_zero_opening_cash_is_allowed(self):
        self.assertEqual(self.start('0').status_code, 201)

    def test_cannot_start_twice(self):
        self.start('1000')
        self.assertEqual(self.start('1000').status_code, 400)
        self.assertEqual(Shift.objects.count(), 1)

    def test_cannot_start_while_another_cashier_is_on_duty(self):
        open_shift(make_cashier('cash2'))
        response = self.start('1000')
        self.assertEqual(response.status_code, 400)
        self.assertIn('cash2', str(response.data))

    def test_the_database_itself_refuses_a_second_open_shift(self):
        open_shift(self.cashier)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Shift.objects.create(cashier=make_cashier('cash2'), opening_cash=Decimal('0'))

    def test_first_ever_shift_has_nothing_to_compare(self):
        self.start('1000')
        shift = Shift.objects.get()
        self.assertIsNone(shift.previous_closing_cash)
        self.assertIsNone(shift.opening_difference)

    def test_a_difference_from_the_last_closing_count_is_flagged(self):
        closed_shift(make_cashier('cash2'), counted='1500.00')
        self.start('1450.00')
        shift = Shift.objects.get(status='open')
        self.assertEqual(shift.previous_closing_cash, Decimal('1500.00'))
        self.assertEqual(shift.opening_difference, Decimal('-50.00'))

    def test_matching_cash_gives_a_zero_difference(self):
        closed_shift(make_cashier('cash2'), counted='1500.00')
        self.start('1500.00')
        self.assertEqual(Shift.objects.get(status='open').opening_difference, Decimal('0'))

    def test_the_cashier_never_sees_the_comparison(self):
        closed_shift(make_cashier('cash2'), counted='1500.00')
        response = self.start('1450.00')
        self.assertEqual(set(response.data), {'id', 'cashier', 'status', 'start_time', 'opening_cash'})
        text = self.api.get('/api/shifts/current/').content.decode().lower()
        for secret in ('previous', 'difference', '1500'):
            self.assertNotIn(secret, text)

    def test_shifts_cannot_be_deleted(self):
        shift = open_shift(self.cashier)
        with self.assertRaises(PermissionError):
            shift.delete()


class CurrentShiftTests(TestCase):
    def setUp(self):
        self.cashier = make_cashier()
        self.api = client_for(self.cashier)

    def test_no_shift_open(self):
        data = self.api.get('/api/shifts/current/').data
        self.assertIsNone(data['shift'])
        self.assertFalse(data['is_mine'])

    def test_my_shift(self):
        open_shift(self.cashier)
        data = self.api.get('/api/shifts/current/').data
        self.assertTrue(data['is_mine'])
        self.assertEqual(data['shift']['cashier'], 'cash')

    def test_someone_elses_shift(self):
        open_shift(make_cashier('cash2'))
        data = self.api.get('/api/shifts/current/').data
        self.assertFalse(data['is_mine'])
        self.assertEqual(data['shift']['cashier'], 'cash2')

    def test_the_owner_can_check_too(self):
        self.assertEqual(client_for(make_owner()).get('/api/shifts/current/').status_code, 200)