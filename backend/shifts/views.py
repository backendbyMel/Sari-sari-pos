from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCashierOrOwner, IsOwner

from .models import Shift, CashMovement
from .serializers import (
    CashMovementSerializer, OwnerShiftSerializer, PayoutCreateSerializer,
    ReasonSerializer, ShiftEndSerializer, ShiftOwnerCloseSerializer,
    ShiftResultSerializer, ShiftSerializer, ShiftStartSerializer,
)
from .services import close_shift, reopen_shift, start_shift, record_payout, shift_totals
from django.db.models import Count, Sum
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied
from decimal import Decimal
from django.shortcuts import get_object_or_404
import logging
from datetime import date
from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404
from .reports import current_reports, generate_shift_report
# Create your views here.

logger = logging.getLogger(__name__)

def money(value):
    return str(Decimal(value).quantize(Decimal('0.01')))
def make_report(shift):
    try:
        return generate_shift_report(shift.pk)
    except Exception:
        logger.exception('Could not generate the report for shift %s', shift.pk)
        return None


def report_info(report):
    return {'report_no': report.report_no, 'version': report.version} if report else None

def result_payload(shift, totals, report=None):
    return {
        'shift': ShiftResultSerializer(shift).data,
        'sales_count': totals['sales_count'],
        'cash_sales': money(totals['cash_sales']),
        'payouts_total': money(totals['payouts_total']),
        'payouts_count': totals['payouts_count'],
        'report': report_info(report),
    }

class ShiftStartView(APIView):
    permission_classes = [IsCashierOrOwner]

    def post(self, request):
        form = ShiftStartSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        shift = start_shift(
            cashier=request.user,   
            opening_cash=form.validated_data['opening_cash'],
        )
        return Response(ShiftSerializer(shift).data, status=status.HTTP_201_CREATED)


class CurrentShiftView(APIView):
    permission_classes = [IsCashierOrOwner]

    def get(self, request):
        shift = Shift.objects.select_related('cashier').filter(status=Shift.Status.OPEN).first()
        return Response({
            'shift': ShiftSerializer(shift).data if shift else None,
            'is_mine': bool(shift and shift.cashier_id == request.user.id),
        })

class ShiftEndView(APIView):
    """POST /api/shifts/end/  (Cashier+). Ends the caller's OWN open shift."""
    permission_classes = [IsCashierOrOwner]

    def post(self, request):
        form = ShiftEndSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data

        shift = Shift.objects.filter(cashier=request.user, status=Shift.Status.OPEN).first()
        if shift is None:
            raise ValidationError({'shift': 'You have no open shift to end.'})

        shift, totals = close_shift(
            shift_id=shift.pk, counted_cash=data['counted_cash'],
            denominations=data.get('denominations'), closed_by=request.user,
        )
        return Response(result_payload(shift, totals, make_report(shift)))


class ShiftOwnerCloseView(APIView):
    """POST /api/shifts/<id>/close/  (Owner only). Closes ANY open shift, with a reason."""
    permission_classes = [IsOwner]

    def post(self, request, pk):
        form = ShiftOwnerCloseSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        shift, totals = close_shift(
            shift_id=pk, counted_cash=data['counted_cash'],
            denominations=data.get('denominations'), closed_by=request.user,
            reason=data['reason'],
        )
        return Response(result_payload(shift, totals, make_report(shift)))


class ShiftReopenView(APIView):
    permission_classes = [IsOwner]

    def post(self, request, pk):
        form = ReasonSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        shift = reopen_shift(shift_id=pk, user=request.user, reason=form.validated_data['reason'])
        return Response(ShiftSerializer(shift).data)


class ShiftListView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        params = request.query_params
        shifts = Shift.objects.select_related('cashier', 'closed_by').annotate(reopen_count=Count('reopens'))

        errors = {}
        for key, lookup in (('date_from', 'start_time__date__gte'), ('date_to', 'start_time__date__lte')):
            if params.get(key):
                try:
                    shifts = shifts.filter(**{lookup: date.fromisoformat(params[key])})
                except ValueError:
                    errors[key] = 'Use the format YYYY-MM-DD.'
        if errors:
            raise ValidationError(errors)
        if params.get('cashier', '').isdigit():
            shifts = shifts.filter(cashier_id=params['cashier'])
        if params.get('variance') == '1':
            shifts = shifts.filter(variance__isnull=False).exclude(variance=0)

        shifts = list(shifts.order_by('-start_time', '-id')[:100])
        paid = {
            row['shift']: row
            for row in CashMovement.objects.filter(
                shift__in=[s.pk for s in shifts], type=CashMovement.Type.OUT
            ).values('shift').annotate(total=Sum('amount'), count=Count('id'))
        }
        reports = current_reports(shifts)
        rows = []
        for row in OwnerShiftSerializer(shifts, many=True).data:
            entry = dict(row)
            found = paid.get(row['id'])
            entry['payouts_total'] = money(found['total']) if found else '0.00'
            entry['payouts_count'] = found['count'] if found else 0
            entry['report'] = report_info(reports.get(row['id']))
            rows.append(entry)
        return Response(rows)
    
class ShiftPayoutView(APIView):
    permission_classes = [IsCashierOrOwner]

    def post(self, request):
        form = PayoutCreateSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        movement, warnings = record_payout(
            user=request.user,   # from the login, never from the request body
            amount=form.validated_data['amount'],
            reason=form.validated_data['reason'],
        )
        return Response(
            {'payout': CashMovementSerializer(movement).data, 'warnings': warnings},
            status=status.HTTP_201_CREATED,
        )


class ShiftSummaryView(APIView):
    permission_classes = [IsCashierOrOwner]

    def get(self, request):
        shift = (
            Shift.objects.select_related('cashier')
            .filter(cashier=request.user, status=Shift.Status.OPEN)
            .first()
        )
        if shift is None:
            return Response({'shift': None})
        totals = shift_totals(shift)
        payouts = shift.cash_movements.filter(type=CashMovement.Type.OUT).select_related('recorded_by')
        return Response({
            'shift': ShiftSerializer(shift).data,
            'sales_count': totals['sales_count'],
            'sales_total': money(totals['sales_total']),
            'payouts_total': money(totals['payouts_total']),
            'payouts': CashMovementSerializer(payouts, many=True).data,
        })


class ShiftPayoutsOwnerView(APIView):
    permission_classes = [IsOwner]

    def get(self, request, pk):
        shift = get_object_or_404(Shift, pk=pk)
        payouts = shift.cash_movements.select_related('recorded_by')
        return Response(CashMovementSerializer(payouts, many=True).data)

class MyShiftsView(APIView):
    permission_classes = [IsCashierOrOwner]

    def get(self, request):
        shifts = list(
            Shift.objects.select_related('cashier', 'closed_by')
            .filter(cashier=request.user, status=Shift.Status.CLOSED)
            .order_by('-end_time', '-id')[:30]
        )
        reports = current_reports(shifts)
        rows = []
        for shift, row in zip(shifts, ShiftResultSerializer(shifts, many=True).data):
            entry = dict(row)
            entry['report'] = report_info(reports.get(shift.pk))
            rows.append(entry)
        return Response(rows)


class ShiftReportDownloadView(APIView):
    permission_classes = [IsCashierOrOwner]

    def get(self, request, pk):
        copy = request.query_params.get('copy', 'cashier')
        if copy not in ('cashier', 'owner'):
            raise ValidationError({'copy': 'Use copy=cashier or copy=owner.'})
        user = request.user
        if copy == 'owner' and not user.is_owner:
            raise PermissionDenied('Only the owner can download the owner copy.')

        shift = get_object_or_404(Shift, pk=pk)
        if not user.is_owner and shift.cashier_id != user.id:
            raise Http404   # not theirs: we don't even confirm that it exists

        report = current_reports([shift]).get(shift.pk)
        if report is None:
            raise NotFound('There is no report for this shift yet.')

        path = Path(settings.REPORTS_ROOT) / (report.owner_file if copy == 'owner' else report.cashier_file)
        if not path.is_file():
            raise NotFound('The report file is missing on the server. Tell the owner.')

        disposition = 'attachment' if request.query_params.get('download') == '1' else 'inline'
        response = FileResponse(path.open('rb'), content_type='application/pdf')
        response['Content-Disposition'] = f'{disposition}; filename="{report.report_no}-{copy}.pdf"'
        response['Cache-Control'] = 'private, no-store'
        return response


class ShiftReportGenerateView(APIView):
    permission_classes = [IsOwner]

    def post(self, request, pk):
        shift = get_object_or_404(Shift, pk=pk)
        if shift.status != Shift.Status.CLOSED:
            raise ValidationError({'shift': 'Only a closed shift has a report.'})
        return Response({'report': report_info(generate_shift_report(shift.pk))})