from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCashierOrOwner

from .models import Receipt, Sale
from .serializers import SaleCreateSerializer
from .services import build_receipt, create_sale, reprint_receipt
from django.utils import timezone
# Create your views here.
class SaleCreateView(APIView):
    permission_classes = [IsCashierOrOwner]

    def post(self, request):
        form = SaleCreateSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data

        sale, warnings = create_sale(
            cashier=request.user,
            items=data['items'],
            payment_type=data['payment_type'],
            cash_received=data['cash_received'],
        )
        return Response(
            {'receipt': build_receipt(sale), 'warnings': warnings},
            status=status.HTTP_201_CREATED,
        )


class ReceiptDetailView(APIView):
    permission_classes = [IsCashierOrOwner]

    def get(self, request, receipt_no):
        receipt = get_object_or_404(Receipt, receipt_no=receipt_no, source=Receipt.Source.SALE)
        sale = get_object_or_404(Sale.objects.select_related('cashier'), pk=receipt.source_id)
        return Response(build_receipt(sale))

class ReceiptReprintView(APIView):
    permission_classes = [IsCashierOrOwner]

    def post(self, request, receipt_no):
        return Response(reprint_receipt(receipt_no, request.user))


class RecentSalesView(APIView):
    permission_classes = [IsCashierOrOwner]

    def get(self, request):
        sales = Sale.objects.select_related('cashier')
        search = request.query_params.get('receipt', '').strip()
        if search:
            sales = sales.filter(receipt_no__icontains=search)

        return Response([
            {
                'receipt_no': s.receipt_no,
                'cashier': s.cashier.username,
                'total': str(s.total),
                'status': s.status,
                'date_time': timezone.localtime(s.timestamp).strftime('%Y-%m-%d %I:%M %p'),
            }
            for s in sales[:30]
        ])