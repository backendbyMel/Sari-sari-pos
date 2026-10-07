from decimal import Decimal

from rest_framework import serializers


class SaleLineSerializer(serializers.Serializer):
    product_unit = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal('0.001')
    )
    

class SaleCreateSerializer(serializers.Serializer):
    items = SaleLineSerializer(many=True, allow_empty=False)
    payment_type = serializers.ChoiceField(choices=['cash'], default='cash')
    cash_received = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0')
    )