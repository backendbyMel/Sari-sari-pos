from django.urls import path

from . import views

urlpatterns = [
    path('customers/', views.CustomerListCreateView.as_view(), name='customers'),
    path('customers/<int:pk>/', views.CustomerDetailView.as_view(), name='customer-detail'),
    path('utang/payments/', views.UtangPaymentView.as_view(), name='utang-payment'),
]