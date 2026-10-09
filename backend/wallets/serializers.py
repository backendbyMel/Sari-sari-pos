from decimal import Decimal

from rest_framework import serializers

from .models import LoadNetwork, LoadProduct


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