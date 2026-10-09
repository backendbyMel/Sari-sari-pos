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
OVERDUE_KEY = 'overdue_days'
CASHIER_TOPUP_KEY = 'cashier_can_topup'
DEFAULT_OVERDUE_DAYS = 30
MIN_OVERDUE_DAYS = 1
MAX_OVERDUE_DAYS = 365


def _save(key, value, user):
    Setting.objects.update_or_create(key=key, defaults={'value': str(value), 'updated_by': user})


def get_idle_minutes():
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

def get_overdue_days():
    row = Setting.objects.filter(key=OVERDUE_KEY).first()
    try:
        days = int(row.value) if row else DEFAULT_OVERDUE_DAYS
    except ValueError:
        return DEFAULT_OVERDUE_DAYS
    return days if MIN_OVERDUE_DAYS <= days <= MAX_OVERDUE_DAYS else DEFAULT_OVERDUE_DAYS


def set_overdue_days(days, user):
    _save(OVERDUE_KEY, days, user)

def get_cashier_can_topup():
    row = Setting.objects.filter(key=CASHIER_TOPUP_KEY).first()
    return bool(row and row.value == 'true')


def set_cashier_can_topup(value, user):
    _save(CASHIER_TOPUP_KEY, 'true' if value else 'false', user)

def current_settings():
    return {
        'idle_logout_minutes': get_idle_minutes(),
        'default_credit_limit': str(get_default_credit_limit().quantize(Decimal('0.01'))),
        'credit_limit_mode': get_credit_limit_mode(),
        'overdue_days': get_overdue_days(),
        'cashier_can_topup': get_cashier_can_topup(),
    }