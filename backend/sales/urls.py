from django.urls import path

from . import views, void_views

urlpatterns = [
    path('sales/', views.SaleCreateView.as_view(), name='sale-create'),
    path('sales/recent/', views.RecentSalesView.as_view(), name='sales-recent'),
    path('sales/<str:receipt_no>/void-request/', void_views.VoidRequestView.as_view(), name='void-request'),
    path('receipts/<str:receipt_no>/', views.ReceiptDetailView.as_view(), name='receipt-detail'),
    path('receipts/<str:receipt_no>/reprint/', views.ReceiptReprintView.as_view(), name='receipt-reprint'),
    path('voids/mine/', void_views.MyVoidsView.as_view(), name='voids-mine'),
    path('voids/', void_views.OwnerVoidListView.as_view(), name='voids-list'),
    path('voids/<int:pk>/approve/', void_views.VoidApproveView.as_view(), name='void-approve'),
    path('voids/<int:pk>/reject/', void_views.VoidRejectView.as_view(), name='void-reject'),
]