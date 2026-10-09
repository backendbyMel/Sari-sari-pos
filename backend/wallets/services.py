from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from sales.models import Receipt
from sales.services import next_receipt_no
from shifts.models import Shift
from shifts.services import record_payout

from .mobile import normalize_mobile
from .models import LoadProduct, LoadTransaction, Wallet, WalletTransaction

MONEY = Decimal('0.01')
LOAD_WALLET = {'type': Wallet.Type.LOAD, 'provider': 'Load wallet'}


def get_load_wallet():
    wallet, _ = Wallet.objects.get_or_create(**LOAD_WALLET)
    return wallet


def wallet_entry(wallet, *, type, amount, user, shift=None, reference_no='', source='',
                 amount_paid=None, note=''):
    wallet.balance += amount
    wallet.save(update_fields=['balance'])
    return WalletTransaction.objects.create(
        wallet=wallet, type=type, amount=amount, balance_after=wallet.balance, reference_no=reference_no,
        source=source, amount_paid=amount_paid, note=note, shift=shift, user=user,
    )


def _own_open_shift(user, message):
    shift = Shift.objects.select_for_update().filter(cashier=user, status=Shift.Status.OPEN).first()
    if shift is None:
        raise ValidationError({'shift': message})
    return shift


def _locked_load_wallet():
    return Wallet.objects.select_for_update().get(pk=get_load_wallet().pk)


@transaction.atomic
def send_load(*, cashier, product_id, mobile_no, reference_no):
    shift = _own_open_shift(cashier, 'You have no open shift. Start your shift before selling load.')
    product = (
        LoadProduct.objects.select_related('network')
        .filter(pk=product_id, is_active=True, network__is_active=True).first()
    )
    if product is None:
        raise ValidationError({'product': 'That load product is not available.'})

    mobile = normalize_mobile(mobile_no)
    reference = reference_no.strip().upper()
    if LoadTransaction.objects.filter(network_name=product.network.name, reference_no=reference).exists():
        raise ValidationError({'reference_no': 'That reference number was already recorded for this network.'})

    wallet = _locked_load_wallet()
    face = product.face_value
    rebate = (face * product.network.rebate_percent / Decimal('100')).quantize(MONEY, ROUND_HALF_UP)

    warnings = []
    if wallet.balance < face:
        # No number here: it would reveal the expected wallet balance (blind wallet check).
        warnings.append(
            'The system thinks the load wallet is too low for this load. '
            'Tell the owner so the wallet can be checked.'
        )

    receipt_no = next_receipt_no()
    tx = LoadTransaction.objects.create(
        wallet=wallet, load_product=product, network_name=product.network.name,
        product_name=product.name, mobile_no=mobile, amount=face, price_charged=product.selling_price,
        rebate=rebate, reference_no=reference, shift=shift, cashier=cashier, receipt_no=receipt_no,
    )
    wallet_entry(wallet, type=WalletTransaction.Type.LOAD_SENT, amount=-face, user=cashier,
                 shift=shift, reference_no=reference, note=f'Load {receipt_no}')
    Receipt.objects.create(receipt_no=receipt_no, source=Receipt.Source.LOAD, source_id=tx.pk)
    return tx, warnings


@transaction.atomic
def fail_load(*, user, load_id, note):
    shift = _own_open_shift(user, 'You have no open shift.')
    wallet = _locked_load_wallet()
    tx = LoadTransaction.objects.select_for_update().filter(pk=load_id).first()
    if tx is None:
        raise NotFound('Load not found.')
    if tx.shift_id != shift.pk:
        raise ValidationError({'load': 'Only loads from your current open shift can be marked failed here. '
                                       'Tell the owner about older ones.'})
    if tx.status != LoadTransaction.Status.SUCCESS:
        raise ValidationError({'load': 'This load is already marked failed.'})

    tx.status = LoadTransaction.Status.FAILED
    tx.failed_note = note
    tx.failed_at = timezone.now()
    tx.save(update_fields=['status', 'failed_note', 'failed_at'])
    wallet_entry(wallet, type=WalletTransaction.Type.REVERSAL, amount=tx.amount, user=user,
                 shift=shift, reference_no=tx.reference_no, note=f'Failed load {tx.receipt_no}: {note}')
    return tx


@transaction.atomic
def top_up(*, user, amount_added, amount_paid, source, reference_no=''):
    warnings, shift = [], None
    if source == 'drawer':
        label = 'Load wallet top-up' + (f' ({reference_no})' if reference_no else '')
        movement, warnings = record_payout(user=user, amount=amount_paid, reason=label)   # locks the shift
        shift = movement.shift
    wallet = _locked_load_wallet()
    entry = wallet_entry(wallet, type=WalletTransaction.Type.TOPUP, amount=amount_added, user=user,
                         shift=shift, reference_no=reference_no, source=source,
                         amount_paid=amount_paid, note='Top-up')
    return entry, warnings


@transaction.atomic
def adjust_wallet(*, user, actual_balance, reason):
    wallet = _locked_load_wallet()
    difference = actual_balance - wallet.balance
    if difference == 0:
        raise ValidationError({'actual_balance': 'The system already shows that balance.'})
    return wallet_entry(wallet, type=WalletTransaction.Type.ADJUSTMENT, amount=difference,
                        user=user, note=reason)