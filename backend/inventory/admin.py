from django.contrib import admin
from config.admin_utils import ReadOnlyAdmin, ReadOnlyInline
from .models import (
    Category, PriceTier, Product, ProductUnit, Restock, StockMovement, Supplier,
)


class ProductUnitInline(admin.TabularInline):
    model = ProductUnit
    


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'base_unit', 'cost_price', 'stock_qty', 'needs_recount','is_active')
    list_filter = ('category', 'is_active','needs_recount')
    search_fields = ('name', 'units__barcode')
    inlines = [ProductUnitInline]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'product', 'type', 'quantity', 'balance_after', 'user')
    list_filter = ('type',)

@admin.register(Category)
class CategoryAdmin(ReadOnlyAdmin):
    pass

@admin.register(PriceTier)
class PriceTierAdmin(ReadOnlyAdmin):
    pass

admin.site.register(Supplier)