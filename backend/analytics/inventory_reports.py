from decimal import ROUND_HALF_UP, Decimal

from django.db.models import F, Q
from django.utils import timezone

from inventory.models import Product, ProductUnit, Restock

from .services import ZERO, money, num

COST_PLACES = Decimal('0.0001')
NO_CATEGORY = '(no category)'


def money4(value):
    return str(Decimal(value).quantize(COST_PLACES, ROUND_HALF_UP))


def inventory_value():
    products = Product.objects.filter(Q(is_active=True) | Q(stock_qty__gt=0)).select_related('category')
    rows, categories = [], {}
    total, negative = ZERO, 0
    for p in products:
        counted = max(p.stock_qty, ZERO)
        value = counted * p.cost_price
        category = p.category.name if p.category_id else NO_CATEGORY
        total += value
        if p.stock_qty < 0:
            negative += 1
        entry = categories.setdefault(category, {'items': 0, 'value': ZERO})
        entry['items'] += 1
        entry['value'] += value
        rows.append({
            'id': p.pk, 'name': p.name, 'category': category, 'stock': num(p.stock_qty),
            'unit': p.base_unit, 'cost': money4(p.cost_price), 'value': money(value),
            'is_active': p.is_active, 'negative': p.stock_qty < 0,
        })
    rows.sort(key=lambda r: (r['category'] == NO_CATEGORY, r['category'].lower(), r['name'].lower()))
    summary = [{'category': name, 'items': v['items'], 'value': money(v['value'])}
               for name, v in categories.items()]
    summary.sort(key=lambda c: (-Decimal(c['value']), c['category'].lower()))
    return {
        'total_value': money(total), 'item_count': len(rows), 'negative_count': negative,
        'categories': summary, 'items': rows,
    }


def shopping_list():
    products = list(
        Product.objects.filter(
            is_active=True, stock_qty__lte=F('low_stock_level'),
            pk__in=ProductUnit.objects.values('product_id'),
        ).select_related('category')
    )
    last = {}
    deliveries = (Restock.objects.filter(product_id__in=[p.pk for p in products])
                  .order_by('product_id', '-date', '-id').values('product_id', 'date', 'quantity'))
    for r in deliveries:
        last.setdefault(r['product_id'], r)         

    rows = []
    for p in products:
        d = last.get(p.pk)
        rows.append({
            'id': p.pk, 'name': p.name,
            'category': p.category.name if p.category_id else NO_CATEGORY,
            'stock': num(p.stock_qty), 'unit': p.base_unit, 'low_level': num(p.low_stock_level),
            'status': 'out' if p.stock_qty <= 0 else 'low', 'needs_recount': p.needs_recount,
            'last_bought': d['date'].isoformat() if d else None,
            'last_quantity': num(d['quantity']) if d else None,
        })
    rows.sort(key=lambda r: (r['status'] != 'out', r['category'] == NO_CATEGORY,
                             r['category'].lower(), r['name'].lower()))
    return {'date': timezone.localdate().isoformat(), 'count': len(rows), 'items': rows}