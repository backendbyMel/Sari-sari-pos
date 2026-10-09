from rest_framework.exceptions import APIException, ValidationError

from core.services import get_credit_limit_mode, get_default_credit_limit


class OverCreditLimit(APIException):
    status_code = 409
    default_detail = 'This sale is over the credit limit.'
    default_code = 'over_limit'

    def __init__(self, info):
        self.detail = info    


def effective_limit(customer, default=None):
    if customer.credit_limit is not None:
        return customer.credit_limit
    return default if default is not None else get_default_credit_limit()


def check_credit_limit(customer, total, confirmed):
    limit = effective_limit(customer)
    would_be = customer.balance + total
    if would_be <= limit:
        return
    message = (
        f'{customer.name} already owes \u20b1{customer.balance}. This sale of \u20b1{total} would '
        f'make it \u20b1{would_be}, over the limit of \u20b1{limit}.'
    )
    if get_credit_limit_mode() == 'block':
        raise ValidationError({'customer': message + ' The owner has blocked utang over the limit.'})
    if confirmed:
        return
    raise OverCreditLimit({
        'code': 'over_limit', 'detail': message, 'customer': customer.name,
        'balance': str(customer.balance), 'limit': str(limit),
        'total': str(total), 'would_be': str(would_be),
    })