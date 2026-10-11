from django.urls import path

from . import views

urlpatterns = [
    path('owner/dashboard/', views.DashboardView.as_view(), name='owner-dashboard'),
]