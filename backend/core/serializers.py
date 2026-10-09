from decimal import Decimal

from rest_framework import serializers

from .services import CREDIT_MODES, MAX_IDLE_MINUTES, MIN_IDLE_MINUTES, MAX_OVERDUE_DAYS, MIN_OVERDUE_DAYS


class SettingsSerializer(serializers.Serializer):
    idle_logout_minutes = serializers.IntegerField(
        min_value=MIN_IDLE_MINUTES, max_value=MAX_IDLE_MINUTES, required=False
    )
    default_credit_limit = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0'), required=False
    )
    credit_limit_mode = serializers.ChoiceField(choices=list(CREDIT_MODES), required=False)

    overdue_days = serializers.IntegerField(
        min_value=MIN_OVERDUE_DAYS, max_value=MAX_OVERDUE_DAYS, required=False
    )
    cashier_can_topup = serializers.BooleanField(required=False)