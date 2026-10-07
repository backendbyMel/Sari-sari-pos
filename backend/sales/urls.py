from django.urls import path

from . import views

urlpatterns = [
    path('sales/', views.SaleCreateView.as_view(), name='sale-create'),
    path('receipts/<str:receipt_no>/', views.ReceiptDetailView.as_view(), name='receipt-detail'),
]