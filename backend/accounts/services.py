from django.db import transaction

from .models import User

MAX_PIN_ATTEMPTS = 5


def attempt_pin_login(username, pin):
    with transaction.atomic():
        user = (
            User.objects.select_for_update()
            .filter(username=username, role=User.Role.CASHIER)
            .first()
        )
        if user is None or not user.is_active or not user.pin_hash or user.pin_locked:
            return None
        if user.check_pin(pin):
            if user.pin_failed_attempts:
                user.pin_failed_attempts = 0
                user.save(update_fields=['pin_failed_attempts'])
            return user
        user.pin_failed_attempts += 1
        if user.pin_failed_attempts >= MAX_PIN_ATTEMPTS:
            user.pin_locked = True
        user.save(update_fields=['pin_failed_attempts', 'pin_locked'])
        return None