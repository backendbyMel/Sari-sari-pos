import csv
import io
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from analytics.exports import safe_text
from config.testkit import client_for, make_candy, make_cashier, make_marlboro, make_owner, open_shift
from inventory.models import Category, Product, ProductUnit

REPORTS = '/api/owner/reports/'
EXPORTS = '/api/owner/exports/'
ALL_EXPORTS = ['sales/', 'best-sellers/', 'slow-movers/', 'inventory/', 'shopping-list/']


def table(response):
    return list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))


class StoreBase(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.cashier = make_cashier()
        open_shift(self.cashier, '1000.00')
        self.api = client_for(self.cashier)
        self.owner_api = client_for(self.owner)
        self.marlboro, self.stick, self.pack = make_marlboro()    
        self.candy, self.piece = make_candy()                      

    def sell(self, unit, qty, cash='500'):
        response = self.api.post('/api/sales/', {
            'items': [{'product_unit': unit.id, 'quantity': qty}], 'cash_received': cash}, format='json')
        self.assertEqual(response.status_code, 201, response.data)

    def product(self, name, stock='10', level='0', cost='15', category=None, active=True):
        p = Product.objects.create(
            name=name, base_unit='pack', cost_price=Decimal(cost), stock_qty=Decimal(stock),
            low_stock_level=Decimal(level), category=category, is_active=active)
        ProductUnit.objects.create(product=p, unit_name='pack', pieces_per_unit=Decimal('1'),
                                   selling_price=Decimal('25'))
        return p


class InventoryReportTests(StoreBase):
    def get(self):
        response = self.owner_api.get(REPORTS + 'inventory/')
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_value_is_stock_times_cost_by_category(self):
        Product.objects.filter(pk=self.marlboro.pk).update(category=Category.objects.create(name='Cigarettes'))
        data = self.get()
        self.assertEqual((data['total_value'], data['item_count'], data['negative_count']), ('3250.00', 2, 0))
        self.assertEqual([(c['category'], c['value'], c['items']) for c in data['categories']],
                         [('Cigarettes', '3200.00', 1), ('(no category)', '50.00', 1)])
        marlboro = next(i for i in data['items'] if i['name'] == 'Marlboro Red')
        self.assertEqual((marlboro['stock'], marlboro['cost'], marlboro['value']), ('400', '8.0000', '3200.00'))

    def test_a_sale_lowers_the_value(self):
        self.sell(self.pack, '1')                                   
        self.assertEqual(self.get()['total_value'], '3090.00')   

    def test_negative_stock_counts_as_zero_and_is_flagged(self):
        Product.objects.filter(pk=self.candy.pk).update(stock_qty=Decimal('-5'))
        data = self.get()
        candy = next(i for i in data['items'] if i['name'] == 'Candy Test')
        self.assertEqual((candy['stock'], candy['value'], candy['negative']), ('-5', '0.00', True))
        self.assertEqual((data['total_value'], data['negative_count']), ('3200.00', 1))

    def test_inactive_products_count_only_while_they_hold_stock(self):
        self.product('Retired', stock='4', cost='10', active=False)
        self.product('Gone', stock='0', active=False)
        data = self.get()
        names = {i['name']: i for i in data['items']}
        self.assertNotIn('Gone', names)
        self.assertEqual((names['Retired']['value'], names['Retired']['is_active']), ('40.00', False))
        self.assertEqual(data['total_value'], '3290.00')

    def test_the_total_is_rounded_once(self):
        self.product('Tiny', stock='3', cost='0.3333')             
        data = self.get()
        self.assertEqual(next(i for i in data['items'] if i['name'] == 'Tiny')['value'], '1.00')
        self.assertEqual(data['total_value'], '3251.00')            # 3200 + 50 + 0.9999

    def test_only_the_owner_can_read_it(self):
        self.assertEqual(self.api.get(REPORTS + 'inventory/').status_code, 403)
        self.assertEqual(client_for().get(REPORTS + 'inventory/').status_code, 401)


class ShoppingListTests(StoreBase):
    def get(self):
        response = self.owner_api.get(REPORTS + 'shopping-list/')
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_only_active_sellable_items_at_or_below_their_level_and_out_first(self):
        self.product('Chips', stock='3', level='10')
        self.product('Soap', stock='0', level='5')
        self.product('Plenty', stock='50', level='10')
        self.product('Retired', stock='0', level='5', active=False)
        Product.objects.create(name='No unit', base_unit='pack', stock_qty=Decimal('0'), low_stock_level=Decimal('5'))
        data = self.get()
        self.assertEqual([(i['name'], i['status']) for i in data['items']], [('Soap', 'out'), ('Chips', 'low')])
        self.assertEqual(data['count'], 2)

    def test_the_last_delivery_is_shown(self):
        chips = self.product('Chips', stock='3', level='20')
        self.owner_api.post('/api/restocks/', {
            'product': chips.id, 'product_unit': chips.units.get().id,
            'quantity': '10', 'unit_cost': '12'}, format='json')            # stock 13, still low
        row = self.get()['items'][0]
        self.assertEqual((row['name'], row['stock'], row['last_quantity']), ('Chips', '13', '10'))
        self.assertEqual(row['last_bought'], timezone.localdate().isoformat())

    def test_never_bought_and_recount_flag(self):
        soap = self.product('Soap', stock='0', level='5')
        Product.objects.filter(pk=soap.pk).update(needs_recount=True)
        row = self.get()['items'][0]
        self.assertEqual((row['last_bought'], row['last_quantity'], row['needs_recount']), (None, None, True))


class CsvTests(StoreBase):
    def test_safe_text(self):
        for risky in ('=1+1', '+cmd', '-x', '@SUM(A1)', '\tx'):
            self.assertEqual(safe_text(risky), "'" + risky)
        self.assertEqual((safe_text('Marlboro'), safe_text(None), safe_text(5)), ('Marlboro', '', '5'))

    def test_the_sales_file(self):
        self.sell(self.piece, '7')
        response = self.owner_api.get(EXPORTS + 'sales/?group=day')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/csv'))
        self.assertTrue(response.content.startswith(b'\xef\xbb\xbf'))                  # the Excel marker
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        rows = table(response)
        self.assertEqual(rows[0][0], 'Day')
        self.assertEqual(rows[1], [timezone.localdate().isoformat(), '1', '5.00', '0.00', '1.50', '0.00', '0.00', '1.50'])
        self.assertEqual(len(rows), 2)                                                

    def test_the_file_name_comes_from_validated_dates(self):
        response = self.owner_api.get(EXPORTS + 'sales/?date_from=2026-03-01&date_to=2026-03-31&group=week')
        self.assertIn('sales-week-2026-03-01_to_2026-03-31.csv', response['Content-Disposition'])
        self.assertEqual(table(response)[0][0], 'Week starting (Monday)')

    def test_negative_money_stays_a_number(self):
        Product.objects.filter(pk=self.candy.pk).update(cost_price=Decimal('5'))
        self.sell(self.piece, '7')                                  # P5 sale, P35 cost
        row = table(self.owner_api.get(EXPORTS + 'sales/'))[1]
        self.assertEqual((row[4], row[7]), ('-30.00', '-30.00'))

    def test_formulas_in_names_are_neutralised(self):
        Product.objects.filter(pk=self.candy.pk).update(
            name='=HYPERLINK("http://evil","click")',
            category=Category.objects.create(name='+cmd'))
        rows = table(self.owner_api.get(EXPORTS + 'inventory/'))
        row = next(r for r in rows if 'HYPERLINK' in r[1])
        self.assertTrue(row[1].startswith("'="))
        self.assertTrue(row[0].startswith("'+"))

    def test_commas_and_quotes_survive(self):
        Product.objects.filter(pk=self.candy.pk).update(name='Chips, "Cheese"')
        rows = table(self.owner_api.get(EXPORTS + 'inventory/'))
        self.assertIn('Chips, "Cheese"', [r[1] for r in rows])

    def test_the_inventory_file(self):
        rows = table(self.owner_api.get(EXPORTS + 'inventory/'))
        self.assertEqual(rows[0], ['Category', 'Product', 'In stock', 'Unit', 'Cost per unit',
                                   'Value at cost', 'Status', 'Note'])
        marlboro = next(r for r in rows if r[1] == 'Marlboro Red')
        self.assertEqual(marlboro, ['(no category)', 'Marlboro Red', '400', 'stick', '8.0000',
                                    '3200.00', 'Active', ''])

    def test_best_sellers_by_quantity_and_by_profit(self):
        self.sell(self.piece, '50')                                
        self.sell(self.pack, '1')                                  
        by_qty = table(self.owner_api.get(EXPORTS + 'best-sellers/'))
        self.assertEqual(by_qty[1], ['1', 'Candy Test', '50', 'piece', '34.00', '9.00'])
        by_profit = table(self.owner_api.get(EXPORTS + 'best-sellers/?rank=profit&limit=1'))
        self.assertEqual(by_profit[1], ['1', 'Marlboro Red', '20', 'stick', '190.00', '30.00'])
        self.assertEqual(len(by_profit), 2)

    def test_slow_movers(self):
        piattos = self.product('Piattos', stock='10', cost='15')
        Product.objects.update(created_at=timezone.now() - timedelta(days=100))
        rows = table(self.owner_api.get(EXPORTS + 'slow-movers/'))
        self.assertEqual(rows[0][0], 'Product')
        self.assertEqual(next(r for r in rows if r[0] == piattos.name),
                         ['Piattos', '10', 'pack', '150.00', 'Never', ''])

    def test_the_shopping_list(self):
        self.product('Soap', stock='0', level='5')
        rows = table(self.owner_api.get(EXPORTS + 'shopping-list/'))
        self.assertEqual(rows[0][-1], 'To buy')
        self.assertEqual(rows[1], ['Soap', '(no category)', '0', 'pack', '5', 'OUT', 'Never', '', ''])


class PdfTests(StoreBase):
    def test_every_pdf_builds_even_with_odd_names(self):
        self.sell(self.piece, '7')
        Product.objects.filter(pk=self.candy.pk).update(name='Chips <Cheese> & "Onion"')
        self.product('Soap', stock='0', level='5')              
        for url in ['sales/', 'sales/?group=week', 'best-sellers/?rank=profit', 'slow-movers/',
                    'inventory/', 'shopping-list/']:
            with self.subTest(url=url):
                response = self.owner_api.get(f'{EXPORTS}{url}{"&" if "?" in url else "?"}fmt=pdf')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'application/pdf')
                self.assertTrue(response.content.startswith(b'%PDF'))
                self.assertIn('attachment', response['Content-Disposition'])

    def test_empty_reports_still_make_a_pdf(self):
        for url in ALL_EXPORTS:
            with self.subTest(url=url):
                self.assertTrue(self.owner_api.get(f'{EXPORTS}{url}?fmt=pdf').content.startswith(b'%PDF'))


class ValidationAndSecurityTests(StoreBase):
    def test_bad_requests_are_refused(self):
        bad = ['sales/?fmt=xml', 'sales/?fmt=', 'sales/?date_from=abc', 'sales/?group=year',
               'sales/?date_from=2026-01-01&date_to=2027-01-02', 'best-sellers/?rank=cheapest',
               'best-sellers/?limit=0', 'slow-movers/?days=0', 'slow-movers/?days=abc']
        for url in bad:
            with self.subTest(url=url):
                self.assertEqual(self.owner_api.get(EXPORTS + url).status_code, 400)

    def test_csv_is_the_default(self):
        self.assertTrue(self.owner_api.get(EXPORTS + 'inventory/')['Content-Type'].startswith('text/csv'))

    def test_only_the_owner_can_export(self):
        for url in ALL_EXPORTS:
            for fmt in ('csv', 'pdf'):
                with self.subTest(url=url, fmt=fmt):
                    self.assertEqual(self.api.get(f'{EXPORTS}{url}?fmt={fmt}').status_code, 403)
                    self.assertEqual(client_for().get(f'{EXPORTS}{url}?fmt={fmt}').status_code, 401)