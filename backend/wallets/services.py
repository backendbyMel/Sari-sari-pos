from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from sales.models import Receipt
from sales.services import next_receipt_no
from shifts.models import Shift
from shifts.services import record_payout, expected_cash_for, shift_totals

from .mobile import normalize_mobile
from .models import LoadProduct, LoadTransaction, Wallet, WalletTransaction, EWalletTransaction, FeeRule

MONEY = Decimal('0.01')
LOAD_WALLET = {'type': Wallet.Type.LOAD, 'provider': 'Load wallet'}


def get_load_wallet():
    wallet, _ = Wallet.objects.get_or_create(**LOAD_WALLET)
    return wallet

def get_ewallet():
    wallet, _ = Wallet.objects.get_or_create(type=Wallet.Type.EWALLET, provider='GCash')
    return wallet


def wallet_for(kind):
    return get_load_wallet() if kind == 'load' else get_ewallet()


def _locked_wallet(kind):
    return Wallet.objects.select_for_update().get(pk=wallet_for(kind).pk)


def fee_for(wallet, amount):
    rule = FeeRule.objects.filter(wallet=wallet, min_amount__lte=amount, max_amount__gte=amount).first()
    return rule.fee if rule else None


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
def top_up(*, user, amount_added, amount_paid, source, reference_no='', kind='load'):
    warnings, shift = [], None
    if source == 'drawer':
        label = f'{wallet_for(kind).provider} top-up' + (f' ({reference_no})' if reference_no else '')
        movement, warnings = record_payout(user=user, amount=amount_paid, reason=label)   
        shift = movement.shift
    wallet = _locked_wallet(kind)
    entry = wallet_entry(wallet, type=WalletTransaction.Type.TOPUP, amount=amount_added, user=user,
                         shift=shift, reference_no=reference_no, source=source,
                         amount_paid=amount_paid, note='Top-up')
    return entry, warnings


@transaction.atomic
def adjust_wallet(*, user, actual_balance, reason, kind='load'):
    wallet = _locked_wallet(kind)
    difference = actual_balance - wallet.balance
    if difference == 0:
        raise ValidationError({'actual_balance': 'The system already shows that balance.'})
    return wallet_entry(wallet, type=WalletTransaction.Type.ADJUSTMENT, amount=difference,
                        user=user, note=reason)

@transaction.atomic
def ewallet_transaction(*, cashier, kind, amount, mobile_no, reference_no,
                        fee_override=None, override_reason=''):
    
    shift = _own_open_shift(cashier, 'You have no open shift. Start your shift before GCash cash in or cash out.')
    wallet = _locked_wallet('ewallet')

    amount = Decimal(amount).quantize(MONEY)
    mobile = normalize_mobile(mobile_no)
    reference = reference_no.strip().upper()
    if EWalletTransaction.objects.filter(wallet=wallet, reference_no=reference).exists():
        raise ValidationError({'reference_no': 'That GCash reference number was already recorded.'})

    table_fee = fee_for(wallet, int(amount))
    reason = (override_reason or '').strip()
    if fee_override is not None:
        fee = Decimal(fee_override).quantize(MONEY, ROUND_HALF_UP)
    elif table_fee is not None:
        fee = table_fee
    else:
        raise ValidationError({'fee': 'No fee is set for this amount. Ask the owner to add it to the fee table, '
                                      'or enter a different fee with a reason.'})
    overridden = fee_override is not None and fee != table_fee
    if overridden and not reason:
        raise ValidationError({'override_reason': 'Enter the reason for a different fee. It is required and logged.'})
    if fee > amount:
        raise ValidationError({'fee': 'The fee cannot be more than the amount.'})

    warnings = []
    if kind == EWalletTransaction.Type.CASH_OUT:
        drawer = expected_cash_for(shift, shift_totals(shift))
        if amount - fee > drawer:
            warnings.append('This is more cash than the drawer should hold, according to the system. '
                            'Please check the amount.')
    elif wallet.balance < amount:
        warnings.append('The system thinks the GCash wallet is too low for this cash in. '
                        'Tell the owner so the wallet can be checked.')

    receipt_no = next_receipt_no()
    tx = EWalletTransaction.objects.create(
        wallet=wallet, wallet_name=wallet.provider, type=kind, amount=amount, fee=fee, table_fee=table_fee,
        fee_overridden=overridden, fee_override_reason=reason if overridden else '',
        customer_mobile=mobile, reference_no=reference, shift=shift, cashier=cashier, receipt_no=receipt_no,
    )
    cash_in = kind == EWalletTransaction.Type.CASH_IN
    wallet_entry(
        wallet, type=WalletTransaction.Type.CASH_IN if cash_in else WalletTransaction.Type.CASH_OUT,
        amount=-amount if cash_in else amount, user=cashier, shift=shift,
        reference_no=reference, note=f'GCash {receipt_no}',
    )
    Receipt.objects.create(receipt_no=receipt_no, source=Receipt.Source.EWALLET, source_id=tx.pk)
    return tx, warnings


@transaction.atomic
def reverse_ewallet(*, user, tx_id, note):
    first = EWalletTransaction.objects.filter(pk=tx_id).first()
    if first is None:
        raise NotFound('Transaction not found.')
    shift = Shift.objects.select_for_update().get(pk=first.shift_id)
    if shift.status != Shift.Status.OPEN:
        raise ValidationError({'transaction': 'That shift is already closed, so it cannot be reversed here. '
                                              'Older transactions need the void feature (Phase 5).'})
    wallet = Wallet.objects.select_for_update().get(pk=first.wallet_id)
    tx = EWalletTransaction.objects.select_for_update().get(pk=tx_id)
    if tx.status != EWalletTransaction.Status.SUCCESS:
        raise ValidationError({'transaction': 'This transaction is already reversed.'})

    tx.status = EWalletTransaction.Status.REVERSED
    tx.reversed_note = note
    tx.reversed_by = user
    tx.reversed_at = timezone.now()
    tx.save(update_fields=['status', 'reversed_note', 'reversed_by', 'reversed_at'])
    undo = tx.amount if tx.type == EWalletTransaction.Type.CASH_IN else -tx.amount
    wallet_entry(wallet, type=WalletTransaction.Type.REVERSAL, amount=undo, user=user, shift=shift,
                 reference_no=tx.reference_no, note=f'Reversed {tx.receipt_no}: {note}')
    return tx