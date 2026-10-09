from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from sales.models import Sale

from .models import Shift, ShiftReopen, CashMovement
from utang.models import UtangPayment

ZERO = Decimal('0')


@transaction.atomic
def start_shift(*, cashier, opening_cash):
    open_shift = Shift.objects.select_related('cashier').filter(status=Shift.Status.OPEN).first()
    if open_shift:
        if open_shift.cashier_id == cashier.id:
            message = 'You already have an open shift.'
        else:
            message = (
                f'{open_shift.cashier.username} still has a shift open. '
                'It must be ended before a new shift can start.'
            )
        raise ValidationError({'shift': message})

    previous = (
        Shift.objects.filter(status=Shift.Status.CLOSED, counted_cash__isnull=False)
        .order_by('-end_time', '-id')
        .first()
    )
    previous_cash = previous.counted_cash if previous else None
    difference = opening_cash - previous_cash if previous else None

    try:
        with transaction.atomic():
            return Shift.objects.create(
                cashier=cashier,
                opening_cash=opening_cash,
                previous_closing_cash=previous_cash,
                opening_difference=difference,
            )
    except IntegrityError:
        raise ValidationError(
            {'shift': 'Another shift was just started. Check the shift status.'}
        )


def shift_totals(shift):
    sales = Sale.objects.filter(shift=shift, status=Sale.Status.COMPLETED)
    cash = sales.filter(payment_type=Sale.PaymentType.CASH).aggregate(t=Sum('total'))['t']
    on_utang = sales.filter(payment_type=Sale.PaymentType.UTANG).aggregate(t=Sum('total'))['t']
    everything = sales.aggregate(t=Sum('total'))['t']
    collected = UtangPayment.objects.filter(shift=shift).aggregate(t=Sum('amount'))['t']
    payouts = CashMovement.objects.filter(shift=shift, type=CashMovement.Type.OUT)
    paid = payouts.aggregate(t=Sum('amount'))['t']
    return {
        'sales_count': sales.count(),
        'sales_total': everything or ZERO,
        'cash_sales': cash or ZERO,
        'utang_given': on_utang or ZERO,
        'utang_collected': collected or ZERO,
        'payouts_total': paid or ZERO,
        'payouts_count': payouts.count(),
    }


@transaction.atomic
def close_shift(*, shift_id, counted_cash, denominations, closed_by, reason=''):
    shift = Shift.objects.select_for_update().filter(pk=shift_id).first()
    if shift is None:
        raise NotFound('Shift not found.')
    if shift.status != Shift.Status.OPEN:
        raise ValidationError({'shift': 'This shift is already closed.'})

    totals = shift_totals(shift)
    expected = (
        shift.opening_cash + totals['cash_sales'] + totals['utang_collected'] - totals['payouts_total']
    )

    shift.expected_cash = expected
    shift.counted_cash = counted_cash
    shift.variance = counted_cash - expected
    shift.denominations = denominations or None
    shift.end_time = timezone.now()
    shift.closed_by = closed_by
    shift.close_reason = reason
    shift.status = Shift.Status.CLOSED
    shift.save()
    return shift, totals


@transaction.atomic
def reopen_shift(*, shift_id, user, reason):
    shift = Shift.objects.select_for_update().filter(pk=shift_id).first()
    if shift is None:
        raise NotFound('Shift not found.')
    if shift.status != Shift.Status.CLOSED:
        raise ValidationError({'shift': 'This shift is not closed.'})

    latest = Shift.objects.order_by('-start_time', '-id').first()
    if latest.pk != shift.pk:
        raise ValidationError(
            {'shift': 'Only the most recent shift can be reopened, because newer shifts '
                      'start from its closing count.'}
        )

    ShiftReopen.objects.create(
        shift=shift, reopened_by=user, reason=reason,
        previous_end_time=shift.end_time,
        previous_expected_cash=shift.expected_cash,
        previous_counted_cash=shift.counted_cash,
        previous_variance=shift.variance,
        previous_denominations=shift.denominations,
        previous_closed_by=shift.closed_by,
        previous_close_reason=shift.close_reason,
    )
    Shift.objects.filter(pk=shift.pk).update(
        status=Shift.Status.OPEN, end_time=None, expected_cash=None, counted_cash=None,
        variance=None, denominations=None, closed_by=None, close_reason='',
    )
    shift.refresh_from_db()
    return shift

@transaction.atomic
def record_payout(*, user, amount, reason):
    shift = (
        Shift.objects.select_for_update()
        .filter(cashier=user, status=Shift.Status.OPEN)
        .first()
    )
    if shift is None:
        raise ValidationError({'shift': 'You have no open shift. Start your shift first.'})

    totals = shift_totals(shift)
    drawer = (
        shift.opening_cash + totals['cash_sales'] + totals['utang_collected'] - totals['payouts_total']
    )
    warnings = []
    if amount > drawer:
        warnings.append(
            'This is more than the drawer should hold, according to the system. '
            'Please check the amount.'
        )

    movement = CashMovement.objects.create(
        shift=shift, type=CashMovement.Type.OUT, amount=amount,
        reason=reason, recorded_by=user,
    )
    return movement, warnings