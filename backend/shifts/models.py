from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

ZERO = Decimal('0')

# Create your models here.
class Shift(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        CLOSED = 'closed', 'Closed'

    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='shifts'
    )
    start_time = models.DateTimeField(auto_now_add=True, db_index=True)
    end_time = models.DateTimeField(null=True, blank=True)

    opening_cash = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )
    previous_closing_cash = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    opening_difference = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    expected_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    counted_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    variance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    status = models.CharField(max_length=6, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ['-start_time', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['status'],
                condition=Q(status='open'),
                name='only_one_open_shift',
            )
        ]

    def delete(self, *args, **kwargs):
        raise PermissionError('Shifts cannot be deleted.')

    def __str__(self):
        return f'Shift #{self.pk} {self.cashier} ({self.status})'