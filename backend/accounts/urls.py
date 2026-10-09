from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='login'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', views.me, name='me'),
    path('owner-check/', views.owner_check, name='owner_check'),
    path('pin-login/', views.PinLoginView.as_view(), name='pin-login'),
]