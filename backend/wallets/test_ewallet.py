from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from config.testkit import client_for, fund_ewallet, make_cashier, make_gcash, make_owner, open_shift
from core.services import set_cashier_can_topup
from sales.models import Receipt
from shifts.models import CashMovement, Shift
from shifts.reports import build_report_data
from wallets.models import EWalletTransaction, FeeRule, Wallet, WalletTransaction


class GcashBase(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.cashier = make_cashier()
        self.shift = open_shift(self.cashier, '1000.00')
        self.api = client_for(self.cashier)
        self.owner_api = client_for(self.owner)
        self.wallet = make_gcash()
        fund_ewallet(self.owner, '2000')
        self.n = 0

    def go(self, kind, amount, mobile='0917 123 4567', reference=None, api=None, **extra):
        if reference is None:
            self.n += 1
            reference = f'GC{self.n:010d}'
        body = {'amount': amount, 'mobile_no': mobile, 'reference_no': reference}
        body.update(extra)
        return (api or self.api).post(f'/api/ewallet/{kind}/', body, format='json')

    def balance(self):
        return Wallet.objects.get(type='ewallet').balance

    def end(self, counted):
        return self.api.post('/api/shifts/end/', {'counted_cash': counted}, format='json')

    def reverse(self, tx_id, note='Customer cancelled', api=None):
        return (api or self.owner_api).post(f'/api/owner/ewallet/{tx_id}/reverse/', {'note': note}, format='json')

    def run_check(self):
        out = StringIO()
        call_command('check_integrity', stdout=out)
        return out.getvalue()


class CashInOutTests(GcashBase):
    def test_cash_in(self):
        response = self.go('cash-in', 500)
        self.assertEqual(response.status_code, 201)
        receipt = response.data['receipt']
        self.assertEqual((receipt['kind'], receipt['total'], receipt['receipt_no']), ('ewallet', '510.00', 'SR-000001'))
        self.assertEqual(receipt['ewallet'], {
            'service': 'GCash', 'type': 'cash_in', 'amount': '500.00', 'fee': '10.00',
            'mobile': '0917***4567', 'reference_no': 'GC0000000001'})
        self.assertEqual(self.balance(), Decimal('1500'))
        tx = EWalletTransaction.objects.get()
        self.assertEqual((tx.fee, tx.table_fee, tx.fee_overridden, tx.shift, tx.cashier, tx.customer_mobile),
                         (Decimal('10'), Decimal('10'), False, self.shift, self.cashier, '09171234567'))
        entry = WalletTransaction.objects.filter(type='cash_in').get()
        self.assertEqual((entry.amount, entry.balance_after, entry.user), (Decimal('-500'), Decimal('1500'), self.cashier))
        self.assertEqual(Receipt.objects.get(receipt_no='SR-000001').source, 'ewallet')

    def test_cash_out(self):
        response = self.go('cash-out', 500)
        self.assertEqual(response.data['receipt']['total'], '490.00')      # amount - fee
        self.assertEqual(self.balance(), Decimal('2500'))
        self.assertEqual(WalletTransaction.objects.filter(type='cash_out').get().amount, Decimal('500'))

    def test_the_drawer_formula_follows_the_spec(self):
        self.go('cash-in', 500)      # drawer + (500 + 10)
        self.go('cash-out', 200)     # drawer - 200 + 10
        closed = self.end('1320')    # 1000 + 510 - 190
        self.assertEqual(Decimal(closed.data['shift']['expected_cash']), Decimal('1320'))
        self.assertEqual(Decimal(closed.data['shift']['variance']), 0)
        self.assertEqual((closed.data['ewallet_in'], closed.data['ewallet_out'], closed.data['ewallet_count']),
                         ('510.00', '190.00', 2))

    def test_fee_boundaries_and_the_quote(self):
        fees = {500: '10.00', 501: '20.00', 1000: '20.00', 1: '10.00'}
        for amount, fee in fees.items():
            with self.subTest(amount=amount):
                self.assertEqual(self.api.get('/api/ewallet/quote/', {'amount': amount}).data['fee'], fee)
        self.assertIsNone(self.api.get('/api/ewallet/quote/', {'amount': 1001}).data['fee'])
        for bad in ('abc', '0', '-5', '1.5', ''):
            with self.subTest(bad=bad):
                self.assertEqual(self.api.get('/api/ewallet/quote/', {'amount': bad}).status_code, 400)

    def test_no_fee_range_needs_an_override(self):
        self.assertEqual(self.go('cash-in', 1500).status_code, 400)
        self.assertEqual(self.balance(), Decimal('2000'))
        ok = self.go('cash-in', 1500, fee_override='30', override_reason='Big transaction')
        self.assertEqual(ok.status_code, 201)
        self.assertIsNone(EWalletTransaction.objects.get().table_fee)

    def test_a_different_fee_needs_a_reason_and_is_flagged(self):
        for reason in ('', '   '):
            self.assertEqual(self.go('cash-in', 600, fee_override='15', override_reason=reason).status_code, 400)
        self.assertEqual(EWalletTransaction.objects.count(), 0)
        self.assertEqual(self.go('cash-in', 600, fee_override='15', override_reason='Regular customer').status_code, 201)
        tx = EWalletTransaction.objects.get()
        self.assertEqual((tx.fee, tx.table_fee, tx.fee_overridden, tx.fee_override_reason),
                         (Decimal('15'), Decimal('20'), True, 'Regular customer'))

    def test_the_same_fee_is_not_an_override(self):
        self.go('cash-in', 600, fee_override='20')
        self.assertFalse(EWalletTransaction.objects.get().fee_overridden)

    def test_a_fee_bigger_than_the_amount_is_refused(self):
        response = self.go('cash-out', 5, fee_override='9', override_reason='x')
        self.assertEqual(response.status_code, 400)

    def test_bad_requests(self):
        for amount in (0, -5, '1.5', 'abc', ''):
            with self.subTest(amount=amount):
                self.assertEqual(self.go('cash-in', amount).status_code, 400)
        for mobile in ('12345', '0817 123 4567', ''):
            with self.subTest(mobile=mobile):
                self.assertEqual(self.go('cash-in', 100, mobile=mobile).status_code, 400)
        for reference in ('', 'ab', 'a b c d', 'ab#12'):
            with self.subTest(reference=reference):
                self.assertEqual(self.go('cash-in', 100, reference=reference).status_code, 400)
        self.assertEqual(EWalletTransaction.objects.count(), 0)
        self.assertEqual(self.balance(), Decimal('2000'))

    def test_a_reference_can_be_used_once(self):
        self.assertEqual(self.go('cash-in', 100, reference='abc12345').status_code, 201)
        self.assertEqual(self.go('cash-out', 100, reference='ABC12345').status_code, 400)
        self.assertEqual(EWalletTransaction.objects.get().reference_no, 'ABC12345')

    def test_the_browser_cannot_set_the_fee_without_the_override_rules(self):
        response = self.go('cash-in', 500, fee='0', table_fee='0', status='reversed')
        self.assertEqual(response.data['receipt']['ewallet']['fee'], '10.00')

    def test_a_shift_is_required(self):
        outsider = client_for(make_cashier('cash2'))
        self.assertEqual(self.go('cash-in', 100, api=outsider).status_code, 400)
        self.assertEqual(self.go('cash-in', 100, api=self.owner_api).status_code, 400)
        self.assertEqual(EWalletTransaction.objects.count(), 0)

    def test_a_big_cash_out_warns_without_a_figure(self):
        FeeRule.objects.create(wallet=self.wallet, min_amount=1001, max_amount=10000, fee=Decimal('100'))
        response = self.go('cash-out', 5000)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data['warnings']), 1)
        self.assertFalse(any(ch.isdigit() for ch in response.data['warnings'][0]))

    def test_a_cash_in_with_a_low_wallet_warns_without_a_figure(self):
        self.owner_api.post('/api/owner/wallet/adjust/?kind=ewallet',
                            {'actual_balance': '100', 'reason': 'Counted'}, format='json')
        response = self.go('cash-in', 500)
        self.assertEqual(response.status_code, 201)
        self.assertFalse(any(ch.isdigit() for ch in response.data['warnings'][0]))
        self.assertEqual(self.balance(), Decimal('-400'))

    def test_a_normal_transaction_has_no_warnings(self):
        self.assertEqual(self.go('cash-in', 500).data['warnings'], [])

    def test_receipts_can_be_viewed_reprinted_and_listed(self):
        number = self.go('cash-in', 500).data['receipt']['receipt_no']
        self.assertEqual(self.api.get(f'/api/receipts/{number}/').data['kind'], 'ewallet')
        self.assertTrue(self.api.post(f'/api/receipts/{number}/reprint/').data['is_copy'])
        row = self.api.get('/api/sales/recent/').data[0]
        self.assertEqual((row['kind'], row['total'], row['status']), ('ewallet', '510.00', 'completed'))

    def test_cashiers_never_see_fee_totals_wallet_balances_or_overrides(self):
        self.go('cash-in', 500)
        for response in (self.api.get('/api/ewallet/mine/'), self.api.get('/api/shifts/summary/')):
            text = response.content.decode().lower()
            for secret in ('fee', 'balance', 'override', 'table'):
                self.assertNotIn(secret, text)


class ReversalTests(GcashBase):
    def test_the_owner_reverses_a_cash_in(self):
        tx_id = self.go('cash-in', 500).data['tx_id']
        response = self.reverse(tx_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['transaction']['status'], 'reversed')
        self.assertEqual(self.balance(), Decimal('2000'))
        tx = EWalletTransaction.objects.get()
        self.assertEqual((tx.reversed_by, tx.reversed_note), (self.owner, 'Customer cancelled'))
        entry = WalletTransaction.objects.filter(type='reversal').get()
        self.assertEqual((entry.amount, entry.user), (Decimal('500'), self.owner))
        self.assertTrue(self.api.get(f'/api/receipts/{tx.receipt_no}/').data['is_reversed'])
        self.assertEqual(self.api.get('/api/sales/recent/').data[0]['status'], 'voided')

    def test_the_owner_reverses_a_cash_out(self):
        tx_id = self.go('cash-out', 500).data['tx_id']
        self.reverse(tx_id)
        self.assertEqual(self.balance(), Decimal('2000'))

    def test_a_reversed_transaction_adds_no_expected_cash(self):
        self.reverse(self.go('cash-in', 500).data['tx_id'])
        closed = self.end('1000')
        self.assertEqual(Decimal(closed.data['shift']['expected_cash']), Decimal('1000'))
        self.assertEqual(Decimal(closed.data['shift']['variance']), 0)

    def test_note_owner_only_and_once(self):
        tx_id = self.go('cash-in', 500).data['tx_id']
        for note in ('', '   '):
            self.assertEqual(self.reverse(tx_id, note).status_code, 400)
        self.assertEqual(self.owner_api.post(f'/api/owner/ewallet/{tx_id}/reverse/', {}, format='json').status_code, 400)
        self.assertEqual(self.reverse(tx_id, api=self.api).status_code, 403)
        self.assertEqual(self.balance(), Decimal('1500'))
        self.assertEqual(self.reverse(tx_id).status_code, 200)
        self.assertEqual(self.reverse(tx_id).status_code, 400)
        self.assertEqual(self.balance(), Decimal('2000'))
        self.assertEqual(self.reverse(999999).status_code, 404)

    def test_a_closed_shift_cannot_be_reversed_here(self):
        tx_id = self.go('cash-in', 500).data['tx_id']
        self.end('1510')
        self.assertEqual(self.reverse(tx_id).status_code, 400)
        self.assertEqual(self.balance(), Decimal('1500'))

    def test_a_reversed_transaction_is_final(self):
        self.reverse(self.go('cash-in', 500).data['tx_id'])
        tx = EWalletTransaction.objects.get()
        tx.reversed_note = 'changed'
        with self.assertRaises(PermissionError):
            tx.save()
        with self.assertRaises(PermissionError):
            tx.delete()


class OwnerGcashTests(GcashBase):
    def test_the_owner_sees_fees_overrides_and_who_did_it(self):
        self.go('cash-in', 600, fee_override='15', override_reason='Regular customer')
        row = self.owner_api.get('/api/owner/ewallet/').data['transactions'][0]
        self.assertEqual((row['fee'], row['table_fee'], row['fee_overridden'], row['cashier'], row['can_reverse']),
                         ('15.00', '20.00', True, 'cash', True))
        self.assertEqual(self.api.get('/api/owner/ewallet/').status_code, 403)

    def test_the_fee_table_can_be_managed(self):
        post = self.owner_api.post
        made = post('/api/owner/fee-rules/', {'min_amount': 1001, 'max_amount': 2000, 'fee': '30'}, format='json')
        self.assertEqual(made.status_code, 201)
        self.assertEqual(self.api.get('/api/ewallet/quote/', {'amount': 1500}).data['fee'], '30.00')
        for bad in ({'min_amount': 1500, 'max_amount': 3000, 'fee': '40'},     # overlaps
                    {'min_amount': 3000, 'max_amount': 2500, 'fee': '40'},     # backwards
                    {'min_amount': 0, 'max_amount': 10, 'fee': '1'},
                    {'min_amount': 3000, 'max_amount': 3500, 'fee': '-1'},
                    {'min_amount': 'a', 'max_amount': 3500, 'fee': '1'}):
            with self.subTest(bad=bad):
                self.assertEqual(post('/api/owner/fee-rules/', bad, format='json').status_code, 400)
        url = f"/api/owner/fee-rules/{made.data['id']}/"
        self.assertEqual(self.owner_api.patch(url, {'fee': '35'}, format='json').data['fee'], '35.00')
        self.assertEqual(self.owner_api.delete(url).status_code, 204)
        self.assertIsNone(self.api.get('/api/ewallet/quote/', {'amount': 1500}).data['fee'])
        self.assertEqual(self.api.get('/api/owner/fee-rules/').status_code, 403)

    def test_changing_the_table_does_not_rewrite_history(self):
        self.go('cash-in', 500)
        FeeRule.objects.filter(min_amount=1).update(fee=Decimal('99'))
        self.assertEqual(EWalletTransaction.objects.get().fee, Decimal('10.00'))

    def test_top_ups_go_to_the_right_wallet(self):
        self.assertEqual(self.balance(), Decimal('2000'))
        self.assertEqual(Wallet.objects.filter(type='load', balance__gt=0).count(), 0)
        set_cashier_can_topup(True, None)
        response = self.api.post('/api/wallets/topup/?kind=ewallet', {
            'amount_added': '300', 'amount_paid': '300', 'source': 'drawer'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('balance', response.data)
        self.assertEqual(self.balance(), Decimal('2300'))
        self.assertEqual(CashMovement.objects.get().reason, 'GCash top-up')
        self.assertEqual(self.api.post('/api/wallets/topup/?kind=lottery', {
            'amount_added': '1', 'amount_paid': '1', 'source': 'drawer'}, format='json').status_code, 400)

    def test_the_owner_wallet_view_for_gcash(self):
        data = self.owner_api.get('/api/owner/wallet/?kind=ewallet').data
        self.assertEqual((data['wallet']['provider'], data['wallet']['balance']), ('GCash', '2000.00'))

    def test_the_seed_command_is_safe_to_run_twice(self):
        FeeRule.objects.all().delete()
        call_command('seed_gcash_example', stdout=StringIO())
        call_command('seed_gcash_example', stdout=StringIO())
        self.assertEqual(FeeRule.objects.count(), 10)
        last = FeeRule.objects.order_by('min_amount').last()
        self.assertEqual((last.min_amount, last.max_amount, last.fee), (4501, 5000, Decimal('100')))


class GcashReportAndIntegrityTests(GcashBase):
    def test_the_cashier_copy_has_no_fees_and_the_owner_copy_does(self):
        self.go('cash-in', 500)
        self.go('cash-out', 200)
        self.go('cash-in', 600, fee_override='15', override_reason='Regular customer')
        self.reverse(self.go('cash-in', 100).data['tx_id'], 'Cancelled')
        closed = self.end('1000')
        self.assertIsNotNone(closed.data['report'])
        shift = Shift.objects.get()
        cashier_copy = build_report_data(shift, owner=False, report_no='X')
        owner_copy = build_report_data(shift, owner=True, report_no='X')
        text = str(cashier_copy).lower()
        for secret in ('fee', 'rebate', 'profit', 'cost', 'margin', 'override'):
            self.assertNotIn(secret, text)
        self.assertEqual({r['label']: r['count'] for r in cashier_copy['ewallet_rows']}, {'Cash in': 2, 'Cash out': 1})
        self.assertEqual(len(cashier_copy['ewallet_reversed']), 1)
        self.assertEqual(owner_copy['fee_income'], Decimal('35'))           # 10 + 10 + 15
        self.assertEqual(owner_copy['fee_overrides'][0]['reason'], 'Regular customer')

    def test_the_books_add_up_and_tampering_is_caught(self):
        self.go('cash-in', 500)
        self.reverse(self.go('cash-out', 200).data['tx_id'])
        self.assertIn('OK', self.run_check())
        Wallet.objects.filter(type='ewallet').update(balance=Decimal('1.00'))
        with self.assertRaises(CommandError):
            self.run_check()

    def test_a_changed_fee_note_is_caught(self):
        self.go('cash-in', 600, fee_override='15', override_reason='Regular customer')
        EWalletTransaction.objects.update(fee_override_reason='')
        with self.assertRaises(CommandError):
            self.run_check()