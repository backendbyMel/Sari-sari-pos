from django.urls import path

from . import export_views, report_views, views

urlpatterns = [
    path('owner/dashboard/', views.DashboardView.as_view(), name='owner-dashboard'),
    path('owner/reports/sales/', report_views.SalesReportView.as_view(), name='report-sales'),
    path('owner/reports/hourly/', report_views.HourlyReportView.as_view(), name='report-hourly'),
    path('owner/reports/best-sellers/', report_views.BestSellersView.as_view(), name='report-best-sellers'),
    path('owner/reports/slow-movers/', report_views.SlowMoversView.as_view(), name='report-slow-movers'),
    path('owner/reports/inventory/', report_views.InventoryReportView.as_view(), name='report-inventory'),
    path('owner/reports/shopping-list/', report_views.ShoppingListView.as_view(), name='report-shopping-list'),
    path('owner/exports/sales/', export_views.ExportView.as_view(kind='sales'), name='export-sales'),
    path('owner/exports/best-sellers/', export_views.ExportView.as_view(kind='best-sellers'), name='export-best-sellers'),
    path('owner/exports/slow-movers/', export_views.ExportView.as_view(kind='slow-movers'), name='export-slow-movers'),
    path('owner/exports/inventory/', export_views.ExportView.as_view(kind='inventory'), name='export-inventory'),
    path('owner/exports/shopping-list/', export_views.ExportView.as_view(kind='shopping-list'), name='export-shopping-list'),
]