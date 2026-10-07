from decimal import Decimal

from rest_framework import serializers

from .models import Shift


class ShiftStartSerializer(serializers.Serializer):
    opening_cash = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0')
    )


class ShiftSerializer(serializers.ModelSerializer):
    cashier = serializers.CharField(source='cashier.username', read_only=True)

    class Meta:
        model = Shift
        fields = ['id', 'cashier', 'status', 'start_time', 'opening_cash']
        read_only_fields = fields