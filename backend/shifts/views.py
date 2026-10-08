from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCashierOrOwner, IsOwner

from .models import Shift
from .serializers import (
    OwnerShiftSerializer, ReasonSerializer, ShiftEndSerializer, ShiftOwnerCloseSerializer,
    ShiftResultSerializer, ShiftSerializer, ShiftStartSerializer,
)
from .services import close_shift, reopen_shift, start_shift
from django.db.models import Count
from rest_framework.exceptions import ValidationError
# Create your views here.

def result_payload(shift, totals):
    return {
        'shift': ShiftResultSerializer(shift).data,
        'sales_count': totals['sales_count'],
        'cash_sales': str(totals['cash_sales']), 
    }

class ShiftStartView(APIView):
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

class ShiftEndView(APIView):
    """POST /api/shifts/end/  (Cashier+). Ends the caller's OWN open shift."""
    permission_classes = [IsCashierOrOwner]

    def post(self, request):
        form = ShiftEndSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data

        shift = Shift.objects.filter(cashier=request.user, status=Shift.Status.OPEN).first()
        if shift is None:
            raise ValidationError({'shift': 'You have no open shift to end.'})

        shift, totals = close_shift(
            shift_id=shift.pk, counted_cash=data['counted_cash'],
            denominations=data.get('denominations'), closed_by=request.user,
        )
        return Response(result_payload(shift, totals))


class ShiftOwnerCloseView(APIView):
    """POST /api/shifts/<id>/close/  (Owner only). Closes ANY open shift, with a reason."""
    permission_classes = [IsOwner]

    def post(self, request, pk):
        form = ShiftOwnerCloseSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        shift, totals = close_shift(
            shift_id=pk, counted_cash=data['counted_cash'],
            denominations=data.get('denominations'), closed_by=request.user,
            reason=data['reason'],
        )
        return Response(result_payload(shift, totals))


class ShiftReopenView(APIView):
    """POST /api/shifts/<id>/reopen/  (Owner only). A reason is required and logged."""
    permission_classes = [IsOwner]

    def post(self, request, pk):
        form = ReasonSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        shift = reopen_shift(shift_id=pk, user=request.user, reason=form.validated_data['reason'])
        return Response(ShiftSerializer(shift).data)


class ShiftListView(APIView):
    """GET /api/shifts/  (Owner only). The latest 30 shifts with every detail."""
    permission_classes = [IsOwner]

    def get(self, request):
        shifts = (
            Shift.objects.select_related('cashier', 'closed_by')
            .annotate(reopen_count=Count('reopens'))
            .order_by('-start_time', '-id')[:30]
        )
        return Response(OwnerShiftSerializer(shifts, many=True).data)