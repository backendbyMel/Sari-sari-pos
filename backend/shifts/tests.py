from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from config.testkit import client_for, make_candy, make_cashier, make_owner, open_shift
from sales.models import Sale
from shifts.models import Shift, ShiftReopen, CashMovement


def closed_shift(cashier, counted='1500.00'):
    """A finished shift, for testing the opening-cash comparison."""
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

class EndShiftTests(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.cashier = make_cashier()
        self.shift = open_shift(self.cashier, '1000.00')
        self.api = client_for(self.cashier)
        self.owner_api = client_for(self.owner)
        _, self.piece = make_candy()

    def sell(self, qty='7', cash='10'):
        return self.api.post('/api/sales/', {
            'items': [{'product_unit': self.piece.id, 'quantity': qty}],
            'cash_received': cash}, format='json')

    def end(self, **body):
        return self.api.post('/api/shifts/end/', body, format='json')

    def test_exact_count_has_zero_variance(self):
        self.sell()                                   # 7 candies = P5.00 (change P5 went back)
        response = self.end(counted_cash='1005.00')
        self.assertEqual(response.status_code, 200)
        shift = response.data['shift']
        self.assertEqual(Decimal(shift['expected_cash']), Decimal('1005'))   # 1000 + 5, not + 10
        self.assertEqual(Decimal(shift['variance']), 0)
        self.assertEqual(shift['status'], 'closed')
        self.assertFalse(shift['closed_on_behalf'])
        self.assertEqual(response.data['sales_count'], 1)
        self.assertEqual(Decimal(response.data['cash_sales']), Decimal('5'))

    def test_short_is_negative(self):
        self.sell()
        shift = self.end(counted_cash='995.00').data['shift']
        self.assertEqual(Decimal(shift['variance']), Decimal('-10'))

    def test_over_is_positive(self):
        self.sell()
        shift = self.end(counted_cash='1010.00').data['shift']
        self.assertEqual(Decimal(shift['variance']), Decimal('5'))

    def test_voided_sales_do_not_count(self):
        self.sell()                                   # SR-000001, P5
        self.sell('1', '5')                           # SR-000002, P1
        Sale.objects.filter(receipt_no='SR-000001').update(status='voided')
        shift = self.end(counted_cash='1001.00').data['shift']
        self.assertEqual(Decimal(shift['expected_cash']), Decimal('1001'))
        self.assertEqual(Decimal(shift['variance']), 0)

    def test_the_server_adds_up_the_breakdown(self):
        denominations = {'1000': '1', '500': '0', '200': '0', '100': '1',
                         '50': '0', '20': '0', 'coins': '5.50'}
        shift = self.end(denominations=denominations).data['shift']
        self.assertEqual(Decimal(shift['counted_cash']), Decimal('1105.50'))
        self.assertEqual(Decimal(shift['variance']), Decimal('105.50'))
        self.assertEqual(shift['denominations']['1000'], 1)

    def test_a_total_that_contradicts_the_breakdown_is_refused(self):
        response = self.end(counted_cash='1000', denominations={'1000': '1', 'coins': '5'})
        self.assertEqual(response.status_code, 400)

    def test_bad_counts_are_refused(self):
        bad = {
            'nothing': {},
            'negative total': {'counted_cash': '-5'},
            'text total': {'counted_cash': 'abc'},
            'empty breakdown': {'denominations': {}},
            'unknown note': {'denominations': {'25': '3'}},
            'negative bills': {'denominations': {'1000': '-1'}},
            'fractional bills': {'denominations': {'1000': '1.5'}},
            'bad coins': {'denominations': {'coins': '1.234'}},
        }
        for name, body in bad.items():
            with self.subTest(case=name):
                self.assertEqual(self.end(**body).status_code, 400)
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.status, 'open')

    def test_a_closed_shift_is_locked(self):
        self.end(counted_cash='1000')
        self.assertEqual(self.sell().status_code, 400)             # no open shift
        self.assertEqual(self.end(counted_cash='1000').status_code, 400)   # cannot end twice
        self.shift.refresh_from_db()
        self.shift.counted_cash = Decimal('5000')
        with self.assertRaises(PermissionError):
            self.shift.save()

    def test_no_shift_no_end(self):
        self.end(counted_cash='1000')
        self.assertEqual(client_for(make_cashier('cash2')).post(
            '/api/shifts/end/', {'counted_cash': '1'}, format='json').status_code, 400)

    def test_the_cashier_copy_has_no_comparison_fields(self):
        text = self.end(counted_cash='1000').content.decode().lower()
        for secret in ('previous', 'difference'):
            self.assertNotIn(secret, text)

    def test_the_next_shift_is_compared_with_this_count(self):
        self.end(counted_cash='1500')
        self.api.post('/api/shifts/start/', {'opening_cash': '1450'}, format='json')
        new = Shift.objects.get(status='open')
        self.assertEqual(new.previous_closing_cash, Decimal('1500'))
        self.assertEqual(new.opening_difference, Decimal('-50'))


class OwnerCloseTests(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.cashier = make_cashier()
        self.shift = open_shift(self.cashier, '1000.00')
        self.cashier_api = client_for(self.cashier)
        self.owner_api = client_for(self.owner)
        self.url = f'/api/shifts/{self.shift.id}/close/'

    def test_a_cashier_cannot_use_it(self):
        response = self.cashier_api.post(self.url, {'counted_cash': '1000', 'reason': 'x'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_a_reason_is_required(self):
        for body in ({'counted_cash': '1000'}, {'counted_cash': '1000', 'reason': ''},
                     {'counted_cash': '1000', 'reason': '   '}):
            with self.subTest(body=body):
                self.assertEqual(self.owner_api.post(self.url, body, format='json').status_code, 400)
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.status, 'open')

    def test_owner_closes_on_behalf_and_it_is_recorded(self):
        response = self.owner_api.post(
            self.url, {'counted_cash': '990', 'reason': 'Cashier went home sick'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.closed_by, self.owner)
        self.assertEqual(self.shift.cashier, self.cashier)
        self.assertEqual(self.shift.close_reason, 'Cashier went home sick')
        self.assertEqual(self.shift.variance, Decimal('-10'))
        self.assertTrue(response.data['shift']['closed_on_behalf'])

    def test_unknown_shift(self):
        response = self.owner_api.post('/api/shifts/9999/close/',
                                       {'counted_cash': '1', 'reason': 'x'}, format='json')
        self.assertEqual(response.status_code, 404)


class ReopenTests(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.cashier = make_cashier()
        self.shift = open_shift(self.cashier, '1000.00')
        self.cashier_api = client_for(self.cashier)
        self.owner_api = client_for(self.owner)
        self.cashier_api.post('/api/shifts/end/', {'counted_cash': '990'}, format='json')
        self.url = f'/api/shifts/{self.shift.id}/reopen/'

    def test_only_the_owner_with_a_reason(self):
        self.assertEqual(self.cashier_api.post(self.url, {'reason': 'x'}, format='json').status_code, 403)
        self.assertEqual(self.owner_api.post(self.url, {}, format='json').status_code, 400)
        self.assertEqual(self.owner_api.post(self.url, {'reason': ''}, format='json').status_code, 400)
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.status, 'closed')

    def test_reopening_logs_the_old_count_and_clears_it(self):
        response = self.owner_api.post(self.url, {'reason': 'Counted wrong'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.status, 'open')
        self.assertIsNone(self.shift.counted_cash)
        self.assertIsNone(self.shift.end_time)
        log = ShiftReopen.objects.get()
        self.assertEqual(log.reopened_by, self.owner)
        self.assertEqual(log.reason, 'Counted wrong')
        self.assertEqual(log.previous_counted_cash, Decimal('990'))
        self.assertEqual(log.previous_variance, Decimal('-10'))

    def test_the_cashier_can_sell_and_close_again(self):
        self.owner_api.post(self.url, {'reason': 'Counted wrong'}, format='json')
        _, piece = make_candy()
        sale = self.cashier_api.post('/api/sales/', {
            'items': [{'product_unit': piece.id, 'quantity': '1'}], 'cash_received': '5'}, format='json')
        self.assertEqual(sale.status_code, 201)
        shift = self.cashier_api.post('/api/shifts/end/', {'counted_cash': '1001'}, format='json').data['shift']
        self.assertEqual(Decimal(shift['variance']), 0)

    def test_an_open_shift_cannot_be_reopened(self):
        self.owner_api.post(self.url, {'reason': 'once'}, format='json')
        self.assertEqual(self.owner_api.post(self.url, {'reason': 'twice'}, format='json').status_code, 400)
        self.assertEqual(ShiftReopen.objects.count(), 1)

    def test_only_the_most_recent_shift_can_be_reopened(self):
        open_shift(self.cashier)           # a newer shift now exists
        response = self.owner_api.post(self.url, {'reason': 'too late'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('most recent', str(response.data))
        self.assertEqual(ShiftReopen.objects.count(), 0)

    def test_reopen_records_are_permanent(self):
        self.owner_api.post(self.url, {'reason': 'x'}, format='json')
        log = ShiftReopen.objects.get()
        with self.assertRaises(PermissionError):
            log.delete()
        log.reason = 'changed'
        with self.assertRaises(PermissionError):
            log.save()


class ShiftListTests(TestCase):
    def test_owner_sees_everything_and_the_cashier_nothing(self):
        cashier = make_cashier()
        open_shift(cashier)
        owner_row = client_for(make_owner()).get('/api/shifts/').data[0]
        self.assertIn('opening_difference', owner_row)
        self.assertEqual(owner_row['reopen_count'], 0)
        self.assertEqual(client_for(cashier).get('/api/shifts/').status_code, 403)

class PayoutTests(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.cashier = make_cashier()
        self.shift = open_shift(self.cashier, '1000.00')
        self.api = client_for(self.cashier)
        _, self.piece = make_candy()

    def payout(self, amount='100', reason='Bought ice', api=None):
        return (api or self.api).post(
            '/api/shifts/payouts/', {'amount': amount, 'reason': reason}, format='json')

    def sell(self, qty='7', cash='10'):
        return self.api.post('/api/sales/', {
            'items': [{'product_unit': self.piece.id, 'quantity': qty}],
            'cash_received': cash}, format='json')

    def test_a_payout_is_recorded_under_the_cashier_and_shift(self):
        response = self.payout()
        self.assertEqual(response.status_code, 201)
        movement = CashMovement.objects.get()
        self.assertEqual(movement.shift, self.shift)
        self.assertEqual(movement.recorded_by, self.cashier)
        self.assertEqual(movement.type, 'out')
        self.assertEqual(movement.amount, Decimal('100.00'))
        self.assertEqual(movement.reason, 'Bought ice')

    def test_bad_requests_are_refused(self):
        bad = [
            {'amount': '0', 'reason': 'x'}, {'amount': '-5', 'reason': 'x'},
            {'amount': 'abc', 'reason': 'x'}, {'amount': '1.234', 'reason': 'x'},
            {'amount': '', 'reason': 'x'}, {'amount': '10'},
            {'amount': '10', 'reason': ''}, {'amount': '10', 'reason': '   '},
        ]
        for body in bad:
            with self.subTest(body=body):
                self.assertEqual(self.api.post('/api/shifts/payouts/', body, format='json').status_code, 400)
        self.assertEqual(CashMovement.objects.count(), 0)

    def test_no_open_shift_no_payout(self):
        other = client_for(make_cashier('cash2'))       # has no shift
        self.assertEqual(self.payout(api=other).status_code, 400)
        self.assertEqual(CashMovement.objects.count(), 0)

    def test_a_closed_shift_takes_no_payouts(self):
        self.api.post('/api/shifts/end/', {'counted_cash': '1000'}, format='json')
        self.assertEqual(self.payout().status_code, 400)

    def test_a_browser_cannot_choose_the_shift_or_the_person(self):
        other_shift = open_shift  # (only one shift can be open, so just try to inject ids)
        body = {'amount': '10', 'reason': 'x', 'shift': 999, 'recorded_by': self.owner.id}
        self.assertEqual(self.api.post('/api/shifts/payouts/', body, format='json').status_code, 201)
        movement = CashMovement.objects.get()
        self.assertEqual(movement.shift, self.shift)
        self.assertEqual(movement.recorded_by, self.cashier)

    def test_payouts_reduce_the_expected_cash(self):
        self.sell()                    # P5.00 of cash sales
        self.payout('100')
        shift = self.api.post('/api/shifts/end/', {'counted_cash': '905'}, format='json').data
        self.assertEqual(Decimal(shift['shift']['expected_cash']), Decimal('905'))   # 1000 + 5 - 100
        self.assertEqual(Decimal(shift['shift']['variance']), 0)
        self.assertEqual(Decimal(shift['payouts_total']), Decimal('100'))
        self.assertEqual(shift['payouts_count'], 1)

    def test_a_big_payout_warns_without_revealing_the_expected_cash(self):
        response = self.payout('5000')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data['warnings']), 1)
        self.assertNotIn('1000', response.data['warnings'][0])

    def test_a_normal_payout_has_no_warning(self):
        self.assertEqual(self.payout('100').data['warnings'], [])

    def test_the_summary_shows_sales_and_payouts_but_no_secrets(self):
        self.sell()
        self.payout('100', 'Bought ice')
        response = self.api.get('/api/shifts/summary/')
        self.assertEqual(response.data['sales_count'], 1)
        self.assertEqual(Decimal(response.data['sales_total']), Decimal('5'))
        self.assertEqual(Decimal(response.data['payouts_total']), Decimal('100'))
        self.assertEqual(response.data['payouts'][0]['reason'], 'Bought ice')
        text = response.content.decode().lower()
        for secret in ('expected', 'cost', 'profit', 'previous', 'difference'):
            self.assertNotIn(secret, text)

    def test_the_summary_without_a_shift(self):
        other = client_for(make_cashier('cash2'))
        self.assertIsNone(other.get('/api/shifts/summary/').data['shift'])

    def test_payouts_are_append_only(self):
        self.payout()
        movement = CashMovement.objects.get()
        with self.assertRaises(PermissionError):
            movement.delete()
        movement.amount = Decimal('1')
        with self.assertRaises(PermissionError):
            movement.save()

    def test_the_owner_sees_every_payout_and_the_cashier_cannot(self):
        self.payout('100', 'Bought ice')
        url = f'/api/shifts/{self.shift.id}/payouts/'
        rows = client_for(self.owner).get(url).data
        self.assertEqual(rows[0]['reason'], 'Bought ice')
        self.assertEqual(rows[0]['recorded_by'], 'cash')
        self.assertEqual(self.api.get(url).status_code, 403)

    def test_the_owner_list_includes_payout_totals(self):
        self.payout('100')
        self.payout('50.50', 'Paid supplier')
        row = client_for(self.owner).get('/api/shifts/').data[0]
        self.assertEqual(Decimal(row['payouts_total']), Decimal('150.50'))
        self.assertEqual(row['payouts_count'], 2)