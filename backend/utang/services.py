from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from sales.models import Receipt
from sales.services import next_receipt_no
from shifts.models import Shift

from .models import Customer, UtangPayment


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