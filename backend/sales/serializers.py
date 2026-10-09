from decimal import Decimal

from rest_framework import serializers

class SaleLineSerializer(serializers.Serializer):
    product_unit = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal('0.001')
    )
    

class SaleCreateSerializer(serializers.Serializer):
    items = SaleLineSerializer(many=True, allow_empty=False)
    payment_type = serializers.ChoiceField(choices=['cash', 'utang'], default='cash')
    cash_received = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0'), required=False
    )
    customer = serializers.IntegerField(min_value=1, required=False)
    confirm_over_limit = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if attrs['payment_type'] == 'cash':
            if 'cash_received' not in attrs:
                raise serializers.ValidationError({'cash_received': 'Enter the cash received.'})
        else:
            if 'customer' not in attrs:
                raise serializers.ValidationError({'customer': 'Choose the customer who is taking the utang.'})
            attrs.pop('cash_received', None)   
        return attrs