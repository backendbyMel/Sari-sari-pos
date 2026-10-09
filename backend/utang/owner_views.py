from decimal import Decimal

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsOwner
from core.services import get_default_credit_limit, get_overdue_days

from .credit import effective_limit
from .models import Customer
from .serializers import OwnerCustomerPatchSerializer, WriteOffSerializer
from .services import history_for, unpaid_ages, write_off


def money(value):
    return str(Decimal(value).quantize(Decimal('0.01')))


def owner_row(customer, info, default_limit):
    entry = info.get(customer.pk)
    oldest = entry['oldest'] if entry else None
    return {
        'id': customer.pk,
        'name': customer.name,
        'contact': customer.contact,
        'balance': money(customer.balance),
        'credit_limit': money(effective_limit(customer, default_limit)),          # what applies now
        'personal_limit': money(customer.credit_limit) if customer.credit_limit is not None else None,
        'is_active': customer.is_active,
        'oldest_unpaid': oldest,
        'days_unpaid': (timezone.now() - oldest).days if oldest else None,
        'overdue': bool(entry and entry['overdue']),
    }


class OwnerCustomerListView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        days = get_overdue_days()
        default_limit = get_default_credit_limit()
        everyone = list(Customer.objects.all())
        info = unpaid_ages(everyone, days)
        rows = [owner_row(c, info, default_limit) for c in everyone]

        summary = {
            'total_unpaid': money(sum((c.balance for c in everyone), Decimal('0'))),
            'owing_count': sum(1 for c in everyone if c.balance > 0),
            'overdue_count': sum(1 for r in rows if r['overdue']),
            'overdue_days': days,
        }

        chosen = request.query_params.get('filter', 'all')
        if chosen == 'owing':
            rows = [r for r in rows if Decimal(r['balance']) > 0]
        elif chosen == 'overdue':
            rows = [r for r in rows if r['overdue']]
        q = request.query_params.get('q', '').strip().lower()
        if q:
            rows = [r for r in rows if q in r['name'].lower() or q in r['contact'].lower()]

        rows.sort(key=lambda r: (not r['overdue'], -Decimal(r['balance']), r['name'].lower()))
        return Response({'summary': summary, 'customers': rows})


class OwnerCustomerDetailView(APIView):
    permission_classes = [IsOwner]

    def payload(self, customer):
        days = get_overdue_days()
        info = unpaid_ages([customer], days)
        return {
            'customer': owner_row(customer, info, get_default_credit_limit()),
            'history': history_for(customer, include_reason=True),
            'overdue_days': days,
        }

    def get(self, request, pk):
        return Response(self.payload(get_object_or_404(Customer, pk=pk)))

    def patch(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        form = OwnerCustomerPatchSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        if data.get('is_active') is False and customer.balance > 0:
            raise ValidationError({
                'is_active': f'{customer.name} still owes \u20b1{customer.balance}. '
                             'Collect it or write it off before deactivating.'
            })
        for field in ('credit_limit', 'is_active'):
            if field in data:
                setattr(customer, field, data[field])
        customer.save(update_fields=[f for f in ('credit_limit', 'is_active') if f in data])
        return Response(self.payload(customer))


class WriteOffView(APIView):
    permission_classes = [IsOwner]

    def post(self, request, pk):
        form = WriteOffSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        write_off(
            user=request.user,  
            customer_id=pk,
            amount=form.validated_data['amount'],
            reason=form.validated_data['reason'],
        )
        customer = get_object_or_404(Customer, pk=pk)
        return Response(OwnerCustomerDetailView().payload(customer), status=status.HTTP_201_CREATED)