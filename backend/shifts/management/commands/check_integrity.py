from decimal import ROUND_HALF_UP, Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Sum

from inventory.models import Product, StockMovement
from sales.models import Receipt, ReceiptCounter, Sale, SaleItem
from shifts.models import CashMovement, Shift
from shifts.reports import current_reports
from shifts.services import shift_totals

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
        covered = set()
        for r in receipts:
            if r.source == Receipt.Source.SALE:
                covered.add(r.source_id)
                if sale_numbers.get(r.source_id) != r.receipt_no:
                    self.problems.append(f'Receipt {r.receipt_no} does not match any sale.')
        for sale_id, number in sale_numbers.items():
            if sale_id not in covered:
                self.problems.append(f'Sale {number} has no receipt record.')

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
            expected = s.opening_cash + totals['cash_sales'] - totals['payouts_total']
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