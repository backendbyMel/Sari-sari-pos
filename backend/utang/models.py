from django.db import models


from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator

ZERO = Decimal('0')

# Create your models here.
class Customer(models.Model):
    name = models.CharField(max_length=150)
    contact = models.CharField(max_length=150, help_text='Phone number or address')
    credit_limit = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(ZERO)],
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='customers_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name', 'id']

    def delete(self, *args, **kwargs):
        raise PermissionError('Customers cannot be deleted.')

    def __str__(self):
        return f'{self.name} (owes {self.balance})'


class UtangPayment(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))]
    )
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='utang_payments'
    )
    shift = models.ForeignKey('shifts.Shift', on_delete=models.PROTECT, related_name='utang_payments')
    receipt_no = models.CharField(max_length=20, unique=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp', '-id']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError('Payments cannot be edited.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Payments cannot be deleted.')

    def __str__(self):
        return f'{self.customer.name} paid {self.amount}'

class BadDebtWriteOff(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='writeoffs')
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))]
    )
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=200)
    written_off_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='writeoffs_made'
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp', '-id']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError('Write-offs cannot be edited.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Write-offs cannot be deleted.')

    def __str__(self):
        return f'{self.customer.name}: wrote off {self.amount}'