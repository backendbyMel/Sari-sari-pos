from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from .models import Shift


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