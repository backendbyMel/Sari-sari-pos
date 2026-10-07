from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import Product, Restock, StockMovement

ZERO = Decimal('0')
COST_PLACES = Decimal('0.0001')
QTY_PLACES = Decimal('0.001')


def _price_per_base_unit(product):
    unit = product.units.order_by('pieces_per_unit').first()
    if unit is None:
        return None
    return unit.selling_price / unit.pieces_per_unit


@transaction.atomic
def record_restock(*, product, unit, quantity, unit_cost, supplier, date,
                   delivery_receipt_no, expiry_date, user):
    
    product = Product.objects.select_for_update().get(pk=product.pk)

    
    base_qty = (quantity * unit.pieces_per_unit).quantize(QTY_PLACES, ROUND_HALF_UP)
    if base_qty <= 0:
        raise ValidationError({'quantity': 'Quantity is too small.'})
    cost_per_base = (unit_cost / unit.pieces_per_unit).quantize(COST_PLACES, ROUND_HALF_UP)

    
    old_qty = product.stock_qty
    old_cost = product.cost_price
    counted_qty = max(old_qty, ZERO)
    new_cost = (
        (counted_qty * old_cost + base_qty * cost_per_base) / (counted_qty + base_qty)
    ).quantize(COST_PLACES, ROUND_HALF_UP)

    
    warnings = []
    price = _price_per_base_unit(product)
    if price is not None and old_cost > 0:
        margin_before = price - old_cost
        margin_after = price - new_cost
        if margin_after < margin_before:
            warnings.append(
                f'Margin dropped from ₱{margin_before:.2f} to ₱{margin_after:.2f} '
                f'per {product.base_unit}.'
            )

    
    product.stock_qty = old_qty + base_qty
    product.cost_price = new_cost
    product.save(update_fields=['stock_qty', 'cost_price'])

    
    restock = Restock.objects.create(
        product=product, supplier=supplier, quantity=base_qty,
        unit_cost=cost_per_base, quantity_remaining=base_qty,
        expiry_date=expiry_date, delivery_receipt_no=delivery_receipt_no,
        received_by=user, date=date,
    )
    reason = f'Restock #{restock.id}'
    if delivery_receipt_no:
        reason += f' (DR {delivery_receipt_no})'
    StockMovement.objects.create(
        product=product, type=StockMovement.Type.RESTOCK, quantity=base_qty,
        balance_after=product.stock_qty, user=user, reason=reason,
    )

    return {'restock': restock, 'product': product,
            'old_cost': old_cost, 'warnings': warnings}