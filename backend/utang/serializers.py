from decimal import Decimal

from rest_framework import serializers

from .credit import effective_limit
from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    credit_limit = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = ['id', 'name', 'contact', 'balance', 'credit_limit']
        read_only_fields = fields

    def get_credit_limit(self, obj):
        return str(effective_limit(obj, self.context.get('default_limit')))


class CustomerCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    contact = serializers.CharField(max_length=150)


class PaymentCreateSerializer(serializers.Serializer):
    customer = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))