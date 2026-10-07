from django.urls import path

from . import views

urlpatterns = [
    path('sales/', views.SaleCreateView.as_view(), name='sale-create'),
    path('sales/recent/', views.RecentSalesView.as_view(), name='sales-recent'),
    path('receipts/<str:receipt_no>/', views.ReceiptDetailView.as_view(), name='receipt-detail'),
    path('receipts/<str:receipt_no>/reprint/', views.ReceiptReprintView.as_view(), name='receipt-reprint'),
    
]