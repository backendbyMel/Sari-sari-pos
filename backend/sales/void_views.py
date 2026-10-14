from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCashierOrOwner, IsOwner

from .models import VoidRequest
from .serializers import VoidApproveSerializer, VoidRejectSerializer, VoidRequestSerializer
from .voids import approve_void, reject_void, request_void


def cashier_row(v):
    return {'id': v.pk, 'receipt_no': v.sale.receipt_no, 'total': str(v.sale.total), 'reason': v.reason,
            'status': v.status, 'decision_note': v.decision_note,
            'requested_at': v.requested_at, 'decided_at': v.decided_at}


def owner_row(v):
    s = v.sale
    return {
        'id': v.pk, 'receipt_no': s.receipt_no, 'total': str(s.total), 'payment_type': s.payment_type,
        'customer': s.customer.name if s.customer_id else None, 'sold_by': s.cashier.username,
        'sold_at': s.timestamp, 'sale_shift': s.shift_id, 'requested_by': v.requested_by.username,
        'reason': v.reason, 'status': v.status, 'decided_by': v.decided_by.username if v.decided_by_id else None,
        'decision_note': v.decision_note, 'requested_at': v.requested_at, 'decided_at': v.decided_at,
        'refund_amount': str(v.refund_amount), 'refund_shift': v.refund_shift_id,
    }


def fetch(pk):
    return VoidRequest.objects.select_related(
        'sale__cashier', 'sale__customer', 'requested_by', 'decided_by').get(pk=pk)


class VoidRequestView(APIView):
    permission_classes = [IsCashierOrOwner]

    def post(self, request, receipt_no):
        form = VoidRequestSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        void = request_void(user=request.user, receipt_no=receipt_no, reason=form.validated_data['reason'])
        return Response(cashier_row(fetch(void.pk)), status=status.HTTP_201_CREATED)


class MyVoidsView(APIView):
    permission_classes = [IsCashierOrOwner]

    def get(self, request):
        rows = VoidRequest.objects.filter(requested_by=request.user).select_related('sale')[:30]
        return Response([cashier_row(v) for v in rows])


class OwnerVoidListView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        chosen = request.query_params.get('status', 'pending')
        if chosen not in ('pending', 'approved', 'rejected', 'all'):
            raise ValidationError({'status': 'Use pending, approved, rejected or all.'})
        rows = VoidRequest.objects.select_related('sale__cashier', 'sale__customer', 'requested_by', 'decided_by')
        if chosen != 'all':
            rows = rows.filter(status=chosen)
        return Response({
            'pending_count': VoidRequest.objects.filter(status='pending').count(),
            'requests': [owner_row(v) for v in rows[:100]],
        })


class VoidApproveView(APIView):
    permission_classes = [IsOwner]

    def post(self, request, pk):
        form = VoidApproveSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        approve_void(owner=request.user, void_id=pk, note=form.validated_data['note'])
        return Response(owner_row(fetch(pk)))


class VoidRejectView(APIView):
    permission_classes = [IsOwner]

    def post(self, request, pk):
        form = VoidRejectSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        reject_void(owner=request.user, void_id=pk, note=form.validated_data['note'])
        return Response(owner_row(fetch(pk)))