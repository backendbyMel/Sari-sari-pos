from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from config.testkit import client_for, make_candy, make_cashier, make_marlboro, make_owner
from inventory.models import PriceTier, StockMovement
from sales.models import Receipt, Sale, SaleItem
from sales.services import create_sale, price_line

# Create your tests here.
class PriceLineTests(TestCase):
    def setUp(self):
        _, self.piece = make_candy()   # P1 each, 3 for P2

    def test_tingi_deal(self):
        expected = {'1': '1.00', '2': '2.00', '3': '2.00', '4': '3.00',
                    '5': '4.00', '6': '4.00', '7': '5.00'}
        for qty, total in expected.items():
            with self.subTest(quantity=qty):
                self.assertEqual(price_line(self.piece, Decimal(qty)), Decimal(total))

    def test_larger_bundles_are_applied_first(self):
        PriceTier.objects.create(product_unit=self.piece, min_qty=Decimal('10'), price=Decimal('5.00'))
        # 10 for P5, plus 2 loose at P1 = P7
        self.assertEqual(price_line(self.piece, Decimal('12')), Decimal('7.00'))


class SaleTests(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.cashier = make_cashier()
        self.api = client_for(self.cashier)
        self.marlboro, self.stick, self.pack = make_marlboro()   # cost P8 per stick
        self.candy, self.piece = make_candy()

    def sell(self, items, cash):
        return self.api.post('/api/sales/', {'items': items, 'cash_received': cash}, format='json')

    def line(self, unit, qty):
        return {'product_unit': unit.id, 'quantity': qty}

    def test_a_pack_deducts_twenty_sticks(self):
        response = self.sell([self.line(self.pack, '1')], '200')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Decimal(response.data['receipt']['total']), Decimal('190'))
        self.assertEqual(Decimal(response.data['receipt']['change']), Decimal('10'))
        self.marlboro.refresh_from_db()
        self.assertEqual(self.marlboro.stock_qty, Decimal('380'))
        movement = StockMovement.objects.get()
        self.assertEqual(movement.quantity, Decimal('-20'))
        self.assertEqual(movement.balance_after, Decimal('380'))
        self.assertEqual(movement.user, self.cashier)
        self.assertEqual(movement.reason, 'Sale SR-000001')

    def test_tingi_deal_on_the_server(self):
        response = self.sell([self.line(self.piece, '7')], '10')
        self.assertEqual(Decimal(response.data['receipt']['total']), Decimal('5'))
        self.assertEqual(Decimal(response.data['receipt']['change']), Decimal('5'))

    def test_mixed_basket(self):
        response = self.sell(
            [self.line(self.pack, '1'), self.line(self.stick, '3'), self.line(self.piece, '2')], '500'
        )
        self.assertEqual(Decimal(response.data['receipt']['total']), Decimal('222'))
        self.assertEqual(Decimal(response.data['receipt']['change']), Decimal('278'))

    def test_repeated_lines_are_merged_before_pricing(self):
        response = self.sell([self.line(self.piece, '2'), self.line(self.piece, '2')], '5')
        self.assertEqual(Decimal(response.data['receipt']['total']), Decimal('3'))   # 4 = 3 for P2 + 1
        self.assertEqual(SaleItem.objects.count(), 1)

    def test_cash_below_total_is_refused_and_nothing_is_saved(self):
        response = self.sell([self.line(self.piece, '7')], '4')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(Receipt.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)
        self.candy.refresh_from_db()
        self.assertEqual(self.candy.stock_qty, Decimal('100'))

    def test_refused_sales_do_not_use_up_receipt_numbers(self):
        self.sell([self.line(self.piece, '7')], '4')      # refused
        first = self.sell([self.line(self.piece, '1')], '5')
        second = self.sell([self.line(self.piece, '1')], '5')
        self.assertEqual(first.data['receipt']['receipt_no'], 'SR-000001')
        self.assertEqual(second.data['receipt']['receipt_no'], 'SR-000002')

    def test_prices_sent_by_the_browser_are_ignored(self):
        item = {'product_unit': self.piece.id, 'quantity': '1', 'unit_price': '0.01', 'line_total': '0.01'}
        response = self.sell([item], '5')
        self.assertEqual(Decimal(response.data['receipt']['total']), Decimal('1'))

    def test_bad_requests_are_refused(self):
        bad = {
            'empty basket': [],
            'unknown unit': [self.line(self.piece, '1') | {'product_unit': 999999}],
            'negative quantity': [self.line(self.piece, '-1')],
        }
        for name, items in bad.items():
            with self.subTest(case=name):
                self.assertEqual(self.sell(items, '5').status_code, 400)
        utang = self.api.post('/api/sales/', {
            'items': [self.line(self.piece, '1')], 'payment_type': 'utang', 'cash_received': '5'}, format='json')
        self.assertEqual(utang.status_code, 400)   # utang is Phase 3

    def test_negative_stock_warns_but_does_not_block(self):
        self.candy.stock_qty = Decimal('5')
        self.candy.save()
        response = self.sell([self.line(self.piece, '8')], '10')    # 8 pieces cost P6
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data['warnings']), 1)
        self.candy.refresh_from_db()
        self.assertEqual(self.candy.stock_qty, Decimal('-3'))
        self.assertTrue(self.candy.needs_recount)

    def test_inactive_product_cannot_be_sold(self):
        self.marlboro.is_active = False
        self.marlboro.save()
        self.assertEqual(self.sell([self.line(self.pack, '1')], '200').status_code, 400)
        self.marlboro.refresh_from_db()
        self.assertEqual(self.marlboro.stock_qty, Decimal('400'))

    def test_price_and_cost_are_snapshots(self):
        self.sell([self.line(self.pack, '1')], '200')
        # The owner raises the price afterwards.
        owner_api = client_for(self.owner)
        owner_api.patch(f'/api/units/{self.pack.id}/', {'selling_price': '300.00'}, format='json')
        item = SaleItem.objects.get()
        self.assertEqual(item.unit_price, Decimal('190.00'))
        self.assertEqual(item.unit_cost, Decimal('160.0000'))    # P8 x 20 sticks
        self.assertEqual(item.line_total, Decimal('190.00'))
        receipt = self.api.get('/api/receipts/SR-000001/')
        self.assertEqual(receipt.data['items'][0]['price'], '190.00')

    def test_receipts_never_show_cost_or_profit(self):
        self.sell([self.line(self.pack, '1')], '200')
        for response in (self.api.get('/api/receipts/SR-000001/'),
                         self.api.post('/api/receipts/SR-000001/reprint/'),
                         self.api.get('/api/sales/recent/')):
            text = response.content.decode().lower()
            self.assertNotIn('cost', text)
            self.assertNotIn('profit', text)

    def test_a_power_cut_in_the_middle_saves_nothing(self):
        crash = patch.object(StockMovement.objects, 'create', side_effect=RuntimeError('power cut'))
        with crash:
            with self.assertRaises(RuntimeError):
                create_sale(
                    cashier=self.cashier, payment_type='cash', cash_received=Decimal('200'),
                    items=[{'product_unit': self.pack.id, 'quantity': Decimal('1')}],
                )
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(SaleItem.objects.count(), 0)
        self.assertEqual(Receipt.objects.count(), 0)
        self.marlboro.refresh_from_db()
        self.assertEqual(self.marlboro.stock_qty, Decimal('400'))
        # Even the receipt number was given back.
        again = self.sell([self.line(self.pack, '1')], '200')
        self.assertEqual(again.data['receipt']['receipt_no'], 'SR-000001')

    def test_sales_cannot_be_deleted(self):
        self.sell([self.line(self.piece, '1')], '5')
        with self.assertRaises(PermissionError):
            Sale.objects.get().delete()


class ReceiptTests(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.cashier = make_cashier()
        self.api = client_for(self.cashier)
        make_candy()
        self.api.post('/api/sales/', {
            'items': [{'product_unit': 1, 'quantity': '1'}], 'cash_received': '5'}, format='json')

    def test_reprint_is_marked_copy_and_logged(self):
        self.assertFalse(self.api.get('/api/receipts/SR-000001/').data['is_copy'])
        first = self.api.post('/api/receipts/SR-000001/reprint/')
        second = client_for(self.owner).post('/api/receipts/SR-000001/reprint/')
        self.assertTrue(first.data['is_copy'])
        self.assertTrue(second.data['is_copy'])
        receipt = Receipt.objects.get(receipt_no='SR-000001')
        self.assertEqual(receipt.printed_count, 2)
        self.assertEqual([entry['user'] for entry in receipt.reprint_log], ['cash', 'boss'])
        # Viewing the original is still not a copy.
        self.assertFalse(self.api.get('/api/receipts/SR-000001/').data['is_copy'])

    def test_unknown_receipt_is_404_and_logs_nothing(self):
        self.assertEqual(self.api.post('/api/receipts/SR-999999/reprint/').status_code, 404)
        self.assertEqual(Receipt.objects.get().printed_count, 0)

    def test_recent_list_has_only_safe_fields(self):
        row = self.api.get('/api/sales/recent/').data[0]
        self.assertEqual(set(row), {'receipt_no', 'cashier', 'total', 'status', 'date_time'})