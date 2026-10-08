from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Sum

from inventory.models import Product
from sales.models import Sale
from shifts.models import Shift


class Command(BaseCommand):
    help = 'Prints how many rows each store table holds, plus a few totals. Changes nothing.'

    def handle(self, *args, **options):
        self.stdout.write(f'Database: {connection.vendor}')
        for model in sorted(apps.get_models(), key=lambda m: m._meta.label):
            if model._meta.app_label in ('accounts', 'inventory', 'sales', 'shifts'):
                self.stdout.write(f'{model._meta.label}: {model.objects.count()}')
        stock = Product.objects.aggregate(t=Sum('stock_qty'))['t'] or 0
        sales = Sale.objects.aggregate(t=Sum('total'))['t'] or 0
        counted = Shift.objects.aggregate(t=Sum('counted_cash'))['t'] or 0
        self.stdout.write(f'Total stock: {stock:.3f}')
        self.stdout.write(f'Total of all sales: {sales:.2f}')
        self.stdout.write(f'Total counted cash: {counted:.2f}')