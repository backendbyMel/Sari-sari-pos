from decimal import Decimal

from rest_framework import serializers

from .services import CREDIT_MODES, MAX_IDLE_MINUTES, MIN_IDLE_MINUTES


class SettingsSerializer(serializers.Serializer):
    idle_logout_minutes = serializers.IntegerField(
        min_value=MIN_IDLE_MINUTES, max_value=MAX_IDLE_MINUTES, required=False
    )
    default_credit_limit = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0'), required=False
    )
    credit_limit_mode = serializers.ChoiceField(choices=list(CREDIT_MODES), required=False)