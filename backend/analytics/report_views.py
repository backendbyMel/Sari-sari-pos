from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsOwner

from .sales_reports import (
    TRUNC, best_sellers, by_cashier, by_category, hourly, parse_range, sales_report, slow_movers,
)
from .inventory_reports import inventory_value, shopping_list

def int_param(params, key, default, low, high):
    raw = params.get(key)
    if raw in (None, ''):
        return default
    if not raw.isdigit() or not low <= int(raw) <= high:
        raise ValidationError({key: f'Use a whole number from {low} to {high}.'})
    return int(raw)


def range_info(d_from, d_to):
    return {'date_from': d_from.isoformat(), 'date_to': d_to.isoformat()}


class SalesReportView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        d_from, d_to, start, end = parse_range(request.query_params)
        group = request.query_params.get('group', 'day')
        if group not in TRUNC:
            raise ValidationError({'group': 'Use group=day, week or month.'})
        return Response({
            **range_info(d_from, d_to), 'group': group,
            **sales_report(start, end, group),
            'by_cashier': by_cashier(start, end),
            'by_category': by_category(start, end),
        })


class HourlyReportView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        d_from, d_to, start, end = parse_range(request.query_params)
        return Response({**range_info(d_from, d_to), **hourly(start, end)})


class BestSellersView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        d_from, d_to, start, end = parse_range(request.query_params)
        limit = int_param(request.query_params, 'limit', 20, 1, 100)
        return Response({**range_info(d_from, d_to), **best_sellers(start, end, limit)})


class SlowMoversView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        return Response(slow_movers(int_param(request.query_params, 'days', 30, 1, 365)))

class InventoryReportView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        return Response(inventory_value())


class ShoppingListView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        return Response(shopping_list())