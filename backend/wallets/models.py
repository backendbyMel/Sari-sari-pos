from django.db import models
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import F, Q

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

class FeeRule(models.Model):
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name='fee_rules')
    min_amount = models.PositiveIntegerField()
    max_amount = models.PositiveIntegerField()
    fee = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(ZERO)])

    class Meta:
        ordering = ['wallet', 'min_amount']
        constraints = [
            models.CheckConstraint(condition=Q(min_amount__lte=F('max_amount')), name='fee_range_valid'),
        ]

    def __str__(self):
        return f'{self.min_amount}-{self.max_amount}: {self.fee}'


class EWalletTransaction(models.Model):
    class Type(models.TextChoices):
        CASH_IN = 'cash_in', 'Cash in'
        CASH_OUT = 'cash_out', 'Cash out'

    class Status(models.TextChoices):
        SUCCESS = 'success', 'Success'
        REVERSED = 'reversed', 'Reversed'

    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name='ewallet_transactions')
    wallet_name = models.CharField(max_length=50)                             
    type = models.CharField(max_length=8, choices=Type.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee = models.DecimalField(max_digits=10, decimal_places=2)              
    table_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 
    fee_overridden = models.BooleanField(default=False)
    fee_override_reason = models.CharField(max_length=200, blank=True)
    customer_mobile = models.CharField(max_length=20)
    reference_no = models.CharField(max_length=30)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.SUCCESS)
    shift = models.ForeignKey('shifts.Shift', on_delete=models.PROTECT, related_name='ewallet_transactions')
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                related_name='ewallet_transactions')
    receipt_no = models.CharField(max_length=20, unique=True)
    reversed_note = models.CharField(max_length=200, blank=True)
    reversed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.PROTECT, related_name='+')
    reversed_at = models.DateTimeField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp', '-id']
        constraints = [
            models.UniqueConstraint(fields=['wallet', 'reference_no'], name='one_reference_per_wallet'),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding and EWalletTransaction.objects.filter(pk=self.pk, status='reversed').exists():
            raise PermissionError('A reversed transaction cannot be changed.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('GCash records cannot be deleted.')

    def __str__(self):
        return f'{self.wallet_name} {self.type} {self.amount} ({self.status})'


class ShiftWalletCheck(models.Model):
    shift = models.ForeignKey('shifts.Shift', on_delete=models.PROTECT, related_name='wallet_checks')
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name='shift_checks')

    balance_start = models.DecimalField(max_digits=12, decimal_places=2)
    expected_start = models.DecimalField(max_digits=12, decimal_places=2)
    difference_start = models.DecimalField(max_digits=12, decimal_places=2)

    balance_end = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expected_end = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    difference_end = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['shift', 'wallet'], name='one_check_per_wallet_per_shift')]

    def save(self, *args, **kwargs):
        from shifts.models import Shift
        if not self._state.adding and Shift.objects.filter(pk=self.shift_id, status='closed').exists():
            raise PermissionError('The checks of a closed shift cannot be edited.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Wallet checks cannot be deleted.')

    def __str__(self):
        return f'Shift #{self.shift_id} {self.wallet.provider}'