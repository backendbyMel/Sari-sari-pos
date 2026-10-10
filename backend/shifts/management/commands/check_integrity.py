from decimal import ROUND_HALF_UP, Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Sum

from inventory.models import Product, StockMovement
from sales.models import Receipt, ReceiptCounter, Sale, SaleItem
from shifts.models import CashMovement, Shift
from shifts.reports import current_reports
from shifts.services import shift_totals, expected_cash_for
from utang.models import Customer, UtangPayment, BadDebtWriteOff
from wallets.models import LoadTransaction, Wallet, WalletTransaction, EWalletTransaction, ShiftWalletCheck

ZERO = Decimal('0')
QTY = Decimal('0.001')


class Command(BaseCommand):
    help = 'Checks that the books add up: stock, sales, receipts and shift cash. Changes nothing.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--from-shift', type=int, default=1,
            help='Only check shifts with this number or higher (to skip old test data).',
        )

    def handle(self, *args, **options):
        self.problems = []
        self.notes = []
        self.from_shift = options['from_shift']

        self.check_stock()
        self.check_sales()
        self.check_receipts()
        self.check_shifts()
        self.check_customers()
        self.check_wallets()
        self.check_wallet_checks()

        for note in self.notes:
            self.stdout.write(f'note: {note}')
        if self.problems:
            for problem in self.problems[:50]:
                self.stdout.write(self.style.ERROR(f'PROBLEM: {problem}'))
            if len(self.problems) > 50:
                self.stdout.write(f'... and {len(self.problems) - 50} more.')
            raise CommandError(f'{len(self.problems)} problem(s) found. Do not ignore them.')
        self.stdout.write(self.style.SUCCESS('OK: the books add up.'))

    def check_stock(self):
        names = dict(Product.objects.values_list('id', 'name'))
        stock = dict(Product.objects.values_list('id', 'stock_qty'))
        last = {}
        lines = StockMovement.objects.order_by('product_id', 'id').values_list(
            'product_id', 'quantity', 'balance_after')
        for pid, qty, after in lines:
            if pid in last and last[pid] + qty != after:
                self.problems.append(
                    f'{names[pid]}: a history line does not follow from the line before it '
                    f'(expected a balance of {last[pid] + qty}, found {after}).')
            last[pid] = after
        for pid, after in last.items():
            if stock[pid] != after:
                self.problems.append(
                    f'{names[pid]}: stock is {stock[pid]} but its history ends at {after}.')
        for pid, qty in stock.items():
            if qty < 0:
                self.notes.append(f'{names[pid]} has negative stock ({qty}). It needs a recount.')

    def check_sales(self):
        line_sums = dict(
            SaleItem.objects.values_list('sale_id').annotate(t=Sum('line_total')).order_by('sale_id'))
        no_shift = 0
        for sale in Sale.objects.order_by('id'):
            items_total = line_sums.get(sale.pk, ZERO)
            if sale.total != items_total - sale.discount:
                self.problems.append(
                    f'{sale.receipt_no}: the total is {sale.total} but its lines add up to '
                    f'{items_total - sale.discount}.')
            if sale.payment_type == Sale.PaymentType.CASH and sale.change != sale.cash_received - sale.total:
                self.problems.append(
                    f'{sale.receipt_no}: the change is {sale.change} but cash received '
                    f'{sale.cash_received} minus the total {sale.total} is '
                    f'{sale.cash_received - sale.total}.')
            if sale.shift_id is None:
                no_shift += 1
        for item in SaleItem.objects.select_related('sale', 'product_unit'):
            expected = (item.quantity * item.product_unit.pieces_per_unit).quantize(QTY, ROUND_HALF_UP)
            if item.base_quantity != expected:
                self.problems.append(
                    f'{item.sale.receipt_no}: a line deducted {item.base_quantity} from stock, '
                    f'but {item.quantity} x {item.product_unit.pieces_per_unit} is {expected}.')
        if no_shift:
            self.notes.append(f'{no_shift} sale(s) have no shift (old Phase 1 test sales). That is expected.')

    def check_receipts(self):
        receipts = list(Receipt.objects.all())
        sale_numbers = dict(Sale.objects.values_list('id', 'receipt_no'))
        payment_numbers = dict(UtangPayment.objects.values_list('id', 'receipt_no'))
        covered_sales, covered_payments = set(), set()
        for r in receipts:
            if r.source == Receipt.Source.SALE:
                covered_sales.add(r.source_id)
                if sale_numbers.get(r.source_id) != r.receipt_no:
                    self.problems.append(f'Receipt {r.receipt_no} does not match any sale.')
            elif r.source == Receipt.Source.UTANG_PAYMENT:
                covered_payments.add(r.source_id)
                if payment_numbers.get(r.source_id) != r.receipt_no:
                    self.problems.append(f'Receipt {r.receipt_no} does not match any utang payment.')
        for sale_id, number in sale_numbers.items():
            if sale_id not in covered_sales:
                self.problems.append(f'Sale {number} has no receipt record.')
        for payment_id, number in payment_numbers.items():
            if payment_id not in covered_payments:
                self.problems.append(f'Utang payment {number} has no receipt record.')
                
        numbers = sorted(int(r.receipt_no.rsplit('-', 1)[1]) for r in receipts)
        counter = ReceiptCounter.objects.first()
        if numbers:
            missing = sorted(set(range(1, numbers[-1] + 1)) - set(numbers))
            if missing:
                self.notes.append(f'Receipt numbers missing from the sequence: {missing[:10]}')
            if counter is None or counter.last_number < numbers[-1]:
                self.problems.append('The receipt counter is behind the newest receipt. Numbers could repeat.')

    def check_shifts(self):
        shifts = Shift.objects.filter(pk__gte=self.from_shift)
        if shifts.filter(status=Shift.Status.OPEN).count() > 1:
            self.problems.append('More than one shift is open.')

        closed = list(shifts.filter(status=Shift.Status.CLOSED).select_related('cashier'))
        reports = current_reports(closed)
        for s in closed:
            label = f'Shift #{s.pk} ({s.cashier.username})'
            if None in (s.end_time, s.counted_cash, s.expected_cash, s.variance):
                self.problems.append(f'{label} is closed but is missing its cash numbers.')
                continue
            totals = shift_totals(s)
            expected = expected_cash_for(s, totals)
            if s.expected_cash != expected:
                self.problems.append(
                    f'{label}: expected cash is saved as {s.expected_cash} but the records add up to {expected}.')
            if s.variance != s.counted_cash - s.expected_cash:
                self.problems.append(
                    f'{label}: the variance is saved as {s.variance} but counted minus expected is '
                    f'{s.counted_cash - s.expected_cash}.')
            if s.pk not in reports:
                self.notes.append(f'{label} has no current PDF report. The owner can create it.')

        late_sales = Sale.objects.filter(
            shift_id__gte=self.from_shift, shift__status=Shift.Status.CLOSED,
            timestamp__gt=F('shift__end_time'))
        for sale in late_sales:
            self.problems.append(f'{sale.receipt_no} was saved after its shift was closed.')
        late_moves = CashMovement.objects.filter(
            shift_id__gte=self.from_shift, shift__status=Shift.Status.CLOSED,
            timestamp__gt=F('shift__end_time'))
        for move in late_moves:
            self.problems.append(f'A pay-out of {move.amount} was recorded after shift #{move.shift_id} closed.')

        late_payments = UtangPayment.objects.filter(
            shift_id__gte=self.from_shift, shift__status=Shift.Status.CLOSED,
            timestamp__gt=F('shift__end_time'))
        for payment in late_payments:
            self.problems.append(
                f'Utang payment {payment.receipt_no} was saved after its shift was closed.')
        
        late_payments = UtangPayment.objects.filter(
            shift_id__gte=self.from_shift, shift__status=Shift.Status.CLOSED,
            timestamp__gt=F('shift__end_time'))
        for payment in late_payments:
            self.problems.append(
                f'Utang payment {payment.receipt_no} was saved after its shift was closed.')

        
    def check_customers(self):
        charged = dict(
            Sale.objects.filter(payment_type=Sale.PaymentType.UTANG, status=Sale.Status.COMPLETED)
            .values_list('customer_id').annotate(t=Sum('total')).order_by('customer_id'))
        paid = dict(UtangPayment.objects.values_list('customer_id').annotate(t=Sum('amount')).order_by('customer_id'))
        written = dict(BadDebtWriteOff.objects.values_list('customer_id').annotate(t=Sum('amount')).order_by('customer_id'))
        # expected = charged.get(customer.pk, ZERO) - paid.get(customer.pk, ZERO) - written.get(customer.pk, ZERO)
        for customer in Customer.objects.all():
            expected = charged.get(customer.pk, ZERO) - paid.get(customer.pk, ZERO) - written.get(customer.pk, ZERO)
            if customer.balance != expected:
                self.problems.append(
                    f'Customer {customer.name} (#{customer.pk}): the balance is {customer.balance} '
                    f'but charges minus payments is {expected}.')
            if customer.balance < 0:
                self.problems.append(f'Customer {customer.name} has a negative balance.')
        for sale in Sale.objects.filter(payment_type=Sale.PaymentType.UTANG, customer__isnull=True):
            self.problems.append(f'{sale.receipt_no} is a utang sale with no customer.')

    def check_wallets(self):
        for wallet in Wallet.objects.all():
            running = ZERO
            for entry in wallet.transactions.order_by('id'):
                running += entry.amount
                if entry.balance_after != running:
                    self.problems.append(
                        f'Wallet {wallet.provider}: entry #{entry.pk} says the balance became '
                        f'{entry.balance_after} but the entries add up to {running}.')
                    running = entry.balance_after
            if wallet.balance != running:
                self.problems.append(
                    f'Wallet {wallet.provider}: the balance is {wallet.balance} but its entries end at {running}.')

        loads = LoadTransaction.objects.all()
        sent = WalletTransaction.objects.filter(type='load_sent').aggregate(t=Sum('amount'))['t'] or ZERO
        face = loads.aggregate(t=Sum('amount'))['t'] or ZERO
        if -sent != face:
            self.problems.append(f'Loads sold add up to {face} but the wallet was reduced by {-sent}.')
        restored = WalletTransaction.objects.filter(wallet__type='load', type='reversal').aggregate(t=Sum('amount'))['t'] or ZERO
        failed_face = loads.filter(status='failed').aggregate(t=Sum('amount'))['t'] or ZERO
        if restored != failed_face:
            self.problems.append(f'Failed loads add up to {failed_face} but {restored} was put back in the wallet.')
        for tx in loads.filter(status='failed', failed_note=''):
            self.problems.append(f'Load {tx.receipt_no} is failed but has no note.')
        for tx in loads:
            if not Receipt.objects.filter(source='load', source_id=tx.pk, receipt_no=tx.receipt_no).exists():
                self.problems.append(f'Load {tx.receipt_no} has no receipt record.')
        late = LoadTransaction.objects.filter(
            shift_id__gte=self.from_shift, shift__status=Shift.Status.CLOSED, timestamp__gt=F('shift__end_time'))
        for tx in late:
            self.problems.append(f'Load {tx.receipt_no} was saved after its shift was closed.')

        ew = EWalletTransaction.objects.all()
        entries = WalletTransaction.objects.filter(wallet__type='ewallet')

        def total(rows):
            return rows.aggregate(t=Sum('amount'))['t'] or ZERO

        ins, outs = ew.filter(type='cash_in'), ew.filter(type='cash_out')
        if -total(entries.filter(type='cash_in')) != total(ins):
            self.problems.append('GCash cash-ins do not match the wallet entries.')
        if total(entries.filter(type='cash_out')) != total(outs):
            self.problems.append('GCash cash-outs do not match the wallet entries.')
        undone = total(ins.filter(status='reversed')) - total(outs.filter(status='reversed'))
        if total(entries.filter(type='reversal')) != undone:
            self.problems.append('GCash reversals do not match the wallet entries.')
        for tx in ew.filter(status='reversed', reversed_note=''):
            self.problems.append(f'GCash {tx.receipt_no} is reversed but has no note.')
        for tx in ew.filter(fee_overridden=True, fee_override_reason=''):
            self.problems.append(f'GCash {tx.receipt_no} has a different fee but no reason.')
        for tx in ew:
            if tx.fee > tx.amount:
                self.problems.append(f'GCash {tx.receipt_no}: the fee is more than the amount.')
            if not Receipt.objects.filter(source='ewallet', source_id=tx.pk, receipt_no=tx.receipt_no).exists():
                self.problems.append(f'GCash {tx.receipt_no} has no receipt record.')
        late = EWalletTransaction.objects.filter(
            shift_id__gte=self.from_shift, shift__status=Shift.Status.CLOSED, timestamp__gt=F('shift__end_time'))
        for tx in late:
            self.problems.append(f'GCash {tx.receipt_no} was saved after its shift was closed.')

    def check_wallet_checks(self):
        checks = ShiftWalletCheck.objects.filter(shift_id__gte=self.from_shift).select_related('shift', 'wallet')
        for c in checks:
            label = f'Shift #{c.shift_id} {c.wallet.provider}'
            if c.difference_start != c.balance_start - c.expected_start:
                self.problems.append(f'{label}: the start gap is saved wrongly.')
            if c.shift.status != Shift.Status.CLOSED:
                continue
            if None in (c.balance_end, c.expected_end, c.difference_end):
                self.problems.append(f'{label}: the shift is closed but its wallet check has no end numbers.')
                continue
            moved = (
                WalletTransaction.objects.filter(
                    wallet_id=c.wallet_id, timestamp__gt=c.started_at, timestamp__lte=c.shift.end_time)
                .aggregate(t=Sum('amount'))['t'] or ZERO
            )
            if c.expected_end != c.balance_start + moved:
                self.problems.append(
                    f'{label}: expected {c.expected_end} at the end but the entries add up to {c.balance_start + moved}.')
            if c.difference_end != c.balance_end - c.expected_end:
                self.problems.append(f'{label}: the end gap is saved wrongly.')