from rest_framework import serializers

from .models import (Category, 
                     PriceTier, 
                     Product, 
                     ProductUnit, 
                     Restock, 
                     StockMovement, 
                     Supplier)
from decimal import Decimal

from django.utils import timezone

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name']


class PriceTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceTier
        fields = ['id', 'product_unit', 'min_qty', 'price']

    def validate(self, attrs):
        unit = attrs.get('product_unit', getattr(self.instance, 'product_unit', None))
        min_qty = attrs.get('min_qty', getattr(self.instance, 'min_qty', None))
        duplicates = PriceTier.objects.filter(product_unit=unit, min_qty=min_qty)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(
                'This unit already has a price tier for that quantity.'
            )
        return attrs


class ProductUnitSerializer(serializers.ModelSerializer):
    tiers = PriceTierSerializer(many=True, read_only=True)

    class Meta:
        model = ProductUnit
        fields = [
            'id', 'product', 'unit_name', 'pieces_per_unit',
            'barcode', 'selling_price', 'tiers',
        ]

    def validate_barcode(self, value):
        return value or None

    def validate_product(self, value):
        if self.instance and value != self.instance.product:
            raise serializers.ValidationError('A unit cannot be moved to another product.')
        return value


class ProductSerializer(serializers.ModelSerializer):
    units = ProductUnitSerializer(many=True, read_only=True)
    stock_status = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'category', 'base_unit', 'cost_price',
            'stock_qty', 'stock_status', 'low_stock_level',
            'photo', 'is_active', 'needs_recount', 'units',
        ]
        
        read_only_fields = ['stock_qty', 'needs_recount']


class ProductLookupSerializer(serializers.ModelSerializer):
    units = ProductUnitSerializer(many=True, read_only=True)
    stock_status = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'base_unit', 'stock_qty', 'stock_status', 'units']

class RestockCreateSerializer(serializers.Serializer):
    
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True)
    )
    product_unit = serializers.PrimaryKeyRelatedField(queryset=ProductUnit.objects.all())
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal('0.001')
    )
    
    unit_cost = serializers.DecimalField(
        max_digits=12, decimal_places=4, min_value=Decimal('0')
    )
    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.all(), required=False, allow_null=True
    )
    date = serializers.DateField(default=timezone.localdate) 
    delivery_receipt_no = serializers.CharField(
        max_length=50, required=False, allow_blank=True, default=''
    )
    expiry_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs['product_unit'].product_id != attrs['product'].id:
            raise serializers.ValidationError(
                {'product_unit': 'That unit does not belong to this product.'}
            )
        expiry = attrs.get('expiry_date')
        if expiry and expiry < attrs['date']:
            raise serializers.ValidationError(
                {'expiry_date': 'Expiry date cannot be before the delivery date.'}
            )
        return attrs


class RestockSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Restock
        fields = [
            'id', 'product', 'supplier', 'quantity', 'unit_cost',
            'quantity_remaining', 'expiry_date', 'delivery_receipt_no',
            'received_by', 'date', 'created_at',
        ]
        read_only_fields = fields

class StockAdjustmentSerializer(serializers.Serializer):
    REASON_CHOICES = ['damaged', 'expired', 'stolen', 'count_error']

    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3) 
    reason_type = serializers.ChoiceField(choices=REASON_CHOICES)
    note = serializers.CharField(max_length=200)  # required, cannot be blank

    def validate(self, attrs):
        if attrs['quantity'] == 0 and attrs['reason_type'] != 'count_error':
            raise serializers.ValidationError({'quantity': 'Quantity cannot be zero.'})
        return attrs


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    user = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            'id', 'product', 'product_name', 'type', 'quantity',
            'balance_after', 'user', 'reason', 'timestamp',
        ]
        read_only_fields = fields