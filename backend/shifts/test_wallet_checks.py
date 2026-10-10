from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from config.testkit import (
    client_for, fund_ewallet, fund_wallet, make_cashier, make_load, make_owner, open_shift,
)
from shifts.models import Shift, ShiftReopen
from shifts.reports import build_report_data
from wallets.models import ShiftWalletCheck, Wallet


class CheckBase(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.cashier = make_cashier()
        self.api = client_for(self.cashier)
        self.owner_api = client_for(self.owner)
        fund_wallet(self.owner, '1000')        # load wallet
        fund_ewallet(self.owner, '2000')       # GCash wallet
        self.load = Wallet.objects.get(type='load')
        self.gcash = Wallet.objects.get(type='ewallet')

    def balances(self, load='1000', gcash='2000'):
        return {str(self.load.id): load, str(self.gcash.id): gcash}

    def start(self, cash='1000', balances=None, api=None):
        body = {'opening_cash': cash,
                'wallet_balances': self.balances() if balances is None else balances}
        return (api or self.api).post('/api/shifts/start/', body, format='json')

    def end(self, counted='1000', balances=None, api=None):
        body = {'counted_cash': counted,
                'wallet_balances': self.balances() if balances is None else balances}
        return (api or self.api).post('/api/shifts/end/', body, format='json')

    def rows(self, response):
        return {r['wallet']: r for r in response.data['wallet_checks']}

    def run_check(self):
        out = StringIO()
        call_command('check_integrity', stdout=out)
        return out.getvalue()


class StartCheckTests(CheckBase):
    def test_a_balance_for_every_wallet_is_required(self):
        for balances in ({}, {str(self.load.id): '1000'}, self.balances(gcash=''),
                         self.balances(load='abc'), self.balances(load='-5'),
                         self.balances(gcash='1.234')):
            with self.subTest(balances=balances):
                self.assertEqual(self.start(balances=balances).status_code, 400)
        self.assertEqual(Shift.objects.count(), 0)
        self.assertEqual(ShiftWalletCheck.objects.count(), 0)

    def test_a_wallet_the_server_did_not_ask_for_is_refused(self):
        self.assertEqual(self.start(balances={**self.balances(), '99999': '5'}).status_code, 400)
        self.assertEqual(Shift.objects.count(), 0)

    def test_what_is_typed_is_compared_with_the_system_and_saved(self):
        response = self.start(balances=self.balances(load='950', gcash='2000'))
        self.assertEqual(response.status_code, 201)
        load = ShiftWalletCheck.objects.get(wallet=self.load)
        self.assertEqual((load.balance_start, load.expected_start, load.difference_start),
                         (Decimal('950'), Decimal('1000'), Decimal('-50')))
        self.assertEqual(ShiftWalletCheck.objects.get(wallet=self.gcash).difference_start, 0)

    def test_the_cashier_never_sees_the_comparison(self):
        response = self.start(balances=self.balances(load='950'))
        self.assertEqual(set(response.data), {'id', 'cashier', 'status', 'start_time', 'opening_cash'})
        listing = self.api.get('/api/shifts/wallets-to-check/')
        text = listing.content.decode().lower()
        for secret in ('balance', 'expected', 'gap', 'difference'):
            self.assertNotIn(secret, text)

    def test_the_list_of_wallets_to_check(self):
        before = self.api.get('/api/shifts/wallets-to-check/').data
        self.assertEqual(before['mode'], 'start')
        self.assertEqual({w['provider'] for w in before['wallets']}, {'Load wallet', 'GCash'})
        shift = self.start().data
        after = self.api.get('/api/shifts/wallets-to-check/').data
        self.assertEqual((after['mode'], len(after['wallets'])), ('end', 2))
        # The owner may ask about a shift. A cashier may not.
        self.assertEqual(len(self.owner_api.get(f"/api/shifts/wallets-to-check/?shift={shift['id']}").data['wallets']), 2)
        self.assertEqual(self.api.get(f"/api/shifts/wallets-to-check/?shift={shift['id']}").status_code, 403)
        self.assertEqual(self.owner_api.get('/api/shifts/wallets-to-check/?shift=abc').status_code, 400)
        self.assertEqual(client_for().get('/api/shifts/wallets-to-check/').status_code, 401)

    def test_an_inactive_wallet_is_not_checked(self):
        Wallet.objects.filter(pk=self.gcash.pk).update(is_active=False)
        self.assertEqual(self.start(balances={str(self.load.id): '1000'}).status_code, 201)
        self.assertEqual(ShiftWalletCheck.objects.count(), 1)

    def test_a_rejected_start_leaves_nothing_behind(self):
        self.start(cash='-5')
        self.assertEqual(ShiftWalletCheck.objects.count(), 0)


class NoWalletsTests(TestCase):
    def test_a_store_without_wallets_starts_and_ends_as_before(self):
        cashier = make_cashier()
        api = client_for(cashier)
        self.assertEqual(api.post('/api/shifts/start/', {'opening_cash': '1000'}, format='json').status_code, 201)
        closed = api.post('/api/shifts/end/', {'counted_cash': '1000'}, format='json')
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.data['wallet_checks'], [])

    def test_a_shift_without_start_checks_needs_no_end_balances(self):
        owner, cashier = make_owner(), make_cashier()
        fund_wallet(owner, '1000')
        open_shift(cashier)                      # created without checks (like old shifts)
        closed = client_for(cashier).post('/api/shifts/end/', {'counted_cash': '1000'}, format='json')
        self.assertEqual(closed.status_code, 200)


class EndCheckTests(CheckBase):
    def test_every_balance_is_required_to_end(self):
        self.start()
        for balances in ({}, {str(self.load.id): '1000'}, self.balances(load='abc')):
            with self.subTest(balances=balances):
                self.assertEqual(self.end(balances=balances).status_code, 400)
        self.assertEqual(Shift.objects.get().status, 'open')

    def test_an_exact_end_has_no_gap(self):
        self.start()
        closed = self.end()
        self.assertEqual(closed.status_code, 200)
        for row in closed.data['wallet_checks']:
            self.assertEqual(Decimal(row['gap']), 0)
            self.assertNotIn('start_gap', row)         # the cashier never gets the start comparison
            self.assertNotIn('start_expected', row)

    def test_the_expected_balance_follows_the_shifts_own_activity(self):
        _, product = make_load()
        self.start()
        sent = self.api.post('/api/load/send/', {
            'product': product.id, 'mobile_no': '09171234567', 'reference_no': 'REF00001'}, format='json')
        self.assertEqual(sent.status_code, 201)              # the load wallet: 1000 - 50
        fund_wallet(self.owner, '500')                       # the owner tops up DURING the shift
        row = self.rows(self.end('1052', self.balances(load='1450', gcash='2000')))['Load wallet']
        self.assertEqual((Decimal(row['expected']), Decimal(row['gap'])), (Decimal('1450'), 0))

    def test_a_shortage_is_a_negative_gap(self):
        self.start()
        row = self.rows(self.end(balances=self.balances(load='940')))['Load wallet']
        self.assertEqual(Decimal(row['gap']), Decimal('-60'))   
        over = Shift.objects.get()
        self.assertEqual(over.status, 'closed')

    def test_a_wrong_start_count_is_not_blamed_again_at_the_end(self):
        self.start(balances=self.balances(load='900'))       # the system said 1000
        row = self.rows(self.end(balances=self.balances(load='900')))['Load wallet']
        self.assertEqual(Decimal(row['gap']), 0)             # nothing moved in THIS shift
        self.assertEqual(ShiftWalletCheck.objects.get(wallet=self.load).difference_start, Decimal('-100'))

    def test_a_closed_shifts_checks_cannot_be_changed(self):
        self.start()
        self.end()
        check = ShiftWalletCheck.objects.get(wallet=self.load)
        check.balance_end = Decimal('1')
        with self.assertRaises(PermissionError):
            check.save()
        with self.assertRaises(PermissionError):
            check.delete()

    def test_the_owner_closing_on_behalf_must_count_the_wallets_too(self):
        shift = self.start().data
        url = f"/api/shifts/{shift['id']}/close/"
        body = {'counted_cash': '1000', 'reason': 'Went home sick'}
        self.assertEqual(self.owner_api.post(url, body, format='json').status_code, 400)
        ok = self.owner_api.post(url, {**body, 'wallet_balances': self.balances(load='990')}, format='json')
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(Decimal(self.rows(ok)['Load wallet']['gap']), Decimal('-10'))

    def test_reopening_saves_the_old_wallet_numbers_and_clears_them(self):
        shift = self.start().data
        self.end(balances=self.balances(load='940'))
        self.assertEqual(self.owner_api.post(f"/api/shifts/{shift['id']}/reopen/", {'reason': 'Recount'}, format='json').status_code, 200)
        log = ShiftReopen.objects.get()
        saved = {r['wallet']: r for r in log.previous_wallet_checks}
        self.assertEqual(Decimal(saved['Load wallet']['difference_end']), Decimal('-60'))
        check = ShiftWalletCheck.objects.get(wallet=self.load)
        self.assertIsNone(check.balance_end)
        row = self.rows(self.end(balances=self.balances(load='1000')))['Load wallet']
        self.assertEqual(Decimal(row['gap']), 0)
        self.assertIn('OK', self.run_check())


class OwnerViewTests(CheckBase):
    def test_the_owner_list_shows_the_start_comparison_and_the_filter_finds_wallet_gaps(self):
        self.start(balances=self.balances(load='950'))
        self.end()                                           # cash exact, wallet gaps only
        shift = self.owner_api.get('/api/shifts/').data[0]
        rows = {r['wallet']: r for r in shift['wallet_checks']}
        self.assertEqual(Decimal(rows['Load wallet']['start_gap']), Decimal('-50'))
        self.assertEqual(Decimal(rows['Load wallet']['start_expected']), Decimal('1000'))
        flagged = self.owner_api.get('/api/shifts/?variance=1').data
        self.assertEqual(len(flagged), 1)                    # flagged by the wallet, not by the cash

    def test_a_clean_shift_is_not_flagged(self):
        self.start()
        self.end()
        self.assertEqual(self.owner_api.get('/api/shifts/?variance=1').data, [])

    def test_the_cashier_cannot_use_the_owner_list(self):
        self.assertEqual(self.api.get('/api/shifts/').status_code, 403)


class ReportAndIntegrityTests(CheckBase):
    def test_the_cashier_copy_has_no_start_comparison_and_the_owner_copy_does(self):
        self.start(balances=self.balances(load='950'))
        closed = self.end(balances=self.balances(load='940'))
        self.assertIsNotNone(closed.data['report'])
        shift = Shift.objects.get()
        cashier_copy = build_report_data(shift, owner=False, report_no='X')
        owner_copy = build_report_data(shift, owner=True, report_no='X')
        text = str(cashier_copy)
        for secret in ('start_gap', 'start_expected'):
            self.assertNotIn(secret, text)
        self.assertEqual(len(cashier_copy['wallet_checks']), 2)
        row = {r['wallet']: r for r in owner_copy['wallet_checks']}['Load wallet']
        self.assertEqual((Decimal(row['start_gap']), Decimal(row['gap'])), (Decimal('-50'), Decimal('-10')))

    def test_the_books_add_up_and_tampering_is_caught(self):
        self.start()
        self.end()
        self.assertIn('OK', self.run_check())
        ShiftWalletCheck.objects.filter(wallet=self.load).update(difference_end=Decimal('77'))
        with self.assertRaises(CommandError):
            self.run_check()

    def test_a_changed_start_gap_is_caught(self):
        self.start(balances=self.balances(load='950'))
        ShiftWalletCheck.objects.filter(wallet=self.load).update(difference_start=Decimal('0'))
        with self.assertRaises(CommandError):
            self.run_check()