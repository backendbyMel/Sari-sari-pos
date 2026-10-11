from datetime import datetime, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from config.testkit import (
    client_for, fund_ewallet, fund_wallet, make_candy, make_cashier, make_customer, make_gcash,
    make_load, make_marlboro, make_owner, open_shift,
)
from inventory.models import Category, Product, ProductUnit
from sales.models import Sale

BASE = '/api/owner/reports/'
MARCH = 'date_from=2026-03-01&date_to=2026-03-31'


def manila(month, day, hour=10, minute=0):
    return timezone.make_aware(datetime(2026, month, day, hour, minute))


class ReportBase(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.cashier = make_cashier()
        self.shift = open_shift(self.cashier, '1000.00')
        self.api = client_for(self.cashier)
        self.owner_api = client_for(self.owner)
        self.marlboro, self.stick, self.pack = make_marlboro()      # cost P8 per stick
        self.candy, self.piece = make_candy()                    

    def sell(self, unit, qty, when=None, cash='500', api=None):
        response = (api or self.api).post('/api/sales/', {
            'items': [{'product_unit': unit.id, 'quantity': qty}], 'cash_received': cash}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        if when is not None:
            Sale.objects.filter(receipt_no=response.data['receipt']['receipt_no']).update(timestamp=when)
        return response

    def raw(self, name, query=''):
        return self.owner_api.get(f'{BASE}{name}/?{query}')

    def get(self, name, query=''):
        response = self.raw(name, query)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data


class SalesReportTests(ReportBase):
    def test_the_totals_add_up_across_goods_load_and_gcash(self):
        self.sell(self.piece, '7')                   
        self.sell(self.pack, '1')                     
        _, load = make_load()                       
        fund_wallet(self.owner, '1000')
        self.api.post('/api/load/send/', {'product': load.id, 'mobile_no': '09171234567',
                                          'reference_no': 'REF00001'}, format='json')
        make_gcash()
        fund_ewallet(self.owner, '2000')
        self.api.post('/api/ewallet/cash-in/', {'amount': 500, 'mobile_no': '09171234567',
                                                'reference_no': 'GC00000001'}, format='json')
        data = self.get('sales')
        self.assertEqual(len(data['rows']), 1)
        totals = data['totals']
        self.assertEqual((totals['sales_count'], totals['sales_total'], totals['utang_total']), (2, '195.00', '0.00'))
        self.assertEqual((totals['goods_profit'], totals['load_sales'], totals['load_profit'], totals['fees']),
                         ('31.50', '52.00', '4.00', '10.00'))
        self.assertEqual(totals['profit'], '45.50')
        self.assertEqual(data['rows'][0]['profit'], '45.50')

    def test_day_week_and_month_grouping(self):
        for when in (manila(3, 2, 10), manila(3, 3, 15), manila(3, 9, 9)):     
            self.sell(self.piece, '7', when, cash='10')
        days = self.get('sales', f'{MARCH}&group=day')['rows']
        self.assertEqual([r['period'] for r in days], ['2026-03-02', '2026-03-03', '2026-03-09'])
        weeks = self.get('sales', f'{MARCH}&group=week')['rows']
        self.assertEqual([(r['period'], r['sales_count']) for r in weeks], [('2026-03-02', 2), ('2026-03-09', 1)])
        months = self.get('sales', f'{MARCH}&group=month')
        self.assertEqual([(r['period'], r['sales_count']) for r in months['rows']], [('2026-03-01', 3)])
        self.assertEqual((months['totals']['sales_total'], months['totals']['goods_profit']), ('15.00', '4.50'))

    def test_days_are_manila_days_not_utc_days(self):
        self.sell(self.piece, '7', manila(3, 3, 0, 30), cash='10')              # 12:30 AM on the 3rd
        self.assertEqual([r['period'] for r in self.get('sales', MARCH)['rows']], ['2026-03-03'])
        self.assertEqual(self.get('sales', 'date_from=2026-03-01&date_to=2026-03-02')['rows'], [])

    def test_the_range_includes_its_last_day_and_excludes_the_day_before(self):
        self.sell(self.piece, '7', timezone.make_aware(datetime(2026, 2, 28, 23, 59)), cash='10')
        self.sell(self.piece, '7', timezone.make_aware(datetime(2026, 3, 31, 23, 59)), cash='10')
        rows = self.get('sales', MARCH)['rows']
        self.assertEqual([r['period'] for r in rows], ['2026-03-31'])

    def test_voided_sales_do_not_count(self):
        self.sell(self.piece, '7')
        Sale.objects.update(status='voided')
        data = self.get('sales')
        self.assertEqual(data['rows'], [])
        self.assertEqual((data['totals']['sales_total'], data['totals']['profit']), ('0.00', '0.00'))

    def test_failed_loads_and_reversed_gcash_do_not_count(self):
        _, load = make_load()
        fund_wallet(self.owner, '1000')
        sent = self.api.post('/api/load/send/', {'product': load.id, 'mobile_no': '09171234567',
                                                 'reference_no': 'REF00001'}, format='json')
        self.api.post(f"/api/load/{sent.data['load_id']}/fail/", {'note': 'Provider error'}, format='json')
        make_gcash()
        fund_ewallet(self.owner, '2000')
        tx = self.api.post('/api/ewallet/cash-in/', {'amount': 500, 'mobile_no': '09171234567',
                                                     'reference_no': 'GC00000001'}, format='json')
        self.owner_api.post(f"/api/owner/ewallet/{tx.data['tx_id']}/reverse/", {'note': 'Cancelled'}, format='json')
        totals = self.get('sales')['totals']
        self.assertEqual((totals['load_sales'], totals['load_profit'], totals['fees'], totals['profit']),
                         ('0.00', '0.00', '0.00', '0.00'))

    def test_utang_counts_as_a_sale_and_the_write_off_is_its_own_line(self):
        nena = make_customer()
        self.api.post('/api/sales/', {'items': [{'product_unit': self.piece.id, 'quantity': '7'}],
                                      'payment_type': 'utang', 'customer': nena.id}, format='json')
        self.owner_api.post(f'/api/owner/customers/{nena.id}/write-off/',
                            {'amount': '2', 'reason': 'Moved away'}, format='json')
        totals = self.get('sales')['totals']
        self.assertEqual((totals['sales_total'], totals['utang_total'], totals['profit']), ('5.00', '5.00', '1.50'))
        self.assertEqual(totals['writeoffs'], '2.00')                           

    def test_a_price_or_cost_change_does_not_rewrite_history(self):
        self.sell(self.pack, '1')
        self.owner_api.patch(f'/api/units/{self.pack.id}/', {'selling_price': '300.00'}, format='json')
        self.owner_api.post('/api/restocks/', {'product': self.marlboro.id, 'product_unit': self.pack.id,
                                               'quantity': '10', 'unit_cost': '220'}, format='json')
        self.assertEqual(self.get('sales')['totals']['goods_profit'], '30.00')

    def test_an_empty_range(self):
        data = self.get('sales', MARCH)
        self.assertEqual((data['rows'], data['by_cashier'], data['by_category']), ([], [], []))
        self.assertEqual((data['totals']['sales_total'], data['totals']['profit']), ('0.00', '0.00'))

    def test_the_breakdown_by_cashier(self):
        self.sell(self.piece, '7')                                              
        self.api.post('/api/shifts/end/', {'counted_cash': '1005'}, format='json')
        second = make_cashier('cash2')
        open_shift(second, '1000.00')
        self.sell(self.pack, '1', api=client_for(second))                        # cash2: P30 profit
        rows = self.get('sales')['by_cashier']
        self.assertEqual([(r['cashier'], r['sales_total'], r['profit']) for r in rows],
                         [('cash2', '190.00', '30.00'), ('cash', '5.00', '1.50')])

    def test_the_breakdown_by_category(self):
        category = Category.objects.create(name='Cigarettes')
        Product.objects.filter(pk=self.marlboro.pk).update(category=category)
        self.sell(self.pack, '1')
        self.sell(self.piece, '7')
        rows = self.get('sales')['by_category']
        self.assertEqual([(r['category'], r['sales_total'], r['goods_profit']) for r in rows],
                         [('Cigarettes', '190.00', '30.00'), ('(no category)', '5.00', '1.50')])


class HourlyTests(ReportBase):
    def test_busy_hours(self):
        for when in (manila(3, 2, 10, 15), manila(3, 2, 10, 45), manila(3, 2, 15, 0)):
            self.sell(self.piece, '7', when, cash='10')
        data = self.get('hourly', MARCH)
        self.assertEqual(len(data['hours']), 24)
        by_hour = {h['hour']: h for h in data['hours']}
        self.assertEqual((by_hour[10]['sales_count'], by_hour[10]['sales_total']), (2, '10.00'))
        self.assertEqual((by_hour[15]['sales_count'], by_hour[3]['sales_count']), (1, 0))
        self.assertEqual(data['busiest_hour'], 10)

    def test_no_sales_means_no_busiest_hour(self):
        self.assertIsNone(self.get('hourly', MARCH)['busiest_hour'])


class BestSellerTests(ReportBase):
    def test_ranked_by_quantity_and_by_profit(self):
        self.sell(self.piece, '50')                    
        self.sell(self.pack, '1')                     
        data = self.get('best-sellers')
        first_qty, second_qty = data['by_quantity']
        self.assertEqual((first_qty['product'], first_qty['quantity'], first_qty['unit'], first_qty['profit']),
                         ('Candy Test', '50', 'piece', '9.00'))
        self.assertEqual((second_qty['product'], second_qty['quantity'], second_qty['unit']),
                         ('Marlboro Red', '20', 'stick'))
        first_profit = data['by_profit'][0]
        self.assertEqual((first_profit['product'], first_profit['profit'], first_profit['sales_total']),
                         ('Marlboro Red', '30.00', '190.00'))

    def test_the_limit(self):
        self.sell(self.piece, '7')
        self.sell(self.pack, '1')
        data = self.get('best-sellers', 'limit=1')
        self.assertEqual((len(data['by_quantity']), len(data['by_profit'])), (1, 1))

    def test_voided_sales_do_not_count(self):
        self.sell(self.piece, '7')
        Sale.objects.update(status='voided')
        self.assertEqual(self.get('best-sellers')['by_quantity'], [])


class SlowMoverTests(ReportBase):
    def setUp(self):
        super().setUp()
        self.old = timezone.now() - timedelta(days=100)
        Product.objects.update(created_at=self.old)

    def product(self, name, stock='10', cost='15', old=True, **extra):
        p = Product.objects.create(name=name, base_unit='pack', cost_price=Decimal(cost),
                                   stock_qty=Decimal(stock), **extra)
        ProductUnit.objects.create(product=p, unit_name='pack', pieces_per_unit=Decimal('1'),
                                   selling_price=Decimal('25'))
        if old:
            Product.objects.filter(pk=p.pk).update(created_at=self.old)
        return p

    def build(self):
        sale = self.sell(self.pack, '1')                                       
        Sale.objects.filter(receipt_no=sale.data['receipt']['receipt_no']).update(
            timestamp=timezone.now() - timedelta(days=45))
        self.sell(self.piece, '7')                                             
        self.product('Piattos')                                                 
        self.product('Newbie', old=False)                                        
        self.product('Empty', stock='0')                                         
        self.product('Retired', is_active=False)                               
        Product.objects.create(name='No unit', base_unit='pack', stock_qty=Decimal('5'), created_at=self.old)

    def test_who_is_slow(self):
        self.build()
        data = self.get('slow-movers')
        self.assertEqual([i['name'] for i in data['items']], ['Marlboro Red', 'Piattos'])
        self.assertEqual((data['count'], data['tied_up']), (2, '3190.00'))        # 380 x 8 + 10 x 15
        marlboro, piattos = data['items']
        self.assertEqual((marlboro['days_since'], marlboro['value'], marlboro['stock']), (45, '3040.00', '380'))
        self.assertEqual((piattos['days_since'], piattos['last_sold']), (None, None))

    def test_a_longer_window_forgives_recent_enough_sales(self):
        self.build()
        data = self.get('slow-movers', 'days=60')
        self.assertEqual([i['name'] for i in data['items']], ['Piattos'])


class ValidationAndSecurityTests(ReportBase):
    def test_bad_requests_are_refused(self):
        bad = [
            ('sales', 'date_from=abc'), ('sales', 'date_to=2026-13-40'),
            ('sales', 'date_from=2026-03-31&date_to=2026-03-01'),
            ('sales', 'date_from=2026-01-01&date_to=2027-01-02'),                # 367 days
            ('sales', 'group=year'), ('hourly', 'date_from=nope'),
            ('best-sellers', 'limit=0'), ('best-sellers', 'limit=101'), ('best-sellers', 'limit=abc'),
            ('slow-movers', 'days=0'), ('slow-movers', 'days=366'), ('slow-movers', 'days=abc'),
        ]
        for name, query in bad:
            with self.subTest(name=name, query=query):
                self.assertEqual(self.raw(name, query).status_code, 400)

    def test_the_longest_allowed_range_works(self):
        self.assertEqual(self.raw('sales', 'date_from=2026-01-01&date_to=2027-01-01').status_code, 200)

    def test_only_the_owner_can_read_reports(self):
        for name in ('sales', 'hourly', 'best-sellers', 'slow-movers'):
            with self.subTest(name=name):
                self.assertEqual(self.api.get(f'{BASE}{name}/').status_code, 403)
                self.assertEqual(client_for().get(f'{BASE}{name}/').status_code, 401)

    def test_money_is_text_never_a_float(self):
        self.sell(self.piece, '7')
        data = self.get('sales')
        for key in ('sales_total', 'goods_profit', 'profit', 'writeoffs'):
            self.assertIsInstance(data['totals'][key], str)
        self.assertIsInstance(self.get('best-sellers')['by_profit'][0]['profit'], str)