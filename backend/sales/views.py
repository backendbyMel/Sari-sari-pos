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
from wallets.models import LoadTransaction
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

        def ids(source):
            return [r.source_id for r in receipts if r.source == source]

        sales = Sale.objects.select_related('cashier').in_bulk(ids(Receipt.Source.SALE))
        payments = UtangPayment.objects.select_related('received_by').in_bulk(ids(Receipt.Source.UTANG_PAYMENT))
        loads = LoadTransaction.objects.select_related('cashier').in_bulk(ids(Receipt.Source.LOAD))

        def when(moment):
            return timezone.localtime(moment).strftime('%Y-%m-%d %I:%M %p')

        rows = []
        for r in receipts:
            if r.source == Receipt.Source.SALE and r.source_id in sales:
                s = sales[r.source_id]
                rows.append({'receipt_no': s.receipt_no, 'cashier': s.cashier.username, 'total': str(s.total),
                             'status': s.status, 'kind': 'sale', 'date_time': when(s.timestamp)})
            elif r.source == Receipt.Source.UTANG_PAYMENT and r.source_id in payments:
                p = payments[r.source_id]
                rows.append({'receipt_no': p.receipt_no, 'cashier': p.received_by.username, 'total': str(p.amount),
                             'status': 'completed', 'kind': 'utang_payment', 'date_time': when(p.timestamp)})
            elif r.source == Receipt.Source.LOAD and r.source_id in loads:
                t = loads[r.source_id]
                rows.append({'receipt_no': t.receipt_no, 'cashier': t.cashier.username, 'total': str(t.price_charged),
                             'status': 'voided' if t.status == 'failed' else 'completed', 'kind': 'load',
                             'date_time': when(t.timestamp)})
        return Response(rows)