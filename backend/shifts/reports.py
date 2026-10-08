from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from inventory.models import Product, StockMovement
from sales.models import Sale, SaleItem

from .models import CashMovement, Shift, ShiftReport
from .services import shift_totals

ZERO = Decimal('0')
MONEY = Decimal('0.01')
BILLS = ['1000', '500', '200', '100', '50', '20']


def build_report_data(shift, *, owner, report_no):
    totals = shift_totals(shift)
    completed = Sale.objects.filter(shift=shift, status=Sale.Status.COMPLETED)
    voided = Sale.objects.filter(shift=shift, status=Sale.Status.VOIDED)

    rows, product_ids = {}, set()
    items = (
        SaleItem.objects.filter(sale__shift=shift, sale__status=Sale.Status.COMPLETED)
        .select_related('product', 'product_unit')
        .order_by('product__name', 'product_unit__pieces_per_unit', 'id')
    )
    for item in items:
        product_ids.add(item.product_id)
        row = rows.setdefault(
            (item.product_id, item.product_unit_id),
            {'name': item.product.name, 'unit': item.product_unit.unit_name,
             'quantity': ZERO, 'amount': ZERO},
        )
        row['quantity'] += item.quantity
        row['amount'] += item.line_total
        if owner:   # cost exists ONLY in the owner copy's data
            row['cost'] = row.get('cost', ZERO) + item.unit_cost * item.quantity
    item_rows = list(rows.values())
    if owner:
        for row in item_rows:
            row['profit'] = (row['amount'] - row.pop('cost')).quantize(MONEY, ROUND_HALF_UP)

    data = {
        'owner': owner,
        'report_no': report_no,
        'store': dict(settings.STORE),
        'shift': {
            'id': shift.pk,
            'cashier': shift.cashier.username,
            'start': shift.start_time,
            'end': shift.end_time,
            'closed_by': shift.closed_by.username if shift.closed_by_id else None,
            'closed_on_behalf': bool(shift.closed_by_id and shift.closed_by_id != shift.cashier_id),
            'close_reason': shift.close_reason,
        },
        'sales_count': totals['sales_count'],
        'sales_total': totals['sales_total'],
        'items': item_rows,
        'remaining': [
            {'name': p.name, 'stock': p.stock_qty, 'unit': p.base_unit, 'needs_recount': p.needs_recount}
            for p in Product.objects.filter(pk__in=product_ids).order_by('name')
        ],
        'opening_cash': shift.opening_cash,
        'cash_sales': totals['cash_sales'],
        'payouts_total': totals['payouts_total'],
        'expected_cash': shift.expected_cash,
        'counted_cash': shift.counted_cash,
        'variance': shift.variance,
        'denominations': shift.denominations,
        'payouts': [
            {'time': m.timestamp, 'by': m.recorded_by.username, 'reason': m.reason, 'amount': m.amount}
            for m in shift.cash_movements.filter(type=CashMovement.Type.OUT)
            .select_related('recorded_by').order_by('timestamp', 'id')
        ],
        'adjustments': [
            {'time': m.timestamp, 'product': m.product.name, 'quantity': m.quantity,
             'reason': m.reason, 'by': m.user.username}
            for m in StockMovement.objects.filter(
                type=StockMovement.Type.ADJUSTMENT,
                timestamp__gte=shift.start_time, timestamp__lte=shift.end_time,
            ).select_related('product', 'user').order_by('timestamp', 'id')
        ],
        'voided_count': voided.count(),
        'voided_total': voided.aggregate(t=Sum('total'))['t'] or ZERO,
        'discounts_total': completed.aggregate(t=Sum('discount'))['t'] or ZERO,
    }
    if owner:
        data['total_profit'] = sum((r['profit'] for r in item_rows), ZERO)
        data['previous_closing_cash'] = shift.previous_closing_cash
        data['opening_difference'] = shift.opening_difference
        data['reopen_count'] = shift.reopens.count()
    return data


_base = getSampleStyleSheet()
BODY = ParagraphStyle('body', parent=_base['Normal'], fontSize=9, leading=11)
SMALL = ParagraphStyle('small', parent=BODY, fontSize=8, leading=10, textColor=colors.HexColor('#555555'))
BOLD = ParagraphStyle('bold', parent=BODY, fontName='Helvetica-Bold', fontSize=10)
H1 = ParagraphStyle('h1', parent=_base['Title'], fontSize=16, leading=19, alignment=0, spaceAfter=2)
H2 = ParagraphStyle('h2', parent=_base['Heading2'], fontSize=11, leading=13, spaceBefore=10, spaceAfter=4)


def P(text, style=BODY):
    return Paragraph(escape(str(text)), style)


def php(value):
    value = Decimal(value)
    return ('-' if value < 0 else '') + f'PHP {abs(value):,.2f}'


def signed(value):
    value = Decimal(value)
    return ('+' if value > 0 else '-' if value < 0 else '') + f'PHP {abs(value):,.2f}'


def qty(value):
    return format(Decimal(value).normalize(), 'f')


def stamp(moment):
    return timezone.localtime(moment).strftime('%Y-%m-%d %I:%M %p') if moment else '-'


def grid(rows, widths, right=(), header=True, bold_rows=()):
    table = Table(rows, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
    commands = [
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]
    if header:
        commands += [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5e7eb')),
                     ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold')]
    for column in right:
        commands.append(('ALIGN', (column, 0), (column, -1), 'RIGHT'))
    for row in bold_rows:
        commands.append(('FONTNAME', (0, row), (-1, row), 'Helvetica-Bold'))
    table.setStyle(TableStyle(commands))
    return table


def render_pdf(data):
    owner = data['owner']
    label = 'OWNER COPY - confidential' if owner else 'CASHIER COPY'
    shift = data['shift']
    variance = Decimal(data['variance'])
    word = 'SHORT' if variance < 0 else 'OVER' if variance > 0 else 'EXACT'

    story = [
        P(data['store']['name'], H1),
        P(f"{data['store']['address']}  |  {data['store']['contact']}", SMALL),
        Spacer(1, 4 * mm),
        P(f"SHIFT REPORT {data['report_no']}  -  {label}", BOLD),
        Spacer(1, 2 * mm),
        grid([['Cashier', shift['cashier'], 'Shift no.', str(shift['id'])],
              ['Started', stamp(shift['start']), 'Ended', stamp(shift['end'])]],
             [25, 65, 25, 65], header=False),
    ]
    if shift['closed_on_behalf']:
        story += [Spacer(1, 2 * mm),
                  P(f"Closed by {shift['closed_by']} on the cashier's behalf. Reason: {shift['close_reason']}")]

    summary = [['Transactions', str(data['sales_count'])], ['Total sales', php(data['sales_total'])]]
    if owner:
        summary.append(['Gross profit on goods', php(data['total_profit'])])
    story += [P('Summary', H2), grid(summary, [90, 90], right=(1,), header=False)]

    story += [P('Cash', H2), grid(
        [['Opening cash', php(data['opening_cash'])],
         ['+ Cash sales', php(data['cash_sales'])],
         ['- Pay-outs', php(data['payouts_total'])],
         ['Expected cash', php(data['expected_cash'])],
         ['Counted cash', php(data['counted_cash'])],
         [f'Variance ({word})', signed(variance)]],
        [90, 90], right=(1,), header=False, bold_rows=(3, 4, 5))]

    if data['denominations']:
        counts = data['denominations']
        rows = [['Bills / coins', 'Count', 'Amount']]
        for bill in BILLS:
            count = int(counts.get(bill, 0))
            if count:
                rows.append([f'PHP {bill} bills', str(count), php(Decimal(bill) * count)])
        if Decimal(counts.get('coins', '0')) > 0:
            rows.append(['Coins (total)', '', php(Decimal(counts['coins']))])
        story += [P('Cash count by denomination', H2), grid(rows, [70, 40, 70], right=(1, 2))]

    story.append(P('Items sold', H2))
    if data['items']:
        if owner:
            rows = [['Item', 'Unit', 'Qty', 'Amount', 'Profit']]
            rows += [[P(r['name']), r['unit'], qty(r['quantity']), php(r['amount']), php(r['profit'])]
                     for r in data['items']]
            rows.append(['TOTAL', '', '', php(data['sales_total']), php(data['total_profit'])])
            story.append(grid(rows, [75, 22, 22, 30, 31], right=(2, 3, 4), bold_rows=(len(rows) - 1,)))
        else:
            rows = [['Item', 'Unit', 'Qty', 'Amount']]
            rows += [[P(r['name']), r['unit'], qty(r['quantity']), php(r['amount'])] for r in data['items']]
            rows.append(['TOTAL', '', '', php(data['sales_total'])])
            story.append(grid(rows, [95, 25, 25, 35], right=(2, 3), bold_rows=(len(rows) - 1,)))
    else:
        story.append(P('No sales in this shift.'))

    story.append(P('Remaining stock of items that sold', H2))
    if data['remaining']:
        rows = [['Item', 'Remaining now']]
        for r in data['remaining']:
            text = f"{qty(r['stock'])} {r['unit']}" + ('  (needs recount)' if r['needs_recount'] else '')
            rows.append([P(r['name']), text])
        story.append(grid(rows, [110, 70]))
    else:
        story.append(P('None.'))

    story.append(P('Drawer pay-outs', H2))
    if data['payouts']:
        rows = [['Time', 'By', 'Reason', 'Amount']]
        rows += [[stamp(p['time']), p['by'], P(p['reason']), php(p['amount'])] for p in data['payouts']]
        story.append(grid(rows, [38, 25, 82, 35], right=(3,)))
    else:
        story.append(P('None.'))

    story.append(P('Stock adjustments made during this shift', H2))
    if data['adjustments']:
        rows = [['Time', 'Item', 'Qty', 'Reason', 'By']]
        rows += [[stamp(a['time']), P(a['product']), f"{'+' if a['quantity'] > 0 else ''}{qty(a['quantity'])}",
                  P(a['reason']), a['by']] for a in data['adjustments']]
        story.append(grid(rows, [32, 45, 18, 60, 25], right=(2,)))
    else:
        story.append(P('None.'))

    story += [P('Voids and discounts', H2), grid(
        [['Voided sales', f"{data['voided_count']} ({php(data['voided_total'])})"],
         ['Discounts given', php(data['discounts_total'])]],
        [90, 90], right=(1,), header=False)]

    if owner:
        rows = []
        if data['opening_difference'] is not None:
            rows.append(['Opening cash vs last closing count',
                         f"{signed(data['opening_difference'])} (last count {php(data['previous_closing_cash'])})"])
        rows.append(['Times this shift was reopened', str(data['reopen_count'])])
        story += [P('Owner notes', H2), grid(rows, [90, 90], right=(1,), header=False)]

    story += [Spacer(1, 4 * mm),
              P('Utang, mobile load, e-wallet and spot-check sections will appear here once those features exist.', SMALL),
              Spacer(1, 6 * mm)]
    signatures = Table([['', '', ''], ['Cashier signature', '', 'Owner signature']],
                       colWidths=[80 * mm, 20 * mm, 80 * mm], rowHeights=[16 * mm, None])
    signatures.setStyle(TableStyle([
        ('LINEABOVE', (0, 1), (0, 1), 0.5, colors.black),
        ('LINEABOVE', (2, 1), (2, 1), 0.5, colors.black),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(signatures)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.drawString(15 * mm, 10 * mm, f"{data['report_no']}  -  {label}")
        canvas.drawRightString(195 * mm, 10 * mm, f'Page {doc.page}')
        canvas.restoreState()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=18 * mm,
        title=f"Shift report {data['report_no']}", author=data['store']['name'],
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def current_reports(shifts):
    """{shift id: its CURRENT report}. A report from before a reopen is no longer current."""
    by_id = {s.pk: s for s in shifts}
    found = {}
    for report in ShiftReport.objects.filter(shift_id__in=list(by_id)).order_by('version'):
        if report.closed_at == by_id[report.shift_id].end_time:
            found[report.shift_id] = report
    return found


def generate_shift_report(shift_id):
    """Makes both PDFs for a CLOSED shift. If the current close already has a report, returns it."""
    with transaction.atomic():
        shift = (
            Shift.objects.select_for_update(of=('self',)).select_related('cashier', 'closed_by').get(pk=shift_id)
        )
        if shift.status != Shift.Status.CLOSED:
            raise ValueError('Only a closed shift has a report.')
        existing = current_reports([shift]).get(shift.pk)
        if existing:
            return existing

        version = shift.reports.count() + 1
        report_no = f'SH-{shift.pk:06d}' + ('' if version == 1 else f'-R{version}')
        folder = Path(settings.REPORTS_ROOT)
        folder.mkdir(parents=True, exist_ok=True)
        stem = f'shift-{shift.pk:06d}-v{version}'
        cashier_file, owner_file = f'{stem}-cashier.pdf', f'{stem}-owner.pdf'

        (folder / cashier_file).write_bytes(
            render_pdf(build_report_data(shift, owner=False, report_no=report_no)))
        (folder / owner_file).write_bytes(
            render_pdf(build_report_data(shift, owner=True, report_no=report_no)))

        return ShiftReport.objects.create(
            shift=shift, version=version, report_no=report_no, closed_at=shift.end_time,
            cashier_file=cashier_file, owner_file=owner_file,
        )