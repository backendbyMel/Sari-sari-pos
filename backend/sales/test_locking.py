import threading
import time
from decimal import Decimal
from unittest import skipUnless

from django.db import connection, connections, transaction
from django.test import TransactionTestCase

from config.testkit import make_candy, make_cashier, open_shift
from inventory.models import Product
from sales.models import Sale
from sales.services import create_sale


def in_thread(errors, target):
    """Runs target() in its own thread (its own database connection)."""
    def runner():
        try:
            target()
        except Exception as error:  
            errors.append(error)
        finally:
            connections.close_all()
    thread = threading.Thread(target=runner)
    thread.start()
    return thread


@skipUnless(connection.vendor == 'postgresql', 'Row locks only exist on PostgreSQL.')
class RowLockTests(TransactionTestCase):
    """
    These tests use real database connections at the same time, so they cannot
    run inside the usual test transaction.
    """

    def setUp(self):
        self.cashier = make_cashier()
        open_shift(self.cashier)
        self.product, self.unit = make_candy(stock='100')

    def sell_one(self):
        return create_sale(
            cashier=self.cashier, payment_type='cash', cash_received=Decimal('5'),
            items=[{'product_unit': self.unit.id, 'quantity': Decimal('1')}],
        )

    def test_a_sale_waits_for_a_product_that_another_request_is_using(self):
        errors, order = [], []
        locked, release = threading.Event(), threading.Event()

        def other_request():
            # Pretends to be another sale that is busy with this same product.
            with transaction.atomic():
                product = Product.objects.select_for_update().get(pk=self.product.pk)
                locked.set()
                release.wait(10)
                product.stock_qty -= Decimal('10')
                product.save(update_fields=['stock_qty'])
                order.append('other request finished')

        def our_sale():
            locked.wait(10)
            self.sell_one()
            order.append('our sale finished')

        first = in_thread(errors, other_request)
        second = in_thread(errors, our_sale)
        time.sleep(1)                    
        self.assertEqual(order, [], 'The sale did not wait for the locked product.')
        release.set()
        first.join(15)
        second.join(15)

        self.assertEqual(errors, [])
        self.assertEqual(order, ['other request finished', 'our sale finished'])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, Decimal('89'))   # 100 - 10 - 1, nothing lost

    def test_simultaneous_sales_all_count_and_receipt_numbers_never_repeat(self):
        count = 8
        errors, numbers = [], []
        start = threading.Barrier(count)

        def one_sale():
            start.wait(10)                 # everyone starts at the same moment
            sale, _ = self.sell_one()
            numbers.append(sale.receipt_no)

        threads = [in_thread(errors, one_sale) for _ in range(count)]
        for thread in threads:
            thread.join(30)

        self.assertEqual(errors, [])
        self.assertEqual(sorted(numbers), [f'SR-{n:06d}' for n in range(1, count + 1)])
        self.assertEqual(Sale.objects.count(), count)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_qty, Decimal('92'))