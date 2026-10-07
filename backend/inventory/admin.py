from django.contrib import admin

from .models import (
    Category, PriceTier, Product, ProductUnit, Restock, StockMovement, Supplier,
)


class ProductUnitInline(admin.TabularInline):
    model = ProductUnit
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'base_unit', 'cost_price', 'stock_qty', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'units__barcode')
    inlines = [ProductUnitInline]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'product', 'type', 'quantity', 'balance_after', 'user')
    list_filter = ('type',)

    # Read-only: nobody can add, edit, or delete history through the admin.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Category)
admin.site.register(PriceTier)
admin.site.register(Supplier)
admin.site.register(Restock)