from decimal import Decimal, InvalidOperation

from .models import Setting

IDLE_KEY = 'idle_logout_minutes'
DEFAULT_IDLE_MINUTES = 15
MIN_IDLE_MINUTES = 1
MAX_IDLE_MINUTES = 240

CREDIT_LIMIT_KEY = 'default_credit_limit'
DEFAULT_CREDIT_LIMIT = Decimal('500.00')
CREDIT_MODE_KEY = 'credit_limit_mode'
CREDIT_MODES = ('warn', 'block')


def _save(key, value, user):
    Setting.objects.update_or_create(key=key, defaults={'value': str(value), 'updated_by': user})


def get_idle_minutes():
    """The saved value, or 15 if nothing valid is saved (garbage never breaks the app)."""
    row = Setting.objects.filter(key=IDLE_KEY).first()
    try:
        minutes = int(row.value) if row else DEFAULT_IDLE_MINUTES
    except ValueError:
        return DEFAULT_IDLE_MINUTES
    return minutes if MIN_IDLE_MINUTES <= minutes <= MAX_IDLE_MINUTES else DEFAULT_IDLE_MINUTES


def set_idle_minutes(minutes, user):
    _save(IDLE_KEY, minutes, user)


def get_default_credit_limit():
    row = Setting.objects.filter(key=CREDIT_LIMIT_KEY).first()
    try:
        value = Decimal(row.value) if row else DEFAULT_CREDIT_LIMIT
        if not value.is_finite() or value < 0:
            return DEFAULT_CREDIT_LIMIT
    except InvalidOperation:
        return DEFAULT_CREDIT_LIMIT
    return value


def set_default_credit_limit(value, user):
    _save(CREDIT_LIMIT_KEY, Decimal(value).quantize(Decimal('0.01')), user)


def get_credit_limit_mode():
    row = Setting.objects.filter(key=CREDIT_MODE_KEY).first()
    return row.value if row and row.value in CREDIT_MODES else 'warn'


def set_credit_limit_mode(mode, user):
    _save(CREDIT_MODE_KEY, mode, user)


def current_settings():
    return {
        'idle_logout_minutes': get_idle_minutes(),
        # text, never a float: money is never a float in JSON
        'default_credit_limit': str(get_default_credit_limit().quantize(Decimal('0.01'))),
        'credit_limit_mode': get_credit_limit_mode(),
    }