from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from django.db.models import Sum

from sales.models import Receipt, Sale
from sales.services import next_receipt_no
from shifts.models import Shift

from .models import BadDebtWriteOff, Customer, UtangPayment

ZERO = Decimal('0')


def register_customer(*, user, name, contact):
    if Customer.objects.filter(name__iexact=name, contact__iexact=contact).exists():
        raise ValidationError({'name': 'This customer is already registered. Search for them instead.'})
    return Customer.objects.create(name=name, contact=contact, created_by=user)


@transaction.atomic
def record_payment(*, user, customer_id, amount):
    shift = (
        Shift.objects.select_for_update()
        .filter(cashier=user, status=Shift.Status.OPEN)
        .first()
    )
    if shift is None:
        raise ValidationError({'shift': 'You have no open shift. Start your shift before taking a payment.'})

    customer = Customer.objects.select_for_update().filter(pk=customer_id).first()
    if customer is None:
        raise NotFound('Customer not found.')
    if customer.balance <= 0:
        raise ValidationError({'amount': f'{customer.name} owes nothing.'})
    if amount > customer.balance:
        raise ValidationError({
            'amount': f'The payment (\u20b1{amount}) is more than the balance (\u20b1{customer.balance}).'
        })

    customer.balance -= amount
    customer.save(update_fields=['balance'])

    receipt_no = next_receipt_no()
    payment = UtangPayment.objects.create(
        customer=customer, amount=amount, balance_after=customer.balance,
        received_by=user, shift=shift, receipt_no=receipt_no,
    )
    Receipt.objects.create(
        receipt_no=receipt_no, source=Receipt.Source.UTANG_PAYMENT, source_id=payment.pk
    )
    return payment


@transaction.atomic
def write_off(*, user, customer_id, amount, reason):
    customer = Customer.objects.select_for_update().filter(pk=customer_id).first()
    if customer is None:
        raise NotFound('Customer not found.')
    if customer.balance <= 0:
        raise ValidationError({'amount': f'{customer.name} owes nothing.'})
    if amount > customer.balance:
        raise ValidationError({
            'amount': f'The write-off (\u20b1{amount}) is more than the balance (\u20b1{customer.balance}).'
        })
    customer.balance -= amount
    customer.save(update_fields=['balance'])
    return BadDebtWriteOff.objects.create(
        customer=customer, amount=amount, balance_after=customer.balance,
        reason=reason, written_off_by=user,
    )


def unpaid_ages(customers, days):
    owing = [c for c in customers if c.balance > 0]
    ids = [c.pk for c in owing]
    if not ids:
        return {}
    paid = dict(UtangPayment.objects.filter(customer_id__in=ids)
                .values_list('customer_id').annotate(t=Sum('amount')).order_by('customer_id'))
    written = dict(BadDebtWriteOff.objects.filter(customer_id__in=ids)
                   .values_list('customer_id').annotate(t=Sum('amount')).order_by('customer_id'))
    charges = {}
    rows = (
        Sale.objects.filter(customer_id__in=ids, payment_type=Sale.PaymentType.UTANG,
                            status=Sale.Status.COMPLETED)
        .order_by('timestamp', 'id').values_list('customer_id', 'total', 'timestamp')
    )
    for customer_id, total, moment in rows:
        charges.setdefault(customer_id, []).append((total, moment))

    now = timezone.now()
    result = {}
    for customer in owing:
        credit = paid.get(customer.pk, ZERO) + written.get(customer.pk, ZERO)
        oldest = None
        for total, moment in charges.get(customer.pk, []):
            if credit >= total:
                credit -= total
            else:
                oldest = moment
                break
        result[customer.pk] = {
            'oldest': oldest,
            'overdue': oldest is not None and now - oldest > timedelta(days=days),
        }
    return result


def history_for(customer, *, include_reason=False):
    charges = Sale.objects.filter(
        customer=customer, payment_type=Sale.PaymentType.UTANG
    ).select_related('cashier').order_by('-timestamp')[:50]
    payments = UtangPayment.objects.filter(customer=customer).select_related('received_by')[:50]
    writeoffs = BadDebtWriteOff.objects.filter(customer=customer).select_related('written_off_by')[:50]

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
    for w in writeoffs:
        entry = {'kind': 'writeoff', 'receipt_no': f'WO-{w.pk}', 'amount': str(w.amount),
                 'balance_after': str(w.balance_after), 'status': 'completed',
                 'by': w.written_off_by.username, 'timestamp': w.timestamp}
        if include_reason:
            entry['reason'] = w.reason
        history.append(entry)
    history.sort(key=lambda h: h['timestamp'], reverse=True)
    return history[:50]