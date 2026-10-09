from decimal import Decimal

from django.core.management.base import BaseCommand

from wallets.models import LoadNetwork, LoadProduct
from wallets.services import get_load_wallet


class Command(BaseCommand):
    help = 'Creates Smart, Globe and TM with regular loads (price = amount, rebate 0%). Safe to run twice.'

    def handle(self, *args, **options):
        get_load_wallet()
        for name in ('Smart', 'Globe', 'TM'):
            network, _ = LoadNetwork.objects.get_or_create(name=name, defaults={'rebate_percent': Decimal('0')})
            for face in (10, 20, 50, 100):
                LoadProduct.objects.get_or_create(
                    network=network, name=f'Load {face}',
                    defaults={'face_value': Decimal(face), 'selling_price': Decimal(face)},
                )
        self.stdout.write(self.style.SUCCESS(
            'Done. Set your real prices and rebates (and add promos like EZ50) in Owner > Load setup.'))