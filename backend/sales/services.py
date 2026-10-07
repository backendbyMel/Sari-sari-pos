from django.db import transaction

from .models import ReceiptCounter


@transaction.atomic
def next_receipt_no():
    counter, _ = ReceiptCounter.objects.select_for_update().get_or_create(pk=1)
    counter.last_number += 1
    counter.save(update_fields=['last_number'])
    return f'SR-{counter.last_number:06d}'