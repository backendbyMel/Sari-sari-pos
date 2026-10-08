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
    denominations = models.JSONField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='closed_shifts',
    )
    close_reason = models.CharField(max_length=200, blank=True)
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
    def save(self, *args, **kwargs):
      if not self._state.adding and Shift.objects.filter(
        pk=self.pk, status=self.Status.CLOSED
      ).exists():
        raise PermissionError('A closed shift cannot be edited. The owner can reopen it.')
      super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Shifts cannot be deleted.')

    def __str__(self):
        return f'Shift #{self.pk} {self.cashier} ({self.status})'

class ShiftReopen(models.Model):
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name='reopens')
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='shift_reopens'
    )
    reason = models.CharField(max_length=200)
    timestamp = models.DateTimeField(auto_now_add=True)

    previous_end_time = models.DateTimeField(null=True, blank=True)
    previous_expected_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    previous_counted_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    previous_variance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    previous_denominations = models.JSONField(null=True, blank=True)
    previous_closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+',
    )
    previous_close_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-timestamp', '-id']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError('Reopen records cannot be edited.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Reopen records cannot be deleted.')

    def __str__(self):
        return f'Shift #{self.shift_id} reopened by {self.reopened_by}'


class CashMovement(models.Model):
    class Type(models.TextChoices):
        OUT = 'out', 'Pay-out'
        IN = 'in', 'Cash in'       

    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name='cash_movements')
    type = models.CharField(max_length=3, choices=Type.choices)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))]
    )
    reason = models.CharField(max_length=200)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cash_movements'
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp', '-id']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError('Cash movements cannot be edited.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Cash movements cannot be deleted.')

    def __str__(self):
        return f'{self.type} P{self.amount} on shift #{self.shift_id}'