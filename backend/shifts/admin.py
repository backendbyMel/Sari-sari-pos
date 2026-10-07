from django.contrib import admin

from config.admin_utils import ReadOnlyAdmin

from .models import Shift
# Register your models here.

@admin.register(Shift)
class ShiftAdmin(ReadOnlyAdmin):
    list_display = (
        'id', 'cashier', 'status', 'start_time', 'opening_cash',
        'previous_closing_cash', 'opening_difference',
    )
    list_filter = ('status', 'cashier')