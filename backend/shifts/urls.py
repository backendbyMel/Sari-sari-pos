from django.urls import path

from . import views

urlpatterns = [
    path('shifts/', views.ShiftListView.as_view(), name='shift-list'),
    path('shifts/start/', views.ShiftStartView.as_view(), name='shift-start'),
    path('shifts/current/', views.CurrentShiftView.as_view(), name='shift-current'),
    path('shifts/end/', views.ShiftEndView.as_view(), name='shift-end'),
    path('shifts/<int:pk>/close/', views.ShiftOwnerCloseView.as_view(), name='shift-owner-close'),
    path('shifts/<int:pk>/reopen/', views.ShiftReopenView.as_view(), name='shift-reopen'),
]