from django.shortcuts import render
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCashierOrOwner

from .models import Receipt, Sale
from .serializers import SaleCreateSerializer
from .services import build_receipt, create_sale

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