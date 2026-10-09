from django.db import models
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator

ZERO = Decimal('0')

# Create your models here.
class Wallet(models.Model):
    class Type(models.TextChoices):
        LOAD = 'load', 'Mobile load'
        EWALLET = 'ewallet', 'E-wallet'

    type = models.CharField(max_length=10, choices=Type.choices)
    provider = models.CharField(max_length=50)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    low_level = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('200.00'),
        validators=[MinValueValidator(ZERO)],
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['type', 'provider'], name='one_wallet_per_provider')]

    def delete(self, *args, **kwargs):
        raise PermissionError('Wallets cannot be deleted.')

    def __str__(self):
        return f'{self.provider} ({self.balance})'


class WalletTransaction(models.Model):
    class Type(models.TextChoices):
        TOPUP = 'topup', 'Top-up'
        LOAD_SENT = 'load_sent', 'Load sent'
        CASH_IN = 'cash_in', 'Cash in'
        CASH_OUT = 'cash_out', 'Cash out'
        ADJUSTMENT = 'adjustment', 'Adjustment'
        REVERSAL = 'reversal', 'Reversal'

    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name='transactions')
    type = models.CharField(max_length=12, choices=Type.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)          # signed: + adds, - removes
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    reference_no = models.CharField(max_length=50, blank=True)
    source = models.CharField(max_length=12, blank=True)                   # top-ups: drawer, owner_cash, bank
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    shift = models.ForeignKey('shifts.Shift', null=True, blank=True, on_delete=models.PROTECT,
                              related_name='wallet_transactions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                             related_name='wallet_transactions')
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp', '-id']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError('Wallet entries cannot be edited.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Wallet entries cannot be deleted.')

    def __str__(self):
        return f'{self.type} {self.amount} -> {self.balance_after}'


class LoadNetwork(models.Model):
    name = models.CharField(max_length=50, unique=True)
    rebate_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(ZERO), MaxValueValidator(Decimal('100'))],
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def delete(self, *args, **kwargs):
        raise PermissionError('Networks cannot be deleted. Deactivate them.')

    def __str__(self):
        return self.name


class LoadProduct(models.Model):
    network = models.ForeignKey(LoadNetwork, on_delete=models.PROTECT, related_name='products')
    name = models.CharField(max_length=100)                                
    face_value = models.DecimalField(                                      
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    selling_price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(ZERO)])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['network__name', 'face_value', 'name']
        constraints = [models.UniqueConstraint(fields=['network', 'name'], name='one_load_product_name')]

    def delete(self, *args, **kwargs):
        raise PermissionError('Load products cannot be deleted. Deactivate them.')

    def __str__(self):
        return f'{self.network.name} {self.name}'


class LoadTransaction(models.Model):
    class Status(models.TextChoices):
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'

    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name='load_transactions')
    load_product = models.ForeignKey(LoadProduct, on_delete=models.PROTECT, related_name='transactions')
    network_name = models.CharField(max_length=50)
    product_name = models.CharField(max_length=100)
    mobile_no = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=10, decimal_places=2)           # removed from the wallet
    price_charged = models.DecimalField(max_digits=10, decimal_places=2)    # cash into the drawer
    rebate = models.DecimalField(max_digits=10, decimal_places=2)           # OWNER ONLY
    reference_no = models.CharField(max_length=30)
    status = models.CharField(max_length=7, choices=Status.choices, default=Status.SUCCESS)
    shift = models.ForeignKey('shifts.Shift', on_delete=models.PROTECT, related_name='load_transactions')
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                related_name='load_transactions')
    receipt_no = models.CharField(max_length=20, unique=True)
    failed_note = models.CharField(max_length=200, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp', '-id']
        constraints = [
            models.UniqueConstraint(fields=['network_name', 'reference_no'], name='one_reference_per_network'),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding and LoadTransaction.objects.filter(pk=self.pk, status='failed').exists():
            raise PermissionError('A failed load cannot be changed.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Load records cannot be deleted.')

    def __str__(self):
        return f'{self.network_name} {self.product_name} ({self.status})'