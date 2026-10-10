from decimal import Decimal

from django.core.management.base import BaseCommand

from wallets.models import FeeRule
from wallets.services import get_ewallet


class Command(BaseCommand):
    help = 'Creates the GCash wallet and an EXAMPLE fee table (P10 per P500 or part of it, up to P5,000). Safe to run twice.'

    def handle(self, *args, **options):
        wallet = get_ewallet()
        for k in range(1, 11):
            FeeRule.objects.get_or_create(
                wallet=wallet, min_amount=(k - 1) * 500 + 1,
                defaults={'max_amount': k * 500, 'fee': Decimal(10 * k)},
            )
        self.stdout.write(self.style.SUCCESS('Done. Set your real fees in Owner > GCash fees.'))