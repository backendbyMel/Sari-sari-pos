from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from sales.models import Sale

from .models import Shift, ShiftReopen, CashMovement
from utang.models import UtangPayment
from wallets.models import LoadTransaction, EWalletTransaction, ShiftWalletCheck, Wallet, WalletTransaction
import re

ZERO = Decimal('0')
BALANCE_OK = re.compile(r'^\d{1,10}(\.\d{1,2})?$')


def parse_balances(raw, wallets):
    raw = {str(k): ('' if v is None else str(v).strip()) for k, v in (raw or {}).items()}
    known = {str(w.pk) for w in wallets}
    if any(key not in known for key in raw):
        raise ValidationError({'wallet_balances': 'The request lists a wallet that is not part of this check.'})
    missing = [w.provider for w in wallets if raw.get(str(w.pk), '') == '']
    if missing:
        raise ValidationError({'wallet_balances': 'Enter the balance shown in the app for: ' + ', '.join(missing) + '.'})
    bad = [w.provider for w in wallets if not BALANCE_OK.match(raw[str(w.pk)])]
    if bad:
        raise ValidationError({'wallet_balances': 'The balance for ' + ', '.join(bad) + ' must be an amount like 1250.50.'})
    return {w.pk: Decimal(raw[str(w.pk)]) for w in wallets}


def _check_row(check, owner):
    row = {
        'wallet': check.wallet.provider,
        'opening': str(check.balance_start),
        'expected': None if check.expected_end is None else str(check.expected_end),
        'actual': None if check.balance_end is None else str(check.balance_end),
        'gap': None if check.difference_end is None else str(check.difference_end),
    }
    if owner:  
        row['start_expected'] = str(check.expected_start)
        row['start_gap'] = str(check.difference_start)
    return row


def wallet_checks_for(shifts, *, owner):
    result = {s.pk: [] for s in shifts}
    checks = (ShiftWalletCheck.objects.filter(shift__in=list(result))
              .select_related('wallet').order_by('wallet__type', 'wallet__provider'))
    for check in checks:
        result[check.shift_id].append(_check_row(check, owner))
    return result


def wallet_check_rows(shift, *, owner=False):
    return wallet_checks_for([shift], owner=owner)[shift.pk]

@transaction.atomic
def start_shift(*, cashier, opening_cash, wallet_balances=None):
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

    wallets = list(Wallet.objects.select_for_update().filter(is_active=True).order_by('pk'))
    balances = parse_balances(wallet_balances, wallets)

    previous = (
        Shift.objects.filter(status=Shift.Status.CLOSED, counted_cash__isnull=False)
        .order_by('-end_time', '-id')
        .first()
    )
    previous_cash = previous.counted_cash if previous else None
    difference = opening_cash - previous_cash if previous else None

    try:
        with transaction.atomic():
            shift = Shift.objects.create(
                cashier=cashier,
                opening_cash=opening_cash,
                previous_closing_cash=previous_cash,
                opening_difference=difference,
            )
            for wallet in wallets:
                typed = balances[wallet.pk]
                ShiftWalletCheck.objects.create(
                    shift=shift, wallet=wallet, balance_start=typed,
                    expected_start=wallet.balance, difference_start=typed - wallet.balance,
                )
            return shift
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
    loads = LoadTransaction.objects.filter(shift=shift)
    load_ok = loads.filter(status=LoadTransaction.Status.SUCCESS)
    load_bad = loads.filter(status=LoadTransaction.Status.FAILED)
    load_sales = load_ok.aggregate(t=Sum('price_charged'))['t']
    load_bad_total = load_bad.aggregate(t=Sum('price_charged'))['t']
    ew_ok = EWalletTransaction.objects.filter(shift=shift, status=EWalletTransaction.Status.SUCCESS)
    ins = ew_ok.filter(type=EWalletTransaction.Type.CASH_IN)
    outs = ew_ok.filter(type=EWalletTransaction.Type.CASH_OUT)
    in_sums = ins.aggregate(a=Sum('amount'), f=Sum('fee'))
    out_sums = outs.aggregate(a=Sum('amount'), f=Sum('fee'))
    in_received = (in_sums['a'] or ZERO) + (in_sums['f'] or ZERO)
    out_net = (out_sums['a'] or ZERO) - (out_sums['f'] or ZERO)
    return {
        'sales_count': sales.count(),
        'sales_total': everything or ZERO,
        'cash_sales': cash or ZERO,
        'utang_given': on_utang or ZERO,
        'utang_collected': collected or ZERO,
        'load_sales': load_sales or ZERO,
        'load_count': load_ok.count(),
        'load_failed_count': load_bad.count(),
        'load_failed_total': load_bad_total or ZERO,
        'payouts_total': paid or ZERO,
        'payouts_count': payouts.count(),
        'ewallet_in_received': in_received,
        'ewallet_in_count': ins.count(),
        'ewallet_out_net': out_net,
        'ewallet_out_count': outs.count(),
        'ewallet_reversed_count': EWalletTransaction.objects.filter(
            shift=shift, status=EWalletTransaction.Status.REVERSED).count(),
    }

def expected_cash_for(shift, totals):
    return (
        shift.opening_cash + totals['cash_sales'] + totals['utang_collected'] + totals['load_sales']
        + totals['ewallet_in_received'] - totals['ewallet_out_net'] - totals['payouts_total']
    )

@transaction.atomic
def close_shift(*, shift_id, counted_cash, denominations, closed_by, reason='', wallet_balances=None):
    shift = Shift.objects.select_for_update().filter(pk=shift_id).first()
    if shift is None:
        raise NotFound('Shift not found.')
    if shift.status != Shift.Status.OPEN:
        raise ValidationError({'shift': 'This shift is already closed.'})

    now = timezone.now()

    checks = list(shift.wallet_checks.select_related('wallet').order_by('wallet__pk'))
    if checks:
        list(Wallet.objects.select_for_update().filter(pk__in=[c.wallet_id for c in checks]).order_by('pk'))
        balances = parse_balances(wallet_balances, [c.wallet for c in checks])
        for check in checks:
            moved = (
                WalletTransaction.objects.filter(
                    wallet_id=check.wallet_id, timestamp__gt=check.started_at, timestamp__lte=now)
                .aggregate(t=Sum('amount'))['t'] or ZERO
            )
            check.expected_end = check.balance_start + moved
            check.balance_end = balances[check.wallet_id]
            check.difference_end = check.balance_end - check.expected_end
            check.ended_at = now
            check.save()

    totals = shift_totals(shift)
    expected = expected_cash_for(shift, totals)

    shift.expected_cash = expected
    shift.counted_cash = counted_cash
    shift.variance = counted_cash - expected
    shift.denominations = denominations or None
    shift.end_time = now
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

    previous_checks = [
        {'wallet': c.wallet.provider, 'balance_end': str(c.balance_end),
         'expected_end': str(c.expected_end), 'difference_end': str(c.difference_end)}
        for c in shift.wallet_checks.select_related('wallet') if c.balance_end is not None
    ]

    ShiftReopen.objects.create(
        shift=shift, reopened_by=user, reason=reason,
        previous_end_time=shift.end_time,
        previous_expected_cash=shift.expected_cash,
        previous_counted_cash=shift.counted_cash,
        previous_variance=shift.variance,
        previous_denominations=shift.denominations,
        previous_closed_by=shift.closed_by,
        previous_close_reason=shift.close_reason,
        previous_wallet_checks=previous_checks or None,
    )
    ShiftWalletCheck.objects.filter(shift=shift).update(
        balance_end=None, expected_end=None, difference_end=None, ended_at=None)
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
    drawer = expected_cash_for(shift, totals)
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