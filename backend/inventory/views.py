from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from accounts.permissions import IsCashierOrOwner, IsOwner
from .models import Category, PriceTier, Product, ProductUnit, Restock, StockMovement
from .serializers import (
    CategorySerializer, PriceTierSerializer, ProductLookupSerializer,
    ProductSerializer, ProductUnitSerializer, RestockCreateSerializer,
    RestockSerializer, StockAdjustmentSerializer, StockMovementSerializer,
)
from rest_framework import generics, status, viewsets
from .services import record_restock, record_adjustment
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsOwner]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.prefetch_related('units__tiers')
    serializer_class = ProductSerializer
    permission_classes = [IsOwner]
    
    http_method_names = ['get', 'post', 'patch', 'head', 'options']


class ProductUnitViewSet(viewsets.ModelViewSet):
    queryset = ProductUnit.objects.select_related('product').prefetch_related('tiers')
    serializer_class = ProductUnitSerializer
    permission_classes = [IsOwner]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']


class PriceTierViewSet(viewsets.ModelViewSet):
    queryset = PriceTier.objects.all()
    serializer_class = PriceTierSerializer
    permission_classes = [IsOwner]
    

@api_view(['GET'])
@permission_classes([IsCashierOrOwner])
def product_lookup(request):
    code = request.query_params.get('code', '').strip()
    if not code:
        return Response({'detail': 'Provide ?code= (a barcode or part of a name).'}, status=400)

    products = Product.objects.filter(is_active=True).prefetch_related('units__tiers')
    matches = products.filter(units__barcode=code)        
    if not matches.exists():
        matches = products.filter(name__icontains=code)[:10] 

    if not matches:
        return Response({'detail': 'Item not found'}, status=404)
    return Response(ProductLookupSerializer(matches, many=True).data)

class RestockListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsOwner]
    serializer_class = RestockSerializer

    def get_queryset(self):
        qs = Restock.objects.select_related('product', 'supplier', 'received_by')
        product_id = self.request.query_params.get('product', '')
        if product_id.isdigit():
            qs = qs.filter(product_id=product_id)
        return qs

    def create(self, request, *args, **kwargs):
        form = RestockCreateSerializer(data=request.data)
        form.is_valid(raise_exception=True) 
        data = form.validated_data

        result = record_restock(
            product=data['product'],
            unit=data['product_unit'],
            quantity=data['quantity'],
            unit_cost=data['unit_cost'],
            supplier=data.get('supplier'),
            date=data['date'],
            delivery_receipt_no=data.get('delivery_receipt_no', ''),
            expiry_date=data.get('expiry_date'),
            user=request.user, 
        )
        product = result['product']
        return Response(
            {
                'restock': RestockSerializer(result['restock']).data,
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'stock_qty': str(product.stock_qty),
                    'old_cost_price': str(result['old_cost']),
                    'new_cost_price': str(product.cost_price),
                },
                'warnings': result['warnings'],
            },
            status=status.HTTP_201_CREATED,
        )

class StockAdjustmentView(APIView):
    permission_classes = [IsOwner]

    def post(self, request):
        form = StockAdjustmentSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data

        movement, product = record_adjustment(
            product=data['product'],
            quantity=data['quantity'],
            reason_type=data['reason_type'],
            note=data['note'],
            user=request.user, 
        )
        return Response(
            {
                'movement': StockMovementSerializer(movement).data,
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'stock_qty': str(product.stock_qty),
                    'needs_recount': product.needs_recount,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class StockHistoryPagination(PageNumberPagination):
    page_size = 50


class StockMovementListView(generics.ListAPIView):
    permission_classes = [IsOwner]
    serializer_class = StockMovementSerializer
    pagination_class = StockHistoryPagination

    def get_queryset(self):
        qs = StockMovement.objects.select_related('product', 'user')
        params = self.request.query_params
        if params.get('product', '').isdigit():
            qs = qs.filter(product_id=params['product'])
        if params.get('type') in StockMovement.Type.values:
            qs = qs.filter(type=params['type'])
        return qs