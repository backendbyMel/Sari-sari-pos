from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsCashierOrOwner, IsOwner

from .models import Category, PriceTier, Product, ProductUnit
from .serializers import (
    CategorySerializer, PriceTierSerializer, ProductLookupSerializer,
    ProductSerializer, ProductUnitSerializer,
)


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