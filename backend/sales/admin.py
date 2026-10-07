from django.contrib import admin
from .models import Receipt, Sale, SaleItem

# Register your models here.
class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Sale)
class SaleAdmin(ReadOnlyAdmin):
    list_display = ('receipt_no', 'cashier', 'payment_type', 'total', 'status', 'timestamp')
    list_filter = ('status', 'payment_type')
    inlines = [SaleItemInline]


@admin.register(Receipt)
class ReceiptAdmin(ReadOnlyAdmin):
    list_display = ('receipt_no', 'source', 'printed_count', 'created_at')