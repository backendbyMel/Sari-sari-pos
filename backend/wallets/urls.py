from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register('owner/load-networks', views.LoadNetworkViewSet)
router.register('owner/load-products', views.LoadProductViewSet)

urlpatterns = [
    path('load/products/', views.LoadCatalogView.as_view(), name='load-catalog'),
    path('load/send/', views.LoadSendView.as_view(), name='load-send'),
    path('load/mine/', views.LoadMineView.as_view(), name='load-mine'),
    path('load/<int:pk>/fail/', views.LoadFailView.as_view(), name='load-fail'),
    path('wallets/topup/', views.TopUpView.as_view(), name='wallet-topup'),
    path('owner/wallet/', views.OwnerWalletView.as_view(), name='owner-wallet'),
    path('owner/wallet/adjust/', views.WalletAdjustView.as_view(), name='owner-wallet-adjust'),
    path('', include(router.urls)),
]