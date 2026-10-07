from rest_framework import serializers

from .models import Category, PriceTier, Product, ProductUnit


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