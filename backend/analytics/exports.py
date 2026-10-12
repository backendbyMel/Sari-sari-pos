import csv
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from rest_framework.exceptions import ValidationError

from shifts.reports import BODY, BOLD, H1, SMALL, P, grid, php

from .inventory_reports import inventory_value, shopping_list
from .report_views import int_param
from .sales_reports import TRUNC, best_sellers, parse_range, sales_report, slow_movers

FORMULA_START = ('=', '+', '-', '@', '\t', '\r')
TALL = ParagraphStyle('tall', parent=BODY, leading=26)   


def safe_text(value):
    text = '' if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_START) else text


def csv_response(filename, header, rows, text_cols=()):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'private, no-store'
    response.write('\ufeff')                       # lets Excel read letters like n-tilde correctly
    writer = csv.writer(response)
    writer.writerow([safe_text(h) for h in header])
    for row in rows:
        writer.writerow([
            safe_text(v) if i in text_cols else ('' if v is None else v)
            for i, v in enumerate(row)
        ])
    return response


def pdf_response(filename, title, subtitle, header, rows, widths, *, right=(), text_cols=(),
                 total=None, wide=False, notes=()):
    stamp = timezone.localtime().strftime('%Y-%m-%d %I:%M %p')
    story = [P(settings.STORE['name'], H1), P(title, BOLD), P(subtitle, SMALL), Spacer(1, 3 * mm)]
    if rows:
        body = [header]
        for row in rows:
            # Text columns go through P(), which escapes < > & so odd product names can't break the PDF.
            body.append([P(v) if i in text_cols and isinstance(v, str) else v for i, v in enumerate(row)])
        bold = ()
        if total is not None:
            body.append(total)
            bold = (len(body) - 1,)
        story.append(grid(body, widths, right=right, bold_rows=bold))
    else:
        story.append(P('Nothing to show.'))
    for note in notes:
        story += [Spacer(1, 2 * mm), P(note, SMALL)]

    footer_text = f'{title}  |  OWNER ONLY, confidential  |  made {stamp}'

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.drawString(15 * mm, 10 * mm, footer_text)
        canvas.drawRightString(doc.pagesize[0] - 15 * mm, 10 * mm, f'Page {doc.page}')
        canvas.restoreState()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4) if wide else A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=18 * mm, title=title, author=settings.STORE['name'],
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'private, no-store'
    return response


def _money(value):
    return php(Decimal(value))


def _manila_date(iso):
    return timezone.localtime(datetime.fromisoformat(iso)).strftime('%Y-%m-%d')


def sales_export(params, fmt):
    d_from, d_to, start, end = parse_range(params)
    group = params.get('group', 'day')
    if group not in TRUNC:
        raise ValidationError({'group': 'Use group=day, week or month.'})
    data = sales_report(start, end, group)
    keys = ['period', 'sales_count', 'sales_total', 'utang_total', 'goods_profit',
            'load_profit', 'fees', 'profit']
    first = {'day': 'Day', 'week': 'Week starting (Monday)', 'month': 'Month'}[group]
    header = [first, 'Sales', 'Sales total', 'On utang', 'Goods profit', 'Load profit', 'GCash fees', 'Profit']
    rows = [[r[k] for k in keys] for r in data['rows']]
    name = f'sales-{group}-{d_from}_to_{d_to}'
    if fmt == 'csv':
        return csv_response(f'{name}.csv', header, rows)

    t = data['totals']
    shown = [[r[0], r[1]] + [_money(v) for v in r[2:]] for r in rows]
    total = ['TOTAL', t['sales_count']] + [_money(t[k]) for k in keys[2:]]
    notes = [
        'Profit = goods profit + mobile load profit + GCash fees. Expenses are not subtracted yet '
        '(the expense log arrives in Phase 5).',
        f'Bad debt written off in this range: {_money(t["writeoffs"])} (shown separately, not subtracted).',
    ]
    if group == 'week':
        notes.append('Weeks start on Monday.')
    return pdf_response(
        f'{name}.pdf', 'Sales and profit', f'By {group}, {d_from} to {d_to} (Manila time)',
        header, shown, [35, 22, 35, 35, 35, 35, 35, 35], right=(1, 2, 3, 4, 5, 6, 7),
        total=total, wide=True, notes=notes)


def best_sellers_export(params, fmt):
    d_from, d_to, start, end = parse_range(params)
    rank = params.get('rank', 'quantity')
    if rank not in ('quantity', 'profit'):
        raise ValidationError({'rank': 'Use rank=quantity or rank=profit.'})
    limit = int_param(params, 'limit', 20, 1, 100)
    found = best_sellers(start, end, limit)['by_quantity' if rank == 'quantity' else 'by_profit']
    header = ['Rank', 'Product', 'Quantity', 'Unit', 'Sales', 'Profit']
    rows = [[i, r['product'], r['quantity'], r['unit'], r['sales_total'], r['profit']]
            for i, r in enumerate(found, 1)]
    name = f'best-sellers-{rank}-{d_from}_to_{d_to}'
    if fmt == 'csv':
        return csv_response(f'{name}.csv', header, rows, text_cols={1, 3})
    shown = [r[:4] + [_money(r[4]), _money(r[5])] for r in rows]
    return pdf_response(
        f'{name}.pdf', f'Best sellers by {rank}', f'{d_from} to {d_to} (Manila time), top {limit}',
        header, shown, [14, 66, 28, 22, 25, 25], right=(2, 4, 5), text_cols={1, 3},
        notes=['Quantities are in each product\'s smallest unit (sticks, pieces).'])


def slow_movers_export(params, fmt):
    days = int_param(params, 'days', 30, 1, 365)
    data = slow_movers(days)
    header = ['Product', 'In stock', 'Unit', 'Value at cost', 'Last sold', 'Days since last sale']
    rows = [[i['name'], i['stock'], i['unit'], i['value'],
             _manila_date(i['last_sold']) if i['last_sold'] else 'Never',
             '' if i['days_since'] is None else i['days_since']] for i in data['items']]
    name = f'slow-movers-{days}-days'
    if fmt == 'csv':
        return csv_response(f'{name}.csv', header, rows, text_cols={0, 2})
    shown = [[r[0], r[1], r[2], _money(r[3]), r[4], r[5]] for r in rows]
    total = ['TOTAL (all slow items)', '', '', _money(data['tied_up']), '', '']
    notes = ['Items added less than that many days ago, items with no stock, inactive items and items '
             'with no selling unit are not listed.']
    if data['count'] > len(rows):
        notes.append(f'Showing the {len(rows)} items with the most money tied up, out of {data["count"]}.')
    return pdf_response(
        f'{name}.pdf', 'Slow movers', f'Items with no sale in the last {days} days',
        header, shown, [65, 22, 20, 28, 25, 20], right=(1, 3, 5), text_cols={0, 2}, total=total, notes=notes)


def inventory_export(params, fmt):
    data = inventory_value()
    header = ['Category', 'Product', 'In stock', 'Unit', 'Cost per unit', 'Value at cost', 'Status', 'Note']
    rows = [[i['category'], i['name'], i['stock'], i['unit'], i['cost'], i['value'],
             'Active' if i['is_active'] else 'Inactive',
             'Negative stock counted as 0 (needs recount)' if i['negative'] else '']
            for i in data['items']]
    name = f'inventory-value-{timezone.localdate()}'
    if fmt == 'csv':
        return csv_response(f'{name}.csv', header, rows, text_cols={0, 1, 3})
    shown = [r[:4] + [f'PHP {r[4]}', _money(r[5]), r[6], r[7]] for r in rows]
    total = ['TOTAL', '', '', '', '', _money(data['total_value']), '', '']
    return pdf_response(
        f'{name}.pdf', 'Inventory value', f'Stock x average cost, {timezone.localdate()}',
        header, shown, [38, 70, 22, 18, 28, 32, 20, 39], right=(2, 4, 5), text_cols={0, 1, 3, 7},
        total=total, wide=True,
        notes=['Value = stock x average cost per smallest unit. Negative stock counts as 0.',
               'Inactive products that still hold stock are included.'])


def shopping_export(params, fmt):
    data = shopping_list()

    def status(i):
        return 'OUT' if i['status'] == 'out' else 'Low' + (' / recount' if i['needs_recount'] else '')

    name = f'shopping-list-{data["date"]}'
    if fmt == 'csv':
        header = ['Product', 'Category', 'In stock', 'Unit', 'Low level', 'Status',
                  'Last bought', 'Last quantity bought', 'To buy']
        rows = [[i['name'], i['category'], i['stock'], i['unit'], i['low_level'], status(i),
                 i['last_bought'] or 'Never', i['last_quantity'] or '', '']
                for i in data['items']]
        return csv_response(f'{name}.csv', header, rows, text_cols={0, 1, 3})
    header = ['Product', 'Category', 'In stock', 'Level', 'Status', 'Last bought', 'To buy']
    rows = [[i['name'], i['category'], f'{i["stock"]} {i["unit"]}', i['low_level'], status(i),
             i['last_bought'] or 'Never', Paragraph('&nbsp;', TALL)]
            for i in data['items']]
    return pdf_response(
        f'{name}.pdf', 'Shopping list', f'{data["date"]}: items at or below their low-stock level',
        header, rows, [48, 26, 24, 16, 18, 24, 24], right=(3,), text_cols={0, 1, 2},
        notes=['Write the quantity to buy in the last column. Quantities are in the smallest unit.'])


BUILDERS = {
    'sales': sales_export,
    'best-sellers': best_sellers_export,
    'slow-movers': slow_movers_export,
    'inventory': inventory_export,
    'shopping-list': shopping_export,
}