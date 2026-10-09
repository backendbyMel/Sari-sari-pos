from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError, NotFound

from inventory.models import Product, ProductUnit, StockMovement

from .models import Receipt, ReceiptCounter, Sale, SaleItem
from shifts.models import Shift
from utang.credit import check_credit_limit
from utang.models import Customer, UtangPayment

ZERO = Decimal('0')
MONEY = Decimal('0.01')
QTY = Decimal('0.001')
COST_PLACES = Decimal('0.0001')


@transaction.atomic
def next_receipt_no():
    counter, _ = ReceiptCounter.objects.select_for_update().get_or_create(pk=1)
    counter.last_number += 1
    counter.save(update_fields=['last_number'])
    return f'SR-{counter.last_number:06d}'


def price_line(unit, quantity):
    remaining = quantity
    total = ZERO
    for tier in sorted(unit.tiers.all(), key=lambda t: t.min_qty, reverse=True):
        bundles = remaining // tier.min_qty   
        if bundles > 0:
            total += bundles * tier.price
            remaining -= bundles * tier.min_qty
    total += remaining * unit.selling_price   
    return total.quantize(MONEY, ROUND_HALF_UP)


@transaction.atomic
def create_sale(*, cashier, items, payment_type, cash_received=None,
                customer_id=None, confirm_over_limit=False):
    shift = (
        Shift.objects.select_for_update()
        .filter(cashier=cashier, status=Shift.Status.OPEN)
        .first()
    )
    if shift is None:
        raise ValidationError(
            {'shift': 'You have no open shift. Start your shift before selling.'}
        )

    customer = None
    if payment_type == Sale.PaymentType.UTANG:
        if customer_id:
            customer = Customer.objects.select_for_update().filter(pk=customer_id, is_active=True).first()
        if customer is None:
            raise ValidationError({'customer': 'Choose a registered customer for the utang.'})

    wanted = {}
    for line in items:
        unit_id = line['product_unit']
        wanted[unit_id] = wanted.get(unit_id, ZERO) + line['quantity']

    units = {
        u.pk: u
        for u in ProductUnit.objects.filter(pk__in=list(wanted)).prefetch_related('tiers')
    }
    missing = [str(i) for i in wanted if i not in units]
    if missing:
        raise ValidationError({'items': f'Unknown unit id(s): {", ".join(missing)}'})

    product_ids = sorted({u.product_id for u in units.values()})
    products = {
        p.pk: p
        for p in Product.objects.select_for_update().filter(pk__in=product_ids).order_by('pk')
    }
    for unit in units.values():
        if not products[unit.product_id].is_active:
            raise ValidationError(
                {'items': f'{products[unit.product_id].name} is not active and cannot be sold.'}
            )

    lines = []
    total = ZERO
    for unit_id, qty in wanted.items():
        unit = units[unit_id]
        product = products[unit.product_id]
        line_total = price_line(unit, qty)
        lines.append({
            'unit': unit,
            'product': product,
            'quantity': qty,
            'base_qty': (qty * unit.pieces_per_unit).quantize(QTY, ROUND_HALF_UP),
            'unit_cost': (product.cost_price * unit.pieces_per_unit).quantize(
                COST_PLACES, ROUND_HALF_UP
            ),
            'line_total': line_total,
        })
        total += line_total

    
    if customer is not None:
        check_credit_limit(customer, total, confirm_over_limit)  
        cash_received, change = ZERO, ZERO                      
        balance_after = customer.balance + total
    else:
        if cash_received is None:
            raise ValidationError({'cash_received': 'Enter the cash received.'})
        cash_received = cash_received.quantize(MONEY, ROUND_HALF_UP)
        if cash_received < total:
            raise ValidationError(
                {'cash_received': f'Cash received (\u20b1{cash_received}) is less than the total (\u20b1{total}).'}
            )
        change = cash_received - total
        balance_after = None

    receipt_no = next_receipt_no()
    sale = Sale.objects.create(
        receipt_no=receipt_no, cashier=cashier, shift=shift, payment_type=payment_type,
        customer=customer, customer_balance_after=balance_after,
        total=total, discount=ZERO, cash_received=cash_received, change=change,
    )
    if customer is not None:
        customer.balance = balance_after
        customer.save(update_fields=['balance'])

    for line in lines:
        product = line['product']
        SaleItem.objects.create(
            sale=sale, product=product, product_unit=line['unit'],
            quantity=line['quantity'], base_quantity=line['base_qty'],
            unit_price=line['unit'].selling_price, unit_cost=line['unit_cost'],
            line_total=line['line_total'],
        )
        product.stock_qty -= line['base_qty']
        StockMovement.objects.create(
            product=product, type=StockMovement.Type.SALE,
            quantity=-line['base_qty'], balance_after=product.stock_qty,
            user=cashier, reason=f'Sale {receipt_no}',
        )

    warnings = []
    for product in products.values():
        if product.stock_qty < 0:
            product.needs_recount = True
            warnings.append(
                f'{product.name} stock is now {product.stock_qty} {product.base_unit}. '
                f'Please recount.'
            )
        product.save(update_fields=['stock_qty', 'needs_recount'])

    Receipt.objects.create(
        receipt_no=receipt_no, source=Receipt.Source.SALE, source_id=sale.pk
    )
    return sale, warnings


def _qty_text(value):
    return format(value.normalize(), 'f')

def _store_header():
    return dict(settings.STORE)

def build_receipt(sale, *, is_copy=False):
    local_time = timezone.localtime(sale.timestamp) 
    items = sale.items.select_related('product', 'product_unit').order_by('id')
    return {
        'kind': 'sale',
        'receipt_no': sale.receipt_no,
        'store': _store_header(),
        'date_time': local_time.strftime('%Y-%m-%d %I:%M %p'),
        'cashier': sale.cashier.username,
        'items': [
            {
                'name': item.product.name,
                'unit': item.product_unit.unit_name,
                'quantity': _qty_text(item.quantity),
                'price': str(item.unit_price),
                'line_total': str(item.line_total),
            }
            for item in items
        ],
        'discount': str(sale.discount),
        'total': str(sale.total),
        'payment_type': sale.payment_type,
        'cash_received': str(sale.cash_received),
        'change': str(sale.change),
        'customer': {'name': sale.customer.name} if sale.customer_id else None,
        'balance_after': str(sale.customer_balance_after) if sale.customer_id else None,
        'is_void': sale.status == Sale.Status.VOIDED,
        'is_copy': is_copy,
    }


def build_payment_receipt(payment, *, is_copy=False):
    """Receipt for money received on utang. Shows the customer and the REMAINING balance."""
    local_time = timezone.localtime(payment.timestamp)
    return {
        'kind': 'utang_payment',
        'receipt_no': payment.receipt_no,
        'store': _store_header(),
        'date_time': local_time.strftime('%Y-%m-%d %I:%M %p'),
        'cashier': payment.received_by.username,
        'items': [],
        'discount': '0.00',
        'total': str(payment.amount),
        'payment_type': 'utang_payment',
        'cash_received': str(payment.amount),
        'change': '0.00',
        'customer': {'name': payment.customer.name},
        'balance_after': str(payment.balance_after),
        'is_void': False,
        'is_copy': is_copy,
    }


def build_receipt_for(receipt, *, is_copy=False):
    if receipt.source == Receipt.Source.SALE:
        sale = Sale.objects.select_related('cashier', 'customer').get(pk=receipt.source_id)
        return build_receipt(sale, is_copy=is_copy)
    if receipt.source == Receipt.Source.UTANG_PAYMENT:
        payment = UtangPayment.objects.select_related('customer', 'received_by').get(pk=receipt.source_id)
        return build_payment_receipt(payment, is_copy=is_copy)
    raise NotFound('Receipt not found.')


@transaction.atomic
def reprint_receipt(receipt_no, user):
    receipt = Receipt.objects.select_for_update().filter(receipt_no=receipt_no).first()
    if receipt is None:
        raise NotFound('Receipt not found.')
    data = build_receipt_for(receipt, is_copy=True)

    receipt.reprint_log = receipt.reprint_log + [{
        'user': user.username,                                
        'at': timezone.localtime(timezone.now()).isoformat(),  
    }]
    receipt.printed_count += 1
    receipt.save(update_fields=['printed_count', 'reprint_log'])
    return data