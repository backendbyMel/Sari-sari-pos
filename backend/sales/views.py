from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCashierOrOwner

from .models import Receipt, Sale
from .serializers import SaleCreateSerializer
from .services import build_receipt, create_sale, reprint_receipt, build_receipt_for
from django.utils import timezone
from utang.models import UtangPayment
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
            cash_received=data.get('cash_received'),
            customer_id=data.get('customer'),
            confirm_over_limit=data['confirm_over_limit'],
        )
        sale = Sale.objects.select_related('cashier', 'customer').get(pk=sale.pk)
        return Response(
            {'receipt': build_receipt(sale), 'warnings': warnings},
            status=status.HTTP_201_CREATED,
        )
class ReceiptDetailView(APIView):
    permission_classes = [IsCashierOrOwner]

    def get(self, request, receipt_no):
        receipt = get_object_or_404(Receipt, receipt_no=receipt_no)
        return Response(build_receipt_for(receipt))

class ReceiptReprintView(APIView):
    permission_classes = [IsCashierOrOwner]

    def post(self, request, receipt_no):
        return Response(reprint_receipt(receipt_no, request.user))


class RecentSalesView(APIView):
    permission_classes = [IsCashierOrOwner]

    def get(self, request):
        receipts = Receipt.objects.all()
        search = request.query_params.get('receipt', '').strip()
        if search:
            receipts = receipts.filter(receipt_no__icontains=search)
        receipts = list(receipts.order_by('-id')[:30])

        sales = Sale.objects.select_related('cashier').in_bulk(
            [r.source_id for r in receipts if r.source == Receipt.Source.SALE])
        payments = UtangPayment.objects.select_related('received_by').in_bulk(
            [r.source_id for r in receipts if r.source == Receipt.Source.UTANG_PAYMENT])

        rows = []
        for r in receipts:
            if r.source == Receipt.Source.SALE and r.source_id in sales:
                s = sales[r.source_id]
                rows.append({'receipt_no': s.receipt_no, 'cashier': s.cashier.username,
                             'total': str(s.total), 'status': s.status, 'kind': 'sale',
                             'date_time': timezone.localtime(s.timestamp).strftime('%Y-%m-%d %I:%M %p')})
            elif r.source == Receipt.Source.UTANG_PAYMENT and r.source_id in payments:
                p = payments[r.source_id]
                rows.append({'receipt_no': p.receipt_no, 'cashier': p.received_by.username,
                             'total': str(p.amount), 'status': 'completed', 'kind': 'utang_payment',
                             'date_time': timezone.localtime(p.timestamp).strftime('%Y-%m-%d %I:%M %p')})
        return Response(rows)