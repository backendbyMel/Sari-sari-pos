from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register('categories', views.CategoryViewSet)
router.register('products', views.ProductViewSet)
router.register('units', views.ProductUnitViewSet)
router.register('price-tiers', views.PriceTierViewSet)

urlpatterns = [
    path('products/lookup/', views.product_lookup, name='product-lookup'),
    path('', include(router.urls)),
    path('restocks/', views.RestockListCreateView.as_view(), name='restocks'),
]