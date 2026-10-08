from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from config.testkit import client_for, make_candy, make_cashier, make_marlboro, make_owner
from inventory.models import Product, StockMovement
from sales.models import Receipt, Sale
from shifts.models import Shift, ShiftReport


class StoreCase(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.ana = make_cashier('ana')
        self.ben = make_cashier('ben')
        self.owner_api = client_for(self.owner)
        self.ana_api = client_for(self.ana)
        self.ben_api = client_for(self.ben)
        self.marlboro, self.stick, self.pack = make_marlboro()   
        self.candy, self.piece = make_candy()                    

    def start(self, api, cash):
        return api.post('/api/shifts/start/', {'opening_cash': cash}, format='json')

    def sell(self, api, lines, cash):
        items = [{'product_unit': unit.id, 'quantity': qty} for unit, qty in lines]
        return api.post('/api/sales/', {'items': items, 'cash_received': cash}, format='json')

    def end(self, api, counted):
        return api.post('/api/shifts/end/', {'counted_cash': counted}, format='json')

    def payout(self, api, amount, reason):
        return api.post('/api/shifts/payouts/', {'amount': amount, 'reason': reason}, format='json')

    def get_status(self, api, url):
        response = api.get(url)
        if getattr(response, 'streaming', False):
            response.close()
        return response.status_code

    def run_check(self, **options):
        out = StringIO()
        call_command('check_integrity', stdout=out, **options)
        return out.getvalue()

    def failing_check(self, **options):
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command('check_integrity', stdout=out, **options)
        return out.getvalue()


class StoreDayTests(StoreCase):
    def test_two_shifts_end_to_end(self):
        self.assertEqual(self.start(self.ana_api, '1000').status_code, 201)
        self.assertEqual(self.sell(self.ana_api, [(self.pack, '1'), (self.piece, '7')], '200').status_code, 201)
        self.assertEqual(self.payout(self.ana_api, '50', 'Bought ice').status_code, 201)

        self.assertEqual(self.start(self.ben_api, '1000').status_code, 400)
        self.assertEqual(self.sell(self.ben_api, [(self.piece, '1')], '5').status_code, 400)

        closed = self.end(self.ana_api, '1125')
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(Decimal(closed.data['shift']['expected_cash']), Decimal('1145'))
        self.assertEqual(Decimal(closed.data['shift']['variance']), Decimal('-20'))
        ana_shift = Shift.objects.get(cashier=self.ana)
        self.assertEqual(self.sell(self.ana_api, [(self.piece, '1')], '5').status_code, 400)

        started = self.start(self.ben_api, '1000')
        self.assertEqual(started.status_code, 201)
        self.assertNotIn('difference', started.content.decode().lower())  
        ben_shift = Shift.objects.get(cashier=self.ben)
        self.assertEqual(ben_shift.opening_difference, Decimal('-125'))
        self.assertEqual(self.sell(self.ben_api, [(self.piece, '1')], '5').status_code, 201)

        close = self.owner_api.post(
            f'/api/shifts/{ben_shift.id}/close/',
            {'counted_cash': '1001', 'reason': 'Ben went home sick'}, format='json')
        self.assertEqual(close.status_code, 200)
        self.assertTrue(close.data['shift']['closed_on_behalf'])

        ana_url = f'/api/shifts/{ana_shift.id}/report/'
        ben_url = f'/api/shifts/{ben_shift.id}/report/'
        self.assertEqual(self.get_status(self.ana_api, ana_url), 200)
        self.assertEqual(self.get_status(self.ben_api, ben_url), 200)
        self.assertEqual(self.get_status(self.ana_api, ben_url), 404)
        self.assertEqual(self.get_status(self.ben_api, ana_url), 404)
        self.assertEqual(self.get_status(self.ana_api, ana_url + '?copy=owner'), 403)
        self.assertEqual(self.get_status(self.owner_api, ana_url + '?copy=owner'), 200)

        old = self.owner_api.post(f'/api/shifts/{ana_shift.id}/reopen/', {'reason': 'x'}, format='json')
        self.assertEqual(old.status_code, 400)
        reopen = self.owner_api.post(f'/api/shifts/{ben_shift.id}/reopen/', {'reason': 'Recount'}, format='json')
        self.assertEqual(reopen.status_code, 200)
        self.assertEqual(self.end(self.ben_api, '1001').status_code, 200)
        self.assertEqual(ShiftReport.objects.filter(shift=ben_shift).count(), 2)

        
        rows = {r['id']: r for r in self.owner_api.get('/api/shifts/').data}
        self.assertEqual(len(rows), 2)
        self.assertEqual(Decimal(rows[ben_shift.id]['opening_difference']), Decimal('-125'))
        self.assertEqual(rows[ben_shift.id]['reopen_count'], 1)
        flagged = [r['id'] for r in self.owner_api.get('/api/shifts/?variance=1').data]
        self.assertEqual(flagged, [ana_shift.id])

        
        self.marlboro.refresh_from_db()
        self.candy.refresh_from_db()
        self.assertEqual(self.marlboro.stock_qty, Decimal('380'))   
        self.assertEqual(self.candy.stock_qty, Decimal('92'))      
        self.assertIn('OK', self.run_check())


class IntegrityCheckTests(StoreCase):
    def make_day(self):
        """A busy shift: a sale, a pay-out, a delivery, a damaged item, and a close."""
        self.start(self.ana_api, '1000')
        self.sell(self.ana_api, [(self.pack, '1'), (self.piece, '7')], '200')
        self.payout(self.ana_api, '50', 'Bought ice')
        self.owner_api.post('/api/restocks/', {
            'product': self.marlboro.id, 'product_unit': self.pack.id,
            'quantity': '10', 'unit_cost': '173.40'}, format='json')
        self.owner_api.post('/api/stock-adjustments/', {
            'product': self.marlboro.id, 'quantity': '-5',
            'reason_type': 'damaged', 'note': 'Pack fell in water'}, format='json')
        self.end(self.ana_api, '1145')
        return Shift.objects.get(cashier=self.ana)

    def test_an_empty_store_is_clean(self):
        self.assertIn('OK', self.run_check())

    def test_a_normal_day_is_clean(self):
        self.make_day()
        self.assertIn('OK', self.run_check())

    def test_stock_that_was_changed_behind_the_scenes(self):
        self.make_day()
        Product.objects.filter(pk=self.marlboro.pk).update(stock_qty=Decimal('999'))
        output = self.failing_check()
        self.assertIn('Marlboro Red', output)
        self.assertIn('history ends', output)

    def test_a_broken_history_line(self):
        self.make_day()
        StockMovement.objects.filter(type='adjustment').update(balance_after=Decimal('1'))
        self.assertIn('does not follow', self.failing_check())

    def test_a_sale_total_that_does_not_match_its_lines(self):
        self.make_day()
        Sale.objects.update(total=Decimal('1.00'))
        self.assertIn('SR-000001', self.failing_check())

    def test_a_missing_receipt(self):
        self.make_day()
        Receipt.objects.all().delete()
        self.assertIn('has no receipt', self.failing_check())

    def test_expected_cash_that_does_not_add_up(self):
        shift = self.make_day()
        Shift.objects.filter(pk=shift.pk).update(expected_cash=Decimal('1.00'))
        self.assertIn('expected cash', self.failing_check())

    def test_a_variance_that_does_not_add_up(self):
        shift = self.make_day()
        Shift.objects.filter(pk=shift.pk).update(variance=Decimal('77.00'))
        self.assertIn('variance', self.failing_check())

    def test_a_sale_saved_after_the_shift_closed(self):
        shift = self.make_day()
        Sale.objects.update(timestamp=shift.end_time + timedelta(hours=1))
        self.assertIn('after its shift was closed', self.failing_check())

    def test_old_test_data_can_be_skipped(self):
        shift = self.make_day()
        Shift.objects.filter(pk=shift.pk).update(expected_cash=None)  
        self.assertIn('missing its cash numbers', self.failing_check())
        self.assertIn('OK', self.run_check(from_shift=shift.pk + 1))