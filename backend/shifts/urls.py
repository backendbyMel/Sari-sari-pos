from django.urls import path

from . import views

urlpatterns = [
    path('shifts/start/', views.ShiftStartView.as_view(), name='shift-start'),
    path('shifts/current/', views.CurrentShiftView.as_view(), name='shift-current'),
]