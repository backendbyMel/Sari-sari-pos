from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from inventory.models import Product, ProductUnit, StockMovement

from .models import Receipt, ReceiptCounter, Sale, SaleItem

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
def create_sale(*, cashier, items, payment_type, cash_received):
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

    cash_received = cash_received.quantize(MONEY, ROUND_HALF_UP)
    if cash_received < total:
        raise ValidationError(
            {'cash_received': f'Cash received (₱{cash_received}) is less than the total (₱{total}).'}
        )

    receipt_no = next_receipt_no()
    sale = Sale.objects.create(
        receipt_no=receipt_no, cashier=cashier, payment_type=payment_type,
        total=total, discount=ZERO, cash_received=cash_received,
        change=cash_received - total,
    )

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


def build_receipt(sale, *, is_copy=False):
    local_time = timezone.localtime(sale.timestamp)  # Asia/Manila
    items = sale.items.select_related('product', 'product_unit').order_by('id')
    return {
        'receipt_no': sale.receipt_no,
        'store': dict(settings.STORE),
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
        'is_void': sale.status == Sale.Status.VOIDED,
        'is_copy': is_copy,
    }