from django.contrib import admin

from config.admin_utils import ReadOnlyAdmin

from .models import Shift, ShiftReopen, CashMovement
# Register your models here.
@admin.register(Shift)
class ShiftAdmin(ReadOnlyAdmin):
    list_display = (
        'id', 'cashier', 'status', 'start_time', 'end_time','opening_cash', 'expected_cash', 'counted_cash', 'variance','closed_by',
        'opening_difference',
    )
    list_filter = ('status', 'cashier')

@admin.register(ShiftReopen)
class ShiftReopenAdmin(ReadOnlyAdmin):
    list_display = ('shift', 'reopened_by', 'timestamp', 'reason', 'previous_counted_cash', 'previous_variance')

@admin.register(CashMovement)
class CashMovementAdmin(ReadOnlyAdmin):
    list_display = ('timestamp', 'shift', 'type', 'amount', 'reason', 'recorded_by')
    list_filter = ('type',)