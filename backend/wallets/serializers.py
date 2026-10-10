from decimal import Decimal

from rest_framework import serializers

from .models import LoadNetwork, LoadProduct, FeeRule
from .services import get_ewallet


class LoadSendSerializer(serializers.Serializer):
    product = serializers.IntegerField(min_value=1)
    mobile_no = serializers.CharField(max_length=20)
    reference_no = serializers.RegexField(
        r'^[A-Za-z0-9-]{4,30}$',
        error_messages={'invalid': 'The reference number is 4 to 30 letters, digits or dashes, with no spaces.'},
    )
    


class LoadFailSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=200)  


class TopUpSerializer(serializers.Serializer):
    amount_added = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    amount_paid = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'))
    source = serializers.ChoiceField(choices=['drawer', 'owner_cash', 'bank'])
    reference_no = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')

    def validate(self, attrs):
        if attrs['source'] == 'drawer' and attrs['amount_paid'] <= 0:
            raise serializers.ValidationError({'amount_paid': 'Enter the amount taken from the drawer.'})
        return attrs


class WalletAdjustSerializer(serializers.Serializer):
    actual_balance = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'))
    reason = serializers.CharField(max_length=200)  


class LowLevelSerializer(serializers.Serializer):
    low_level = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'))


class LoadNetworkSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoadNetwork
        fields = ['id', 'name', 'rebate_percent', 'is_active']


class LoadProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoadProduct
        fields = ['id', 'network', 'name', 'face_value', 'selling_price', 'is_active']

    def validate_network(self, value):
        if self.instance and value != self.instance.network:
            raise serializers.ValidationError('A product cannot be moved to another network.')
        return value

class EWalletSendSerializer(serializers.Serializer):
    amount = serializers.IntegerField(min_value=1, max_value=1000000)   
    mobile_no = serializers.CharField(max_length=20)
    reference_no = serializers.RegexField(
        r'^[A-Za-z0-9-]{4,30}$',
        error_messages={'invalid': 'The reference number is 4 to 30 letters, digits or dashes, with no spaces.'},
    )
    fee_override = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0'), required=False)
    override_reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')


class EWalletReverseSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=200) 


class FeeRuleSerializer(serializers.ModelSerializer):
    min_amount = serializers.IntegerField(min_value=1, max_value=1000000)
    max_amount = serializers.IntegerField(min_value=1, max_value=1000000)
    fee = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0'))

    class Meta:
        model = FeeRule
        fields = ['id', 'min_amount', 'max_amount', 'fee']

    def validate(self, attrs):
        low = attrs.get('min_amount', getattr(self.instance, 'min_amount', None))
        high = attrs.get('max_amount', getattr(self.instance, 'max_amount', None))
        if high < low:
            raise serializers.ValidationError({'max_amount': 'The upper amount must not be below the lower amount.'})
        wallet = self.instance.wallet if self.instance else get_ewallet()
        clash = FeeRule.objects.filter(wallet=wallet, min_amount__lte=high, max_amount__gte=low)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError('This range overlaps another range in the fee table.')
        return attrs

    def create(self, validated_data):
        validated_data['wallet'] = get_ewallet()
        return super().create(validated_data)