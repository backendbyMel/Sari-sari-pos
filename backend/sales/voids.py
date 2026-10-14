from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from inventory.models import Product, StockMovement
from shifts.models import CashMovement, Shift
from utang.models import Customer

from .models import Sale, VoidRequest

ZERO = Decimal('0')


@transaction.atomic
def request_void(*, user, receipt_no, reason):
    sale = Sale.objects.select_for_update().filter(receipt_no=receipt_no).first()
    if sale is None:
        raise NotFound('No sale has that receipt number. Only sales can be voided here.')
    if sale.status != Sale.Status.COMPLETED:
        raise ValidationError({'sale': 'This sale is already voided.'})
    if VoidRequest.objects.filter(sale=sale, status=VoidRequest.Status.PENDING).exists():
        raise ValidationError({'sale': 'A void request for this sale is already waiting for the owner.'})
    try:
        with transaction.atomic():
            return VoidRequest.objects.create(sale=sale, requested_by=user, reason=reason)
    except IntegrityError:
        raise ValidationError({'sale': 'A void request for this sale already exists.'})


@transaction.atomic
def approve_void(*, owner, void_id, note=''):
    first = VoidRequest.objects.filter(pk=void_id).first()
    if first is None:
        raise NotFound('Void request not found.')
    open_shift = Shift.objects.select_for_update().filter(status=Shift.Status.OPEN).first()
    sale = Sale.objects.select_for_update().get(pk=first.sale_id)
    void = VoidRequest.objects.select_for_update().get(pk=void_id)
    if void.status != VoidRequest.Status.PENDING:
        raise ValidationError({'void': 'This request was already decided.'})
    if sale.status != Sale.Status.COMPLETED:
        raise ValidationError({'void': 'This sale is already voided.'})

    refund, refund_shift, customer = ZERO, None, None
    if sale.payment_type == Sale.PaymentType.UTANG:
        customer = Customer.objects.select_for_update().get(pk=sale.customer_id)
        if customer.balance < sale.total:
            raise ValidationError({'void': (
                f'{customer.name} owes only \u20b1{customer.balance}, less than this sale '
                f'(\u20b1{sale.total}), because they already paid part of their debt. '
                'The balance cannot go below zero, so this void cannot be approved.')})
    elif open_shift is None or sale.shift_id != open_shift.pk:
        if open_shift is None:
            raise ValidationError({'shift': (
                'The cash must be refunded from a shift that is open. Ask a cashier to '
                'start a shift, then approve again.')})
        refund, refund_shift = sale.total, open_shift

    items = list(sale.items.all())
    product_ids = sorted({i.product_id for i in items})
    products = {p.pk: p for p in Product.objects.select_for_update().filter(pk__in=product_ids).order_by('pk')}
    for item in items:
        product = products[item.product_id]
        product.stock_qty += item.base_quantity
        StockMovement.objects.create(
            product=product, type=StockMovement.Type.VOID, quantity=item.base_quantity,
            balance_after=product.stock_qty, user=owner, reason=f'Void {sale.receipt_no}')
    for product in products.values():
        product.save(update_fields=['stock_qty'])

    if customer is not None:
        customer.balance -= sale.total
        customer.save(update_fields=['balance'])
    if refund > 0:
        CashMovement.objects.create(
            shift=refund_shift, type=CashMovement.Type.OUT, amount=refund,
            reason=f'Refund: void of {sale.receipt_no}', recorded_by=owner)

    now = timezone.now()
    sale.status = Sale.Status.VOIDED
    sale.voided_at = now
    sale.save(update_fields=['status', 'voided_at'])

    void.status = VoidRequest.Status.APPROVED
    void.decided_by, void.decision_note, void.decided_at = owner, note, now
    void.refund_amount, void.refund_shift = refund, refund_shift
    void.save()
    return void


@transaction.atomic
def reject_void(*, owner, void_id, note):
    void = VoidRequest.objects.select_for_update().filter(pk=void_id).first()
    if void is None:
        raise NotFound('Void request not found.')
    if void.status != VoidRequest.Status.PENDING:
        raise ValidationError({'void': 'This request was already decided.'})
    void.status = VoidRequest.Status.REJECTED
    void.decided_by, void.decision_note, void.decided_at = owner, note, timezone.now()
    void.save()
    return void