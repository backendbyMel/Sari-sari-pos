from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCashierOrOwner
from core.services import get_default_credit_limit
from sales.models import Sale
from sales.services import build_payment_receipt

from .models import Customer, UtangPayment
from .serializers import CustomerCreateSerializer, CustomerSerializer, PaymentCreateSerializer
from .services import record_payment, register_customer

# Create your views here.
def serialize(customers, many=False):
    return CustomerSerializer(
        customers, many=many, context={'default_limit': get_default_credit_limit()}
    ).data


class CustomerListCreateView(APIView):
    permission_classes = [IsCashierOrOwner]

    def get(self, request):
        customers = Customer.objects.filter(is_active=True)
        q = request.query_params.get('q', '').strip()
        if q:
            customers = customers.filter(Q(name__icontains=q) | Q(contact__icontains=q))
        return Response(serialize(customers[:30], many=True))

    def post(self, request):
        form = CustomerCreateSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        customer = register_customer(user=request.user, **form.validated_data)
        return Response(serialize(customer), status=status.HTTP_201_CREATED)


class CustomerDetailView(APIView):
    permission_classes = [IsCashierOrOwner]

    def get(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        charges = Sale.objects.filter(
            customer=customer, payment_type=Sale.PaymentType.UTANG
        ).select_related('cashier').order_by('-timestamp')[:50]
        payments = UtangPayment.objects.filter(customer=customer).select_related('received_by')[:50]

        history = [
            {'kind': 'charge', 'receipt_no': s.receipt_no, 'amount': str(s.total),
             'balance_after': str(s.customer_balance_after), 'status': s.status,
             'by': s.cashier.username, 'timestamp': s.timestamp}
            for s in charges
        ] + [
            {'kind': 'payment', 'receipt_no': p.receipt_no, 'amount': str(p.amount),
             'balance_after': str(p.balance_after), 'status': 'completed',
             'by': p.received_by.username, 'timestamp': p.timestamp}
            for p in payments
        ]
        history.sort(key=lambda h: h['timestamp'], reverse=True)
        return Response({'customer': serialize(customer), 'history': history[:50]})


class UtangPaymentView(APIView):
    permission_classes = [IsCashierOrOwner]

    def post(self, request):
        form = PaymentCreateSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        payment = record_payment(
            user=request.user,
            customer_id=form.validated_data['customer'],
            amount=form.validated_data['amount'],
        )
        payment = UtangPayment.objects.select_related('customer', 'received_by').get(pk=payment.pk)
        return Response(
            {'receipt': build_payment_receipt(payment), 'customer': serialize(payment.customer)},
            status=status.HTTP_201_CREATED,
        )