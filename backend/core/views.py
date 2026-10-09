from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCashierOrOwner, IsOwner

from .serializers import SettingsSerializer
from .services import (
    current_settings, set_credit_limit_mode, set_default_credit_limit, set_idle_minutes,
)

# Create your views here.
class PublicSettingsView(APIView):
    permission_classes = [IsCashierOrOwner]

    def get(self, request):
        return Response(current_settings())


class OwnerSettingsView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        return Response(current_settings())

    def patch(self, request):
        form = SettingsSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        if 'idle_logout_minutes' in data:
            set_idle_minutes(data['idle_logout_minutes'], request.user)
        if 'default_credit_limit' in data:
            set_default_credit_limit(data['default_credit_limit'], request.user)
        if 'credit_limit_mode' in data:
            set_credit_limit_mode(data['credit_limit_mode'], request.user)
        return Response(current_settings())