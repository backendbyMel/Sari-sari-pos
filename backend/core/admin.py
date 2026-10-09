from django.contrib import admin

from config.admin_utils import ReadOnlyAdmin

from .models import Setting

# Register your models here.
@admin.register(Setting)
class SettingAdmin(ReadOnlyAdmin):
    list_display = ('key', 'value', 'updated_by', 'updated_at')