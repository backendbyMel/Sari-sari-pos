from decimal import Decimal

from django.test import TestCase

from config.testkit import client_for, make_candy, make_cashier, make_marlboro, make_owner
from inventory.models import ProductUnit, StockMovement

# Create your tests here.
class RestockTests(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.api = client_for(self.owner)
        self.marlboro, self.stick, self.pack = make_marlboro()   # 400 sticks at P8.00

    def restock(self, unit, qty, cost, **extra):
        body = {
            'product': self.marlboro.id, 'product_unit': unit.id,
            'quantity': qty, 'unit_cost': cost,
        }
        body.update(extra)
        return self.api.post('/api/restocks/', body, format='json')

    def test_packs_become_sticks_and_cost_is_averaged(self):
        response = self.restock(self.pack, '10', '173.40', delivery_receipt_no='DR-1001')
        self.assertEqual(response.status_code, 201)
        self.marlboro.refresh_from_db()
        self.assertEqual(self.marlboro.stock_qty, Decimal('600'))             # 400 + 10 x 20
        # (400 x 8.00 + 200 x 8.67) / 600 = 8.2233
        self.assertEqual(self.marlboro.cost_price, Decimal('8.2233'))

    def test_restock_writes_a_history_line(self):
        self.restock(self.pack, '10', '173.40')
        movement = StockMovement.objects.get()
        self.assertEqual(movement.type, 'restock')
        self.assertEqual(movement.quantity, Decimal('200'))
        self.assertEqual(movement.balance_after, Decimal('600'))
        self.assertEqual(movement.user, self.owner)

    def test_margin_warning_when_cost_rises(self):
        response = self.restock(self.pack, '10', '220')   
        self.assertEqual(len(response.data['warnings']), 1)
        self.assertIn('Margin dropped', response.data['warnings'][0])

    def test_no_warning_when_cost_falls(self):
        response = self.restock(self.pack, '10', '140')   
        self.assertEqual(response.data['warnings'], [])

    def test_unit_of_another_product_refused(self):
        _, candy_unit = make_candy()
        response = self.restock(candy_unit, '1', '1')
        self.assertEqual(response.status_code, 400)
        self.marlboro.refresh_from_db()
        self.assertEqual(self.marlboro.stock_qty, Decimal('400'))

    def test_bad_numbers_refused(self):
        for qty in ('-5', '0'):
            with self.subTest(quantity=qty):
                self.assertEqual(self.restock(self.pack, qty, '100').status_code, 400)

    def test_inactive_product_refused(self):
        self.marlboro.is_active = False
        self.marlboro.save()
        self.assertEqual(self.restock(self.pack, '1', '100').status_code, 400)


class AdjustmentTests(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.api = client_for(self.owner)
        self.marlboro, _, _ = make_marlboro()

    def adjust(self, qty, reason='damaged', **extra):
        body = {'product': self.marlboro.id, 'quantity': qty,
                'reason_type': reason, 'note': 'test note'}
        body.update(extra)
        return self.api.post('/api/stock-adjustments/', body, format='json')

    def test_damage_reduces_stock_and_is_logged(self):
        response = self.adjust('-5', note='Pack fell in water')
        self.assertEqual(response.status_code, 201)
        self.marlboro.refresh_from_db()
        self.assertEqual(self.marlboro.stock_qty, Decimal('395'))
        movement = StockMovement.objects.get()
        self.assertEqual(movement.quantity, Decimal('-5'))
        self.assertEqual(movement.reason, 'Damaged: Pack fell in water')
        self.assertEqual(movement.user, self.owner)

    def test_a_loss_can_never_add_stock(self):
        for reason in ('damaged', 'expired', 'stolen'):
            with self.subTest(reason=reason):
                self.assertEqual(self.adjust('5', reason=reason).status_code, 400)
        self.marlboro.refresh_from_db()
        self.assertEqual(self.marlboro.stock_qty, Decimal('400'))

    def test_stock_cannot_go_negative(self):
        self.assertEqual(self.adjust('-99999', reason='count_error').status_code, 400)
        self.marlboro.refresh_from_db()
        self.assertEqual(self.marlboro.stock_qty, Decimal('400'))

    def test_a_note_is_required(self):
        self.assertEqual(self.adjust('-1', note='').status_code, 400)
        body = {'product': self.marlboro.id, 'quantity': '-1', 'reason_type': 'damaged'}
        self.assertEqual(self.api.post('/api/stock-adjustments/', body, format='json').status_code, 400)

    def test_unknown_reason_and_zero_loss_refused(self):
        self.assertEqual(self.adjust('-1', reason='lost').status_code, 400)
        self.assertEqual(self.adjust('0', reason='damaged').status_code, 400)

    def test_recount_of_zero_clears_the_flag(self):
        self.marlboro.needs_recount = True
        self.marlboro.save()
        self.assertEqual(self.adjust('0', reason='count_error').status_code, 201)
        self.marlboro.refresh_from_db()
        self.assertFalse(self.marlboro.needs_recount)


class HistoryTests(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.api = client_for(self.owner)
        self.marlboro, _, self.pack = make_marlboro()

    def test_history_lines_cannot_be_edited_or_deleted(self):
        movement = StockMovement.objects.create(
            product=self.marlboro, type='adjustment', quantity=Decimal('-1'),
            balance_after=Decimal('399'), user=self.owner, reason='x',
        )
        movement.quantity = Decimal('-2')
        with self.assertRaises(PermissionError):
            movement.save()
        with self.assertRaises(PermissionError):
            movement.delete()

    def test_the_history_adds_up(self):
        self.api.post('/api/restocks/', {
            'product': self.marlboro.id, 'product_unit': self.pack.id,
            'quantity': '10', 'unit_cost': '173.40'}, format='json')
        self.api.post('/api/stock-adjustments/', {
            'product': self.marlboro.id, 'quantity': '-5',
            'reason_type': 'damaged', 'note': 'x'}, format='json')
        running = Decimal('400')
        for movement in StockMovement.objects.order_by('id'):
            running += movement.quantity
            self.assertEqual(running, movement.balance_after)
        self.marlboro.refresh_from_db()
        self.assertEqual(running, self.marlboro.stock_qty)

    def test_history_is_read_only_through_the_api(self):
        self.assertEqual(self.api.post('/api/stock-movements/', {}, format='json').status_code, 405)


class ProductApiTests(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.api = client_for(self.owner)
        self.marlboro, self.stick, self.pack = make_marlboro()

    def test_products_and_units_cannot_be_deleted(self):
        for url in (f'/api/products/{self.marlboro.id}/', f'/api/units/{self.stick.id}/'):
            with self.subTest(url=url):
                self.assertEqual(self.api.delete(url).status_code, 405)

    def test_new_product_starts_with_zero_stock(self):
        response = self.api.post('/api/products/', {'name': 'Piattos', 'base_unit': 'pack'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Decimal(response.data['stock_qty']), 0)

    def test_stock_cannot_be_typed_through_the_api(self):
        response = self.api.patch(
            f'/api/products/{self.marlboro.id}/', {'stock_qty': '999'}, format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.marlboro.refresh_from_db()
        self.assertEqual(self.marlboro.stock_qty, Decimal('400'))

    def test_duplicate_barcode_refused(self):
        response = self.api.post('/api/units/', {
            'product': self.marlboro.id, 'unit_name': 'case', 'pieces_per_unit': '24',
            'barcode': '4800000000011', 'selling_price': '480.00'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_empty_barcodes_are_stored_as_nothing(self):
        for name, pieces in (('box', '200'), ('carton', '2000')):
            response = self.api.post('/api/units/', {
                'product': self.marlboro.id, 'unit_name': name, 'pieces_per_unit': pieces,
                'barcode': '', 'selling_price': '100.00'}, format='json')
            self.assertEqual(response.status_code, 201)
        
        self.assertEqual(ProductUnit.objects.filter(barcode__isnull=True).count(), 3)

    def test_negative_price_refused(self):
        response = self.api.post('/api/units/', {
            'product': self.marlboro.id, 'unit_name': 'case', 'pieces_per_unit': '24',
            'selling_price': '-5'}, format='json')
        self.assertEqual(response.status_code, 400)


class LookupTests(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.cashier_api = client_for(make_cashier())
        self.marlboro, _, _ = make_marlboro()
        make_candy()

    def test_cashier_never_sees_cost(self):
        text = self.cashier_api.get('/api/products/lookup/', {'code': '4800000000011'}).content.decode().lower()
        self.assertIn('marlboro', text)
        self.assertNotIn('cost', text)

    def test_owner_does_see_cost(self):
        text = client_for(self.owner).get('/api/products/').content.decode()
        self.assertIn('cost_price', text)

    def test_find_by_barcode_by_name_and_unknown(self):
        self.assertEqual(self.cashier_api.get('/api/products/lookup/', {'code': '4800000000200'}).status_code, 200)
        self.assertEqual(self.cashier_api.get('/api/products/lookup/', {'code': 'marl'}).status_code, 200)
        self.assertEqual(self.cashier_api.get('/api/products/lookup/', {'code': '0000'}).status_code, 404)

    def test_inactive_products_are_not_found(self):
        self.marlboro.is_active = False
        self.marlboro.save()
        self.assertEqual(self.cashier_api.get('/api/products/lookup/', {'code': '4800000000011'}).status_code, 404)