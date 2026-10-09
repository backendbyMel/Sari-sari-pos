from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from config.testkit import client_for, fund_wallet, make_cashier, make_load, make_owner, open_shift
from core.services import set_cashier_can_topup
from sales.models import Receipt
from shifts.models import CashMovement, Shift
from shifts.reports import build_report_data
from wallets.models import LoadNetwork, LoadProduct, LoadTransaction, Wallet, WalletTransaction


class LoadBase(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.cashier = make_cashier()
        self.shift = open_shift(self.cashier, '1000.00')
        self.api = client_for(self.cashier)
        self.owner_api = client_for(self.owner)
        self.network, self.product = make_load()
        fund_wallet(self.owner, '1000')
        self.n = 0

    def send(self, mobile='0917 123 4567', reference=None, product=None, api=None):
        if reference is None:
            self.n += 1
            reference = f'REF{self.n:05d}'
        return (api or self.api).post('/api/load/send/', {
            'product': (product or self.product).id, 'mobile_no': mobile, 'reference_no': reference}, format='json')

    def balance(self):
        return Wallet.objects.get(type='load').balance

    def fail(self, load_id, note='Provider error', api=None):
        return (api or self.api).post(f'/api/load/{load_id}/fail/', {'note': note}, format='json')

    def end(self, counted):
        return self.api.post('/api/shifts/end/', {'counted_cash': counted}, format='json')


class SellLoadTests(LoadBase):
    def test_selling_a_load(self):
        response = self.send()
        self.assertEqual(response.status_code, 201)
        receipt = response.data['receipt']
        self.assertEqual((receipt['kind'], receipt['total'], receipt['receipt_no']), ('load', '52.00', 'SR-000001'))
        self.assertEqual(receipt['load']['mobile'], '0917***4567')
        self.assertEqual(self.balance(), Decimal('950'))
        tx = LoadTransaction.objects.get()
        self.assertEqual((tx.amount, tx.price_charged, tx.rebate, tx.status), (Decimal('50'), Decimal('52'), Decimal('2'), 'success'))
        self.assertEqual((tx.shift, tx.cashier, tx.mobile_no), (self.shift, self.cashier, '09171234567'))
        entry = WalletTransaction.objects.get(type='load_sent')
        self.assertEqual((entry.amount, entry.balance_after, entry.user), (Decimal('-50'), Decimal('950'), self.cashier))
        self.assertEqual(Receipt.objects.get(receipt_no='SR-000001').source, 'load')

    def test_mobile_number_formats(self):
        for number in ('09171234567', '+639171234567', '639171234567', '0917-123-4567'):
            with self.subTest(number=number):
                self.assertEqual(self.send(number).status_code, 201)
        self.assertEqual({t.mobile_no for t in LoadTransaction.objects.all()}, {'09171234567'})
        for bad in ('12345', '0817 123 4567', '091712345678', 'abc', ''):
            with self.subTest(bad=bad):
                self.assertEqual(self.send(bad).status_code, 400)

    def test_reference_rules(self):
        for bad in ('', 'ab', 'a b c d', 'x' * 31, 'ab#12'):
            with self.subTest(reference=bad):
                self.assertEqual(self.send(reference=bad).status_code, 400)
        self.assertEqual(self.send(reference='abc12345').status_code, 201)
        self.assertEqual(self.send(reference='ABC12345').status_code, 400)       # same reference, other case
        self.assertEqual(LoadTransaction.objects.get().reference_no, 'ABC12345')
        self.assertEqual(self.balance(), Decimal('950'))                           # the refused one changed nothing

    def test_the_same_reference_is_fine_on_another_network(self):
        globe = LoadNetwork.objects.create(name='Globe')
        other = LoadProduct.objects.create(network=globe, name='Load 50', face_value=Decimal('50'), selling_price=Decimal('50'))
        self.assertEqual(self.send(reference='SAME1234').status_code, 201)
        self.assertEqual(self.send(reference='SAME1234', product=other).status_code, 201)

    def test_a_shift_is_required(self):
        outsider = client_for(make_cashier('cash2'))
        self.assertEqual(self.send(api=outsider).status_code, 400)
        self.assertEqual(LoadTransaction.objects.count(), 0)

    def test_inactive_products_and_networks_cannot_be_sold(self):
        LoadProduct.objects.filter(pk=self.product.pk).update(is_active=False)
        self.assertEqual(self.send().status_code, 400)
        LoadProduct.objects.filter(pk=self.product.pk).update(is_active=True)
        LoadNetwork.objects.filter(pk=self.network.pk).update(is_active=False)
        self.assertEqual(self.send().status_code, 400)
        self.assertEqual(self.send(product=type('P', (), {'id': 999999})()).status_code, 400)

    def test_prices_sent_by_the_browser_are_ignored(self):
        response = self.api.post('/api/load/send/', {
            'product': self.product.id, 'mobile_no': '09171234567', 'reference_no': 'REF99999',
            'price': '1', 'amount': '1', 'rebate': '99', 'price_charged': '1'}, format='json')
        self.assertEqual(response.data['receipt']['total'], '52.00')
        self.assertEqual(self.balance(), Decimal('950'))
        self.assertEqual(LoadTransaction.objects.get().rebate, Decimal('2.00'))

    def test_a_low_wallet_warns_without_revealing_the_balance(self):
        WalletTransaction.objects.all()   # (balance is 1000; take most of it out through an adjustment)
        self.owner_api.post('/api/owner/wallet/adjust/', {'actual_balance': '30', 'reason': 'Counted'}, format='json')
        response = self.send()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data['warnings']), 1)
        self.assertFalse(any(ch.isdigit() for ch in response.data['warnings'][0]))
        self.assertEqual(self.balance(), Decimal('-20'))

    def test_cashiers_never_see_rebates_or_amounts_taken_from_the_wallet(self):
        responses = [self.api.get('/api/load/products/'), self.send(), self.api.get('/api/load/mine/')]
        for response in responses:
            text = response.content.decode().lower()
            for secret in ('rebate', 'profit', 'cost', 'face', 'balance'):
                self.assertNotIn(secret, text)

    def test_the_catalog_lists_only_active_products(self):
        LoadProduct.objects.create(network=self.network, name='EZ50', face_value=Decimal('50'),
                                   selling_price=Decimal('55'), is_active=False)
        names = [p['name'] for n in self.api.get('/api/load/products/').data for p in n['products']]
        self.assertEqual(names, ['Load 50'])

    def test_receipts_can_be_viewed_reprinted_and_listed(self):
        number = self.send().data['receipt']['receipt_no']
        self.assertEqual(self.api.get(f'/api/receipts/{number}/').data['kind'], 'load')
        self.assertTrue(self.api.post(f'/api/receipts/{number}/reprint/').data['is_copy'])
        row = self.api.get('/api/sales/recent/').data[0]
        self.assertEqual((row['kind'], row['total']), ('load', '52.00'))


class FailedLoadTests(LoadBase):
    def test_a_failed_load_restores_the_wallet_and_leaves_a_trail(self):
        load_id = self.send().data['load_id']
        response = self.fail(load_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['refund'], '52.00')
        self.assertTrue(response.data['receipt']['is_failed'])
        self.assertEqual(self.balance(), Decimal('1000'))
        tx = LoadTransaction.objects.get()
        self.assertEqual((tx.status, tx.failed_note), ('failed', 'Provider error'))
        entry = WalletTransaction.objects.get(type='reversal')
        self.assertEqual((entry.amount, entry.balance_after), (Decimal('50'), Decimal('1000')))
        self.assertTrue(self.api.get(f'/api/receipts/{tx.receipt_no}/').data['is_failed'])

    def test_a_note_is_required_and_a_load_fails_only_once(self):
        load_id = self.send().data['load_id']
        for note in ('', '   '):
            self.assertEqual(self.fail(load_id, note).status_code, 400)
        self.assertEqual(self.api.post(f'/api/load/{load_id}/fail/', {}, format='json').status_code, 400)
        self.assertEqual(self.fail(load_id).status_code, 200)
        self.assertEqual(self.fail(load_id).status_code, 400)
        self.assertEqual(self.balance(), Decimal('1000'))
        self.assertEqual(self.fail(999999).status_code, 404)

    def test_only_the_cashier_of_that_open_shift_can_fail_it(self):
        load_id = self.send().data['load_id']
        self.assertEqual(self.fail(load_id, api=client_for(make_cashier('cash2'))).status_code, 400)
        self.assertEqual(self.fail(load_id, api=self.owner_api).status_code, 400)
        self.assertEqual(self.balance(), Decimal('950'))

    def test_a_load_from_a_closed_shift_cannot_be_failed_here(self):
        load_id = self.send().data['load_id']
        self.end('1052')
        open_shift(self.cashier, '1052')
        self.assertEqual(self.fail(load_id).status_code, 400)
        self.assertEqual(self.balance(), Decimal('950'))

    def test_a_failed_load_is_final(self):
        load_id = self.send().data['load_id']
        self.fail(load_id)
        tx = LoadTransaction.objects.get()
        tx.failed_note = 'changed'
        with self.assertRaises(PermissionError):
            tx.save()
        with self.assertRaises(PermissionError):
            tx.delete()


class LoadCashTests(LoadBase):
    def test_load_cash_is_expected_in_the_drawer(self):
        self.send()
        closed = self.end('1052')
        self.assertEqual(Decimal(closed.data['shift']['expected_cash']), Decimal('1052'))
        self.assertEqual(Decimal(closed.data['shift']['variance']), 0)
        self.assertEqual((closed.data['load_sales'], closed.data['load_count']), ('52.00', 1))

    def test_a_failed_load_adds_no_expected_cash(self):
        self.send()
        self.fail(LoadTransaction.objects.get().pk)
        closed = self.end('1000')
        self.assertEqual(Decimal(closed.data['shift']['expected_cash']), Decimal('1000'))
        self.assertEqual(Decimal(closed.data['shift']['variance']), 0)
        self.assertEqual(closed.data['load_failed_count'], 1)

    def test_the_summary_shows_load_sales_and_no_wallet_balance(self):
        self.send()
        data = self.api.get('/api/shifts/summary/').data
        self.assertEqual((data['load_sales'], data['load_count']), ('52.00', 1))
        self.assertNotIn('wallet', str(data).lower())


class TopUpTests(LoadBase):
    URL = '/api/wallets/topup/'

    def topup(self, api=None, added='500', paid='500', source='owner_cash', reference=''):
        return (api or self.owner_api).post(self.URL, {
            'amount_added': added, 'amount_paid': paid, 'source': source, 'reference_no': reference}, format='json')

    def test_the_owner_tops_up_with_his_own_money(self):
        response = self.topup(reference='GCASH-123')
        self.assertEqual((response.status_code, response.data['balance']), (201, '1500.00'))
        entry = WalletTransaction.objects.filter(type='topup').latest('id')
        self.assertEqual((entry.source, entry.amount_paid, entry.reference_no), ('owner_cash', Decimal('500'), 'GCASH-123'))
        self.assertEqual(CashMovement.objects.count(), 0)

    def test_the_wallet_can_get_more_than_was_paid(self):
        self.topup(added='1000', paid='960', source='bank')
        self.assertEqual(self.balance(), Decimal('2000'))
        self.assertEqual(WalletTransaction.objects.filter(type='topup').latest('id').amount_paid, Decimal('960'))

    def test_cashiers_are_blocked_unless_the_owner_allows_it(self):
        response = self.topup(api=self.api, source='drawer')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.balance(), Decimal('1000'))
        self.assertEqual(CashMovement.objects.count(), 0)

    def test_an_allowed_cashier_can_top_up_only_from_the_drawer_and_it_is_a_payout(self):
        set_cashier_can_topup(True, None)
        self.assertEqual(self.topup(api=self.api, source='bank').status_code, 403)
        self.assertEqual(self.topup(api=self.api, source='owner_cash').status_code, 403)
        response = self.topup(api=self.api, added='300', paid='300', source='drawer')
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('balance', response.data)
        self.assertEqual(self.balance(), Decimal('1300'))
        movement = CashMovement.objects.get()
        self.assertEqual((movement.type, movement.amount, movement.recorded_by, movement.shift),
                         ('out', Decimal('300'), self.cashier, self.shift))
        entry = WalletTransaction.objects.filter(type='topup').latest('id')
        self.assertEqual((entry.shift, entry.source), (self.shift, 'drawer'))
        closed = self.end('700')                         # 1000 - 300 taken out
        self.assertEqual(Decimal(closed.data['shift']['variance']), 0)

    def test_a_drawer_top_up_needs_an_open_shift(self):
        before = WalletTransaction.objects.count()
        response = self.topup(api=self.owner_api, source='drawer')   # the owner has no shift
        self.assertEqual(response.status_code, 400)
        self.assertEqual(WalletTransaction.objects.count(), before)
        self.assertEqual(self.balance(), Decimal('1000'))

    def test_bad_top_ups(self):
        for body in ({'added': '0'}, {'added': '-5'}, {'added': 'abc'}, {'paid': '-1'},
                     {'source': 'drawer', 'paid': '0'}, {'source': 'lottery'}):
            with self.subTest(body=body):
                self.assertEqual(self.topup(**body).status_code, 400)
        self.assertEqual(self.balance(), Decimal('1000'))


class WalletOwnerTests(LoadBase):
    def test_the_owner_corrects_the_balance_and_it_is_recorded(self):
        response = self.owner_api.post('/api/owner/wallet/adjust/',
                                       {'actual_balance': '940', 'reason': 'Counted in the app'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.balance(), Decimal('940'))
        entry = WalletTransaction.objects.filter(type='adjustment').get()
        self.assertEqual((entry.amount, entry.note, entry.user), (Decimal('-60'), 'Counted in the app', self.owner))

    def test_bad_adjustments(self):
        for body in ({'actual_balance': '1000', 'reason': 'same'}, {'actual_balance': '900', 'reason': ''},
                     {'actual_balance': '900'}, {'actual_balance': '-5', 'reason': 'x'}):
            with self.subTest(body=body):
                self.assertEqual(self.owner_api.post('/api/owner/wallet/adjust/', body, format='json').status_code, 400)
        self.assertEqual(self.api.post('/api/owner/wallet/adjust/', {'actual_balance': '1', 'reason': 'x'}, format='json').status_code, 403)
        self.assertEqual(self.balance(), Decimal('1000'))

    def test_the_wallet_view_and_the_low_level(self):
        data = self.owner_api.get('/api/owner/wallet/').data
        self.assertEqual((data['wallet']['balance'], data['wallet']['is_low']), ('1000.00', False))
        self.owner_api.patch('/api/owner/wallet/', {'low_level': '2000'}, format='json')
        self.assertTrue(self.owner_api.get('/api/owner/wallet/').data['wallet']['is_low'])
        self.assertEqual(self.owner_api.patch('/api/owner/wallet/', {'low_level': '-1'}, format='json').status_code, 400)

    def test_wallet_entries_are_append_only(self):
        entry = WalletTransaction.objects.get()
        with self.assertRaises(PermissionError):
            entry.delete()
        entry.amount = Decimal('1')
        with self.assertRaises(PermissionError):
            entry.save()
        with self.assertRaises(PermissionError):
            Wallet.objects.get().delete()


class SetupTests(LoadBase):
    def test_the_owner_manages_networks_and_products(self):
        made = self.owner_api.post('/api/owner/load-networks/', {'name': 'Globe', 'rebate_percent': '3.50'}, format='json')
        self.assertEqual(made.status_code, 201)
        product = self.owner_api.post('/api/owner/load-products/', {
            'network': made.data['id'], 'name': 'GoSURF50', 'face_value': '50', 'selling_price': '55'}, format='json')
        self.assertEqual(product.status_code, 201)
        self.assertEqual(self.owner_api.patch(f"/api/owner/load-products/{product.data['id']}/",
                                              {'selling_price': '56'}, format='json').data['selling_price'], '56.00')
        self.assertEqual(self.owner_api.patch(f"/api/owner/load-networks/{made.data['id']}/",
                                              {'rebate_percent': '4'}, format='json').status_code, 200)

    def test_bad_setups_are_refused(self):
        post = self.owner_api.post
        self.assertEqual(post('/api/owner/load-networks/', {'name': 'Smart', 'rebate_percent': '1'}, format='json').status_code, 400)
        self.assertEqual(post('/api/owner/load-networks/', {'name': 'X', 'rebate_percent': '101'}, format='json').status_code, 400)
        self.assertEqual(post('/api/owner/load-networks/', {'name': 'X', 'rebate_percent': '-1'}, format='json').status_code, 400)
        base = {'network': self.network.id, 'face_value': '50', 'selling_price': '55'}
        self.assertEqual(post('/api/owner/load-products/', {**base, 'name': 'Load 50'}, format='json').status_code, 400)
        self.assertEqual(post('/api/owner/load-products/', {**base, 'name': 'A', 'face_value': '0'}, format='json').status_code, 400)
        self.assertEqual(post('/api/owner/load-products/', {**base, 'name': 'A', 'selling_price': '-1'}, format='json').status_code, 400)

    def test_a_product_cannot_change_network_and_nothing_is_deleted(self):
        other = LoadNetwork.objects.create(name='Globe')
        url = f'/api/owner/load-products/{self.product.id}/'
        self.assertEqual(self.owner_api.patch(url, {'network': other.id}, format='json').status_code, 400)
        self.assertEqual(self.owner_api.delete(url).status_code, 405)
        self.assertEqual(self.owner_api.delete(f'/api/owner/load-networks/{self.network.id}/').status_code, 405)

    def test_changing_a_price_does_not_rewrite_history(self):
        self.send()
        self.owner_api.patch(f'/api/owner/load-products/{self.product.id}/', {'selling_price': '60'}, format='json')
        self.owner_api.patch(f'/api/owner/load-networks/{self.network.id}/', {'rebate_percent': '10'}, format='json')
        tx = LoadTransaction.objects.get()
        self.assertEqual((tx.price_charged, tx.rebate), (Decimal('52.00'), Decimal('2.00')))

    def test_cashiers_cannot_use_the_owner_setup(self):
        self.assertEqual(self.api.get('/api/owner/load-networks/').status_code, 403)
        self.assertEqual(self.api.patch(f'/api/owner/load-products/{self.product.id}/',
                                        {'selling_price': '1'}, format='json').status_code, 403)
        self.assertEqual(self.api.patch('/api/owner/wallet/', {'low_level': '1'}, format='json').status_code, 403)

    def test_the_seed_command_is_safe_to_run_twice(self):
        call_command('seed_load_examples', stdout=StringIO())
        call_command('seed_load_examples', stdout=StringIO())
        self.assertEqual(LoadNetwork.objects.count(), 3)
        self.assertEqual(LoadProduct.objects.filter(network__name='Globe').count(), 4)


class LoadReportAndIntegrityTests(LoadBase):
    def run_check(self):
        out = StringIO()
        call_command('check_integrity', stdout=out)
        return out.getvalue()

    def test_the_report_lists_loads_and_hides_rebates_from_the_cashier_copy(self):
        self.send()
        failed = self.send().data['load_id']
        self.fail(failed, 'Provider error')
        closed = self.end('1052')
        self.assertIsNotNone(closed.data['report'])
        shift = Shift.objects.get()
        cashier_copy = build_report_data(shift, owner=False, report_no='X')
        owner_copy = build_report_data(shift, owner=True, report_no='X')
        self.assertEqual(cashier_copy['load_sales'], Decimal('52'))
        self.assertEqual((cashier_copy['load_rows'][0]['network'], cashier_copy['load_rows'][0]['count']), ('Smart', 1))
        self.assertEqual(cashier_copy['load_failed'][0]['note'], 'Provider error')
        self.assertEqual(cashier_copy['load_failed'][0]['mobile'], '0917***4567')
        text = str(cashier_copy).lower()
        for secret in ('rebate', 'profit', 'cost', 'margin'):
            self.assertNotIn(secret, text)
        self.assertEqual(owner_copy['load_profit'], Decimal('4'))     

    def test_the_books_add_up_and_tampering_is_caught(self):
        self.send()
        self.fail(self.send().data['load_id'])
        self.assertIn('OK', self.run_check())
        Wallet.objects.filter(type='load').update(balance=Decimal('1.00'))
        with self.assertRaises(CommandError):
            self.run_check()

    def test_a_missing_load_receipt_is_caught(self):
        self.send()
        Receipt.objects.filter(source='load').delete()
        with self.assertRaises(CommandError):
            self.run_check()