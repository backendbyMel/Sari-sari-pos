from django.contrib import admin

from config.admin_utils import ReadOnlyAdmin

from .models import LoadNetwork, LoadProduct, LoadTransaction, Wallet, WalletTransaction

# Register your models here.
@admin.register(Wallet)
class WalletAdmin(ReadOnlyAdmin):
    list_display = ('provider', 'type', 'balance', 'low_level', 'is_active')


@admin.register(WalletTransaction)
class WalletTransactionAdmin(ReadOnlyAdmin):
    list_display = ('timestamp', 'wallet', 'type', 'amount', 'balance_after', 'source', 'user', 'shift')
    list_filter = ('type',)


@admin.register(LoadNetwork)
class LoadNetworkAdmin(ReadOnlyAdmin):
    list_display = ('name', 'rebate_percent', 'is_active')


@admin.register(LoadProduct)
class LoadProductAdmin(ReadOnlyAdmin):
    list_display = ('network', 'name', 'face_value', 'selling_price', 'is_active')


@admin.register(LoadTransaction)
class LoadTransactionAdmin(ReadOnlyAdmin):
    list_display = ('timestamp', 'receipt_no', 'network_name', 'product_name', 'price_charged',
                    'status', 'cashier', 'shift')
    list_filter = ('status', 'network_name')