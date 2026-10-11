from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.utils import timezone

from core.services import get_overdue_days
from inventory.models import Product
from sales.models import Sale, SaleItem
from shifts.models import Shift
from utang.models import BadDebtWriteOff, Customer
from utang.services import unpaid_ages
from wallets.models import EWalletTransaction, LoadTransaction, ShiftWalletCheck, Wallet

ZERO = Decimal('0')
CENT = Decimal('0.01')

LINE_COST = ExpressionWrapper(
    F('unit_cost') * F('quantity'),
    output_field=DecimalField(max_digits=24, decimal_places=8),
)


def money(value):
    return str(Decimal(value or 0).quantize(CENT, ROUND_HALF_UP))


def num(value):
    return format(Decimal(value).normalize(), 'f')


def day_bounds(day=None):
    day = day or timezone.localdate()
    start = timezone.make_aware(datetime.combine(day, time.min))
    return day, start, start + timedelta(days=1)


def today_numbers(start, end):
    sales = Sale.objects.filter(timestamp__gte=start, timestamp__lt=end, status=Sale.Status.COMPLETED)
    sale_sums = sales.aggregate(all_total=Sum('total'), n=Count('id'))
    utang_sum = sales.filter(payment_type=Sale.PaymentType.UTANG).aggregate(t=Sum('total'))['t']

    items = SaleItem.objects.filter(
        sale__timestamp__gte=start, sale__timestamp__lt=end, sale__status=Sale.Status.COMPLETED)
    goods = items.aggregate(revenue=Sum('line_total'), cost=Sum(LINE_COST))
    goods_profit = (goods['revenue'] or ZERO) - (goods['cost'] or ZERO)

    loads = LoadTransaction.objects.filter(
        timestamp__gte=start, timestamp__lt=end, status=LoadTransaction.Status.SUCCESS
    ).aggregate(price_sum=Sum('price_charged'), face_sum=Sum('amount'), rebate_sum=Sum('rebate'))
    load_profit = (loads['price_sum'] or ZERO) - (loads['face_sum'] or ZERO) + (loads['rebate_sum'] or ZERO)

    gcash = EWalletTransaction.objects.filter(
        timestamp__gte=start, timestamp__lt=end, status=EWalletTransaction.Status.SUCCESS
    ).aggregate(fee_sum=Sum('fee'), n=Count('id'))

    written_off = BadDebtWriteOff.objects.filter(
        timestamp__gte=start, timestamp__lt=end).aggregate(w=Sum('amount'))['w']

    fees = gcash['fee_sum'] or ZERO
    return {
        'sales_count': sale_sums['n'],
        'sales_total': money(sale_sums['all_total']),
        'utang_sales_total': money(utang_sum),
        'goods_profit': money(goods_profit),
        'load_sales': money(loads['price_sum']),
        'load_profit': money(load_profit),
        'ewallet_count': gcash['n'],
        'ewallet_fees': money(fees),
        'profit': money(goods_profit + load_profit + fees),   
        'writeoffs': money(written_off),                    
    }


def best_sellers(start, end, limit=5):
    rows = (
        SaleItem.objects.filter(
            sale__timestamp__gte=start, sale__timestamp__lt=end, sale__status=Sale.Status.COMPLETED)
        .values('product_id', 'product__name', 'product__base_unit')
        .annotate(total_qty=Sum('base_quantity'), total_amount=Sum('line_total'))
        .order_by('-total_amount', 'product__name')[:limit]
    )
    return [
        {'product': r['product__name'], 'quantity': num(r['total_qty']),
         'unit': r['product__base_unit'], 'amount': money(r['total_amount'])}
        for r in rows
    ]


def shift_cards():
    open_shift = Shift.objects.select_related('cashier').filter(status=Shift.Status.OPEN).first()
    last = (Shift.objects.select_related('cashier', 'closed_by')
            .filter(status=Shift.Status.CLOSED).order_by('-end_time', '-id').first())
    last_card = None
    if last:
        flags = ShiftWalletCheck.objects.filter(shift=last).filter(
            ~Q(difference_start=0) | (Q(difference_end__isnull=False) & ~Q(difference_end=0))
        ).count()
        last_card = {
            'id': last.pk, 'cashier': last.cashier.username, 'end_time': last.end_time,
            'variance': money(last.variance),
            'closed_on_behalf': bool(last.closed_by_id and last.closed_by_id != last.cashier_id),
            'wallet_flags': flags,
        }
    return (
        {'id': open_shift.pk, 'cashier': open_shift.cashier.username,
         'start_time': open_shift.start_time, 'opening_cash': money(open_shift.opening_cash)}
        if open_shift else None,
        last_card,
    )


def low_stock(limit=10):
    low = (Product.objects.filter(is_active=True, units__isnull=False, stock_qty__lte=F('low_stock_level'))
           .distinct().order_by('stock_qty', 'name'))
    return {
        'count': low.count(),
        'recount_count': Product.objects.filter(is_active=True, needs_recount=True).count(),
        'items': [
            {'id': p.pk, 'name': p.name, 'stock': num(p.stock_qty), 'unit': p.base_unit,
             'low_level': num(p.low_stock_level), 'status': 'out' if p.stock_qty <= 0 else 'low'}
            for p in low[:limit]
        ],
    }


def utang_card():
    customers = list(Customer.objects.all())
    days = get_overdue_days()
    info = unpaid_ages(customers, days)
    return {
        'total_unpaid': money(sum((c.balance for c in customers), ZERO)),
        'owing_count': sum(1 for c in customers if c.balance > 0),
        'overdue_count': sum(1 for v in info.values() if v['overdue']),
        'overdue_days': days,
    }


def wallet_cards():
    return [
        {'id': w.pk, 'provider': w.provider, 'type': w.type, 'balance': money(w.balance),
         'low_level': money(w.low_level), 'is_low': w.balance <= w.low_level}
        for w in Wallet.objects.filter(is_active=True).order_by('type', 'provider')
    ]


def dashboard(day=None):
    day, start, end = day_bounds(day)
    open_shift, last_shift = shift_cards()
    return {
        'date': day.isoformat(),
        'today': today_numbers(start, end),
        'open_shift': open_shift,
        'last_shift': last_shift,
        'low_stock': low_stock(),
        'utang': utang_card(),
        'wallets': wallet_cards(),
        'best_sellers': best_sellers(start, end),
    }