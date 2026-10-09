import re

from rest_framework.exceptions import ValidationError


def normalize_mobile(value):
    digits = re.sub(r'[\s\-().]', '', value or '')
    if digits.startswith('+63'):
        digits = '0' + digits[3:]
    elif digits.startswith('63') and len(digits) == 12:
        digits = '0' + digits[2:]
    if not re.fullmatch(r'09\d{9}', digits):
        raise ValidationError({'mobile_no': 'Enter a Philippine mobile number like 0917 123 4567.'})
    return digits


def mask_mobile(number):
    return f'{number[:4]}***{number[-4:]}'