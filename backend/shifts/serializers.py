from decimal import Decimal

from rest_framework import serializers

from .models import Shift, CashMovement
import re

BILLS = ['1000', '500', '200', '100', '50', '20']

class ShiftStartSerializer(serializers.Serializer):
    opening_cash = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0')
    )
    wallet_balances = serializers.DictField(
        child=serializers.CharField(allow_blank=True), required=False
    )


class ShiftSerializer(serializers.ModelSerializer):
    cashier = serializers.CharField(source='cashier.username', read_only=True)

    class Meta:
        model = Shift
        fields = ['id', 'cashier', 'status', 'start_time', 'opening_cash']
        read_only_fields = fields


class ShiftResultSerializer(serializers.ModelSerializer):
    cashier = serializers.CharField(source='cashier.username', read_only=True)
    closed_by = serializers.SerializerMethodField()
    closed_on_behalf = serializers.SerializerMethodField()

    class Meta:
        model = Shift
        fields = [
            'id', 'cashier', 'status', 'start_time', 'end_time', 'opening_cash',
            'expected_cash', 'counted_cash', 'variance', 'denominations',
            'closed_by', 'closed_on_behalf', 'close_reason',
        ]
        read_only_fields = fields

    def get_closed_by(self, obj):
        return obj.closed_by.username if obj.closed_by else None

    def get_closed_on_behalf(self, obj):
        return bool(obj.closed_by_id and obj.closed_by_id != obj.cashier_id)


class OwnerShiftSerializer(ShiftResultSerializer):
    reopen_count = serializers.IntegerField(read_only=True)   

    class Meta(ShiftResultSerializer.Meta):
        fields = ShiftResultSerializer.Meta.fields + [
            'previous_closing_cash', 'opening_difference', 'reopen_count',
        ]
        read_only_fields = fields


class ShiftEndSerializer(serializers.Serializer):
    counted_cash = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0'), required=False
    )
    denominations = serializers.DictField(child=serializers.CharField(), required=False)
    wallet_balances = serializers.DictField(
        child=serializers.CharField(allow_blank=True), required=False
    )
    
    def validate_denominations(self, value):
        clean = {}
        for key, raw in value.items():
            raw = str(raw)
            if key in BILLS:                                 
                if not re.fullmatch(r'\d{1,6}', raw):
                    raise serializers.ValidationError(f'The count of {key}-peso bills must be a whole number.')
                clean[key] = int(raw)
            elif key == 'coins':                            
                if not re.fullmatch(r'\d{1,9}(\.\d{1,2})?', raw):
                    raise serializers.ValidationError('Coins must be an amount like 35.50.')
                clean[key] = str(Decimal(raw))
            else:
                raise serializers.ValidationError(f'Unknown denomination "{key}".')
        return clean

    def validate(self, attrs):
        denominations = attrs.get('denominations')
        if denominations:
            total = Decimal('0')
            for key, value in denominations.items():
                total += Decimal(value) if key == 'coins' else Decimal(key) * value
            total = total.quantize(Decimal('0.01'))
            given = attrs.get('counted_cash')
            if given is not None and given != total:
                raise serializers.ValidationError(
                    {'counted_cash': f'The total ({given}) does not match the breakdown ({total}).'}
                )
            attrs['counted_cash'] = total      
        elif attrs.get('counted_cash') is None:
            raise serializers.ValidationError('Enter the counted cash or the denomination breakdown.')
        return attrs


class ShiftOwnerCloseSerializer(ShiftEndSerializer):
    reason = serializers.CharField(max_length=200)    


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200)


class PayoutCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0.01')
    )
    reason = serializers.CharField(max_length=200)   # required, cannot be blank


class CashMovementSerializer(serializers.ModelSerializer):
    recorded_by = serializers.CharField(source='recorded_by.username', read_only=True)

    class Meta:
        model = CashMovement
        fields = ['id', 'type', 'amount', 'reason', 'recorded_by', 'timestamp']
        read_only_fields = fields