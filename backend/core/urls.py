from django.urls import path

from . import views

urlpatterns = [
    path('settings/', views.OwnerSettingsView.as_view(), name='settings'),
    path('settings/public/', views.PublicSettingsView.as_view(), name='settings-public'),
]