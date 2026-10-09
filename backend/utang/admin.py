from django.contrib import admin

from config.admin_utils import ReadOnlyAdmin

from .models import Customer, UtangPayment, BadDebtWriteOff

# Register your models here.
@admin.register(Customer)
class CustomerAdmin(ReadOnlyAdmin):
    list_display = ('name', 'contact', 'balance', 'credit_limit', 'is_active', 'created_by')
    search_fields = ('name', 'contact')


@admin.register(UtangPayment)
class UtangPaymentAdmin(ReadOnlyAdmin):
    list_display = ('timestamp', 'customer', 'amount', 'balance_after', 'received_by', 'shift', 'receipt_no')

@admin.register(BadDebtWriteOff)
class BadDebtWriteOffAdmin(ReadOnlyAdmin):
    list_display = ('timestamp', 'customer', 'amount', 'balance_after', 'reason', 'written_off_by')