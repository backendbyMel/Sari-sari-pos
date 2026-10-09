from django.urls import path

from . import owner_views, views

urlpatterns = [
    path('customers/', views.CustomerListCreateView.as_view(), name='customers'),
    path('customers/<int:pk>/', views.CustomerDetailView.as_view(), name='customer-detail'),
    path('utang/payments/', views.UtangPaymentView.as_view(), name='utang-payment'),
    path('owner/customers/', owner_views.OwnerCustomerListView.as_view(), name='owner-customers'),
    path('owner/customers/<int:pk>/', owner_views.OwnerCustomerDetailView.as_view(), name='owner-customer'),
    path('owner/customers/<int:pk>/write-off/', owner_views.WriteOffView.as_view(), name='owner-writeoff'),
]