from django.contrib import admin


class ReadOnlyMixin:
    def has_add_permission(self, request, *args, **kwargs):
        return False

    def has_change_permission(self, request, *args, **kwargs):
        return False

    def has_delete_permission(self, request, *args, **kwargs):
        return False


class ReadOnlyAdmin(ReadOnlyMixin, admin.ModelAdmin):
    pass


class ReadOnlyInline(ReadOnlyMixin, admin.TabularInline):
    extra = 0
    can_delete = False