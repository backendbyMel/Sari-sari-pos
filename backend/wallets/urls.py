from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register('owner/load-networks', views.LoadNetworkViewSet)
router.register('owner/load-products', views.LoadProductViewSet)
router.register('owner/fee-rules', views.FeeRuleViewSet, basename='fee-rule')

urlpatterns = [
    path('load/products/', views.LoadCatalogView.as_view(), name='load-catalog'),
    path('load/send/', views.LoadSendView.as_view(), name='load-send'),
    path('load/mine/', views.LoadMineView.as_view(), name='load-mine'),
    path('load/<int:pk>/fail/', views.LoadFailView.as_view(), name='load-fail'),
    path('ewallet/quote/', views.EWalletQuoteView.as_view(), name='ewallet-quote'),
    path('ewallet/cash-in/', views.EWalletSendView.as_view(kind='cash_in'), name='ewallet-cash-in'),
    path('ewallet/cash-out/', views.EWalletSendView.as_view(kind='cash_out'), name='ewallet-cash-out'),
    path('ewallet/mine/', views.EWalletMineView.as_view(), name='ewallet-mine'),
    path('wallets/topup/', views.TopUpView.as_view(), name='wallet-topup'),
    path('owner/wallet/', views.OwnerWalletView.as_view(), name='owner-wallet'),
    path('owner/wallet/adjust/', views.WalletAdjustView.as_view(), name='owner-wallet-adjust'),
    path('owner/ewallet/', views.OwnerEWalletView.as_view(), name='owner-ewallet'),
    path('owner/ewallet/<int:pk>/reverse/', views.EWalletReverseView.as_view(), name='owner-ewallet-reverse'),
    path('', include(router.urls)),
]