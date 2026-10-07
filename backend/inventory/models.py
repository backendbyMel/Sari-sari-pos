from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

ZERO = Decimal('0')


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=150)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.PROTECT,
        related_name='products',
    )
    base_unit = models.CharField(
        max_length=30, help_text='Smallest thing you sell: stick, sachet, piece'
    )
    
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=4, default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    
    stock_qty = models.DecimalField(max_digits=12, decimal_places=3, default=ZERO)
    low_stock_level = models.DecimalField(
        max_digits=12, decimal_places=3, default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    photo = models.ImageField(upload_to='products/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    needs_recount = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    @property
    def stock_status(self):
        """Used by the price-check page: 'out', 'low', or 'in_stock'."""
        if self.stock_qty <= 0:
            return 'out'
        if self.stock_qty <= self.low_stock_level:
            return 'low'
        return 'in_stock'

    def __str__(self):
        return self.name


class ProductUnit(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='units'
    )
    unit_name = models.CharField(max_length=30)
    pieces_per_unit = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('1'),
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text='How many BASE units are in one of this unit (pack = 20 sticks)',
    )
    
    barcode = models.CharField(max_length=64, unique=True, null=True, blank=True)
    selling_price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'unit_name'], name='unique_unit_per_product'
            )
        ]

    def __str__(self):
        return f'{self.product.name} - {self.unit_name}'


class PriceTier(models.Model):
    product_unit = models.ForeignKey(
        ProductUnit, on_delete=models.CASCADE, related_name='tiers'
    )
    min_qty = models.DecimalField(
        max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))]
    )
    price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )

    class Meta:
        ordering = ['product_unit', 'min_qty']

    def __str__(self):
        return f'{self.min_qty} x {self.product_unit} for P{self.price}'


class Supplier(models.Model):
    name = models.CharField(max_length=150)
    contact = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Restock(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='restocks'
    )
    supplier = models.ForeignKey(
        Supplier, null=True, blank=True, on_delete=models.PROTECT,
        related_name='restocks',
    )
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))]
    )
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=4, validators=[MinValueValidator(ZERO)]
    )
    quantity_remaining = models.DecimalField(max_digits=12, decimal_places=3)
    expiry_date = models.DateField(null=True, blank=True)
    delivery_receipt_no = models.CharField(max_length=50, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='restocks'
    )
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f'{self.product.name} +{self.quantity} on {self.date}'


class StockMovement(models.Model):
    class Type(models.TextChoices):
        SALE = 'sale', 'Sale'
        RESTOCK = 'restock', 'Restock'
        ADJUSTMENT = 'adjustment', 'Adjustment'
        VOID = 'void', 'Void'
        BREAKDOWN = 'breakdown', 'Breakdown'

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='movements'
    )
    type = models.CharField(max_length=12, choices=Type.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    balance_after = models.DecimalField(max_digits=12, decimal_places=3)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='stock_movements'
    )
    reason = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp', '-id']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError('Stock movements are append-only and cannot be edited.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Stock movements cannot be deleted.')

    def __str__(self):
        return f'{self.product.name} {self.type} {self.quantity}'