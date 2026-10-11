from django.urls import path

from . import report_views, views

urlpatterns = [
    path('owner/dashboard/', views.DashboardView.as_view(), name='owner-dashboard'),
    path('owner/reports/sales/', report_views.SalesReportView.as_view(), name='report-sales'),
    path('owner/reports/hourly/', report_views.HourlyReportView.as_view(), name='report-hourly'),
    path('owner/reports/best-sellers/', report_views.BestSellersView.as_view(), name='report-best-sellers'),
    path('owner/reports/slow-movers/', report_views.SlowMoversView.as_view(), name='report-slow-movers'),
]