from django.contrib import admin
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User
# Register your models here.

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('Store role', {'fields': ('role',)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('Store role', {'fields': ('role',)}),)
    list_display = ('username', 'role', 'is_active')
    list_filter = ('role', 'is_active')

    def has_delete_permission(self, request, obj=None):
        return False


