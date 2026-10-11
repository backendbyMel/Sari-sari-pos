from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, F, Max, Q, Sum
from django.db.models.functions import ExtractHour, TruncDay, TruncMonth, TruncWeek
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from inventory.models import Product, ProductUnit
from sales.models import Sale, SaleItem
from utang.models import BadDebtWriteOff
from wallets.models import EWalletTransaction, LoadTransaction

from .services import LINE_COST, ZERO, day_bounds, money, num

MAX_DAYS = 366
TRUNC = {'day': TruncDay, 'week': TruncWeek, 'month': TruncMonth}  


def parse_range(params):
    today = timezone.localdate()
    errors = {}

    def read(key, default):
        raw = params.get(key)
        if not raw:
            return default
        try:
            return date.fromisoformat(raw)
        except ValueError:
            errors[key] = 'Use the format YYYY-MM-DD.'
            return default

    d_from = read('date_from', today.replace(day=1))
    d_to = read('date_to', today)
    if errors:
        raise ValidationError(errors)
    if d_to < d_from:
        raise ValidationError({'date_to': 'The end date must not be before the start date.'})
    if (d_to - d_from).days + 1 > MAX_DAYS:
        raise ValidationError({'date_to': f'Choose a range of at most {MAX_DAYS} days.'})
    _, start, _ = day_bounds(d_from)
    _, _, end = day_bounds(d_to)
    return d_from, d_to, start, end


def _period_date(value):
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.date()


def _empty():
    return {'sales_count': 0, 'sales_total': ZERO, 'utang_total': ZERO, 'cost': ZERO,
            'load_sales': ZERO, 'load_profit': ZERO, 'fees': ZERO}


def _add(total, raw):
    for key, value in raw.items():
        total[key] += value


def _finish(raw):
    goods = raw['sales_total'] - raw['cost']
    return {
        'sales_count': raw['sales_count'],
        'sales_total': money(raw['sales_total']),
        'utang_total': money(raw['utang_total']),
        'goods_profit': money(goods),
        'load_sales': money(raw['load_sales']),
        'load_profit': money(raw['load_profit']),
        'fees': money(raw['fees']),
        'profit': money(goods + raw['load_profit'] + raw['fees']),
    }


def _collect(start, end, sale_key, item_key, load_key, ew_key):
    out = {}

    def at(key):
        return out.setdefault(key, _empty())

    sales = Sale.objects.filter(timestamp__gte=start, timestamp__lt=end, status=Sale.Status.COMPLETED)
    for r in (sales.annotate(grp=sale_key).values('grp').order_by()
              .annotate(n=Count('id'), sales_sum=Sum('total'),
                        utang_sum=Sum('total', filter=Q(payment_type=Sale.PaymentType.UTANG)))):
        row = at(r['grp'])
        row['sales_count'] += r['n']
        row['sales_total'] += r['sales_sum'] or ZERO
        row['utang_total'] += r['utang_sum'] or ZERO

    items = SaleItem.objects.filter(
        sale__timestamp__gte=start, sale__timestamp__lt=end, sale__status=Sale.Status.COMPLETED)
    for r in items.annotate(grp=item_key).values('grp').order_by().annotate(cost_sum=Sum(LINE_COST)):
        at(r['grp'])['cost'] += r['cost_sum'] or ZERO

    loads = LoadTransaction.objects.filter(
        timestamp__gte=start, timestamp__lt=end, status=LoadTransaction.Status.SUCCESS)
    for r in (loads.annotate(grp=load_key).values('grp').order_by()
              .annotate(price_sum=Sum('price_charged'), face_sum=Sum('amount'), rebate_sum=Sum('rebate'))):
        row = at(r['grp'])
        row['load_sales'] += r['price_sum'] or ZERO
        row['load_profit'] += (r['price_sum'] or ZERO) - (r['face_sum'] or ZERO) + (r['rebate_sum'] or ZERO)

    gcash = EWalletTransaction.objects.filter(
        timestamp__gte=start, timestamp__lt=end, status=EWalletTransaction.Status.SUCCESS)
    for r in gcash.annotate(grp=ew_key).values('grp').order_by().annotate(fee_sum=Sum('fee')):
        at(r['grp'])['fees'] += r['fee_sum'] or ZERO
    return out


def sales_report(start, end, group):
    trunc = TRUNC[group]
    raw = _collect(start, end, trunc('timestamp'), trunc('sale__timestamp'),
                   trunc('timestamp'), trunc('timestamp'))
    by_period = {_period_date(key): values for key, values in raw.items()}
    rows, total = [], _empty()
    for period in sorted(by_period):
        rows.append({'period': period.isoformat(), **_finish(by_period[period])})
        _add(total, by_period[period])
    written_off = BadDebtWriteOff.objects.filter(
        timestamp__gte=start, timestamp__lt=end).aggregate(w=Sum('amount'))['w']
    return {'rows': rows, 'totals': {**_finish(total), 'writeoffs': money(written_off)}}


def by_cashier(start, end):
    raw = _collect(start, end, F('cashier__username'), F('sale__cashier__username'),
                   F('cashier__username'), F('cashier__username'))
    rows = [{'cashier': name, **_finish(values)} for name, values in raw.items()]
    rows.sort(key=lambda r: (-Decimal(r['profit']), r['cashier']))
    return rows


def by_category(start, end):
    items = SaleItem.objects.filter(
        sale__timestamp__gte=start, sale__timestamp__lt=end, sale__status=Sale.Status.COMPLETED)
    found = (items.annotate(grp=F('product__category__name')).values('grp').order_by()
             .annotate(rev=Sum('line_total'), cost_sum=Sum(LINE_COST)))
    rows = [{'category': r['grp'] or '(no category)', 'sales_total': money(r['rev']),
             'goods_profit': money(r['rev'] - r['cost_sum'])} for r in found]
    rows.sort(key=lambda r: (-Decimal(r['goods_profit']), r['category']))
    return rows


def hourly(start, end):
    sales = Sale.objects.filter(timestamp__gte=start, timestamp__lt=end, status=Sale.Status.COMPLETED)
    found = {
        r['hr']: r for r in (sales.annotate(hr=ExtractHour('timestamp')).values('hr').order_by()
                             .annotate(n=Count('id'), sales_sum=Sum('total')))
    }
    hours = [
        {'hour': h, 'sales_count': found[h]['n'] if h in found else 0,
         'sales_total': money(found[h]['sales_sum'] if h in found else 0)}
        for h in range(24)
    ]
    busiest = max(hours, key=lambda h: (h['sales_count'], Decimal(h['sales_total'])))
    return {'hours': hours, 'busiest_hour': busiest['hour'] if busiest['sales_count'] else None}


def best_sellers(start, end, limit=20):
    items = SaleItem.objects.filter(
        sale__timestamp__gte=start, sale__timestamp__lt=end, sale__status=Sale.Status.COMPLETED)
    found = (items.values('product_id', 'product__name', 'product__base_unit').order_by()
             .annotate(qty_sum=Sum('base_quantity'), rev=Sum('line_total'), cost_sum=Sum(LINE_COST)))
    rows = [{'product': r['product__name'], 'unit': r['product__base_unit'], 'qty': r['qty_sum'],
             'sales': r['rev'], 'profit': r['rev'] - r['cost_sum']} for r in found]

    def shape(row):
        return {'product': row['product'], 'unit': row['unit'], 'quantity': num(row['qty']),
                'sales_total': money(row['sales']), 'profit': money(row['profit'])}

    by_qty = sorted(rows, key=lambda r: (-r['qty'], r['product']))[:limit]
    by_profit = sorted(rows, key=lambda r: (-r['profit'], r['product']))[:limit]
    return {'by_quantity': [shape(r) for r in by_qty], 'by_profit': [shape(r) for r in by_profit]}


def slow_movers(days):
    now = timezone.now()
    cutoff = now - timedelta(days=days)
    sold_recently = SaleItem.objects.filter(
        sale__timestamp__gte=cutoff, sale__status=Sale.Status.COMPLETED).values('product_id')
    products = (
        Product.objects.filter(is_active=True, stock_qty__gt=0, created_at__lt=cutoff,
                               pk__in=ProductUnit.objects.values('product_id'))
        .exclude(pk__in=sold_recently)
        .annotate(last_sold=Max('sale_items__sale__timestamp',
                                filter=Q(sale_items__sale__status=Sale.Status.COMPLETED)))
    )
    rows = [{'id': p.pk, 'name': p.name, 'stock': p.stock_qty, 'unit': p.base_unit,
             'value': p.stock_qty * p.cost_price, 'last_sold': p.last_sold} for p in products]
    rows.sort(key=lambda r: (-r['value'], r['name']))
    return {
        'days': days,
        'count': len(rows),
        'tied_up': money(sum((r['value'] for r in rows), ZERO)),
        'items': [
            {'id': r['id'], 'name': r['name'], 'stock': num(r['stock']), 'unit': r['unit'],
             'value': money(r['value']),
             'last_sold': r['last_sold'].isoformat() if r['last_sold'] else None,
             'days_since': (now - r['last_sold']).days if r['last_sold'] else None}
            for r in rows[:200]
        ],
    }