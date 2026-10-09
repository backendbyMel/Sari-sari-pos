from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCashierOrOwner, IsOwner
from core.services import get_cashier_can_topup
from sales.services import build_load_receipt
from shifts.models import Shift

from .mobile import mask_mobile
from .models import LoadNetwork, LoadProduct, LoadTransaction
from .serializers import (
    LoadFailSerializer, LoadNetworkSerializer, LoadProductSerializer, LoadSendSerializer,
    LowLevelSerializer, TopUpSerializer, WalletAdjustSerializer,
)
from .services import adjust_wallet, fail_load, get_load_wallet, send_load, top_up

# Create your views here.

def load_row(tx):
    return {
        'id': tx.pk, 'receipt_no': tx.receipt_no, 'network': tx.network_name, 'product': tx.product_name,
        'mobile': mask_mobile(tx.mobile_no), 'price': str(tx.price_charged),
        'reference_no': tx.reference_no, 'status': tx.status,
        'failed_note': tx.failed_note, 'timestamp': tx.timestamp,
    }

class LoadCatalogView(APIView):
    permission_classes = [IsCashierOrOwner]

    def get(self, request):
        networks = LoadNetwork.objects.filter(is_active=True).prefetch_related(
            Prefetch('products', queryset=LoadProduct.objects.filter(is_active=True).order_by('face_value', 'name'))
        )
        data = []
        for n in networks:
            products = list(n.products.all())
            if products:
                data.append({'id': n.pk, 'name': n.name, 'products': [
                    {'id': p.pk, 'name': p.name, 'selling_price': str(p.selling_price)} for p in products]})
        return Response(data)


class LoadSendView(APIView):
    permission_classes = [IsCashierOrOwner]

    def post(self, request):
        form = LoadSendSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        tx, warnings = send_load(
            cashier=request.user,   
            product_id=data['product'], mobile_no=data['mobile_no'], reference_no=data['reference_no'],
        )
        return Response(
            {'receipt': build_load_receipt(tx), 'load_id': tx.pk, 'warnings': warnings},
            status=status.HTTP_201_CREATED,
        )


class LoadFailView(APIView):
    permission_classes = [IsCashierOrOwner]

    def post(self, request, pk):
        form = LoadFailSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        tx = fail_load(user=request.user, load_id=pk, note=form.validated_data['note'])
        return Response({'receipt': build_load_receipt(tx), 'refund': str(tx.price_charged)})


class LoadMineView(APIView):
    permission_classes = [IsCashierOrOwner]

    def get(self, request):
        shift = Shift.objects.filter(cashier=request.user, status=Shift.Status.OPEN).first()
        if shift is None:
            return Response({'loads': []})
        loads = LoadTransaction.objects.filter(shift=shift).order_by('-timestamp', '-id')
        return Response({'loads': [load_row(t) for t in loads]})


class TopUpView(APIView):
    permission_classes = [IsCashierOrOwner]

    def post(self, request):
        form = TopUpSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        user = request.user
        if not user.is_owner:
            if not get_cashier_can_topup():
                raise PermissionDenied('The owner has not allowed cashiers to top up the wallet.')
            if data['source'] != 'drawer':
                raise PermissionDenied('Cashiers can only top up with cash from the drawer.')
        entry, warnings = top_up(
            user=user, amount_added=data['amount_added'], amount_paid=data['amount_paid'],
            source=data['source'], reference_no=data['reference_no'],
        )
        body = {'detail': 'Top-up recorded.', 'warnings': warnings}
        if user.is_owner:
            body['balance'] = str(entry.balance_after)
        return Response(body, status=status.HTTP_201_CREATED)



def wallet_payload(wallet):
    entries = wallet.transactions.select_related('user')[:50]
    return {
        'wallet': {
            'id': wallet.pk, 'provider': wallet.provider, 'balance': str(wallet.balance),
            'low_level': str(wallet.low_level), 'is_low': wallet.balance <= wallet.low_level,
        },
        'transactions': [
            {'id': e.pk, 'type': e.type, 'amount': str(e.amount), 'balance_after': str(e.balance_after),
             'reference_no': e.reference_no, 'source': e.source,
             'amount_paid': str(e.amount_paid) if e.amount_paid is not None else None,
             'note': e.note, 'user': e.user.username, 'shift': e.shift_id, 'timestamp': e.timestamp}
            for e in entries
        ],
    }


class OwnerWalletView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        return Response(wallet_payload(get_load_wallet()))

    def patch(self, request):
        form = LowLevelSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        wallet = get_load_wallet()
        wallet.low_level = form.validated_data['low_level']
        wallet.save(update_fields=['low_level'])
        return Response(wallet_payload(wallet))


class WalletAdjustView(APIView):
    permission_classes = [IsOwner]

    def post(self, request):
        form = WalletAdjustSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        adjust_wallet(user=request.user, actual_balance=form.validated_data['actual_balance'],
                      reason=form.validated_data['reason'])
        return Response(wallet_payload(get_load_wallet()), status=status.HTTP_201_CREATED)


class LoadNetworkViewSet(viewsets.ModelViewSet):
    queryset = LoadNetwork.objects.all()
    serializer_class = LoadNetworkSerializer
    permission_classes = [IsOwner]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']   


class LoadProductViewSet(viewsets.ModelViewSet):
    queryset = LoadProduct.objects.select_related('network')
    serializer_class = LoadProductSerializer
    permission_classes = [IsOwner]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']