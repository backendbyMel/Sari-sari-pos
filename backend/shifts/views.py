from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCashierOrOwner

from .models import Shift
from .serializers import ShiftSerializer, ShiftStartSerializer
from .services import start_shift

# Create your views here.
class ShiftStartView(APIView):
    """POST /api/shifts/start/  (Cashier+)"""
    permission_classes = [IsCashierOrOwner]

    def post(self, request):
        form = ShiftStartSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        shift = start_shift(
            cashier=request.user,   
            opening_cash=form.validated_data['opening_cash'],
        )
        return Response(ShiftSerializer(shift).data, status=status.HTTP_201_CREATED)


class CurrentShiftView(APIView):
    permission_classes = [IsCashierOrOwner]

    def get(self, request):
        shift = Shift.objects.select_related('cashier').filter(status=Shift.Status.OPEN).first()
        return Response({
            'shift': ShiftSerializer(shift).data if shift else None,
            'is_mine': bool(shift and shift.cashier_id == request.user.id),
        })