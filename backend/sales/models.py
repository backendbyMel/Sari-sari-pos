from django.db import models
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from inventory.models import Product, ProductUnit
from django.db.models import Q
# Create your models here.
ZERO = Decimal('0')


class ReceiptCounter(models.Model):
    last_number = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f'Last receipt number: {self.last_number}'


class Sale(models.Model):
    class PaymentType(models.TextChoices):
        CASH = 'cash', 'Cash'
        UTANG = 'utang', 'Utang'      # not usable until Phase 3

    class Status(models.TextChoices):
        COMPLETED = 'completed', 'Completed'
        VOIDED = 'voided', 'Voided'
        
    receipt_no = models.CharField(max_length=20, unique=True)
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='sales'
    )
    shift = models.ForeignKey(
        'shifts.Shift', null=True, blank=True, on_delete=models.PROTECT,
        related_name='sales',
    )
    customer = models.ForeignKey(
        'utang.Customer', null=True, blank=True, on_delete=models.PROTECT, related_name='sales'
    )
    customer_balance_after = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    payment_type = models.CharField(
        max_length=10, choices=PaymentType.choices, default=PaymentType.CASH
    )
    total = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )
    discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    cash_received = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    change = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.COMPLETED
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp', '-id']

    def delete(self, *args, **kwargs):
        raise PermissionError('Sales cannot be deleted. Void them instead.')

    def __str__(self):
        return f'{self.receipt_no} P{self.total} ({self.status})'


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='items')
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='sale_items'
    )
    product_unit = models.ForeignKey(
        ProductUnit, on_delete=models.PROTECT, related_name='sale_items'
    )
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))]
    )
    base_quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError('Sale items cannot be edited.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Sale items cannot be deleted.')

    def __str__(self):
        return f'{self.quantity} x {self.product_unit}'


class Receipt(models.Model):
    class Source(models.TextChoices):
        SALE = 'sale', 'Sale'
        UTANG_PAYMENT = 'utang_payment', 'Utang payment'   # Phase 3
        LOAD = 'load', 'Mobile load'                       # Phase 3
        EWALLET = 'ewallet', 'E-wallet'                    # Phase 3

    receipt_no = models.CharField(max_length=20, unique=True)
    source = models.CharField(max_length=15, choices=Source.choices)
    source_id = models.PositiveIntegerField()
    printed_count = models.PositiveIntegerField(default=0)
    reprint_log = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'source_id'], name='one_receipt_per_source'
            )
        ]

    def delete(self, *args, **kwargs):
        raise PermissionError('Receipts cannot be deleted.')

    def __str__(self):
        return self.receipt_no


class VoidRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='void_requests')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='void_requests')
    reason = models.CharField(max_length=200)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    requested_at = models.DateTimeField(auto_now_add=True, db_index=True)

    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.PROTECT, related_name='void_decisions')
    decision_note = models.CharField(max_length=200, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    refund_shift = models.ForeignKey('shifts.Shift', null=True, blank=True, on_delete=models.PROTECT,
                                     related_name='void_refunds')

    class Meta:
        ordering = ['-requested_at', '-id']
        constraints = [
            models.UniqueConstraint(fields=['sale'], condition=Q(status__in=['pending', 'approved']),
                                    name='one_live_void_per_sale'),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding and VoidRequest.objects.filter(pk=self.pk).exclude(status='pending').exists():
            raise PermissionError('A decided void request cannot be changed.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Void requests cannot be deleted.')

    def __str__(self):
        return f'Void {self.sale.receipt_no} ({self.status})'