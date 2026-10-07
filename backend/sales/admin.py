from django.contrib import admin
from .models import Receipt, Sale, SaleItem
from config.admin_utils import ReadOnlyAdmin, ReadOnlyInline
# Register your models here.
class SaleItemInline(admin.TabularInline):
    model = SaleItem
    

@admin.register(Sale)
class SaleAdmin(ReadOnlyAdmin):
    list_display = ('receipt_no', 'cashier', 'payment_type', 'total', 'status', 'timestamp')
    list_filter = ('status', 'payment_type')
    inlines = [SaleItemInline]


@admin.register(Receipt)
class ReceiptAdmin(ReadOnlyAdmin):
    list_display = ('receipt_no', 'source', 'printed_count', 'created_at')