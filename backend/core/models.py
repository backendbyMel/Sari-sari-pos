from django.db import models
from django.conf import settings

# Create your models here.
class Setting(models.Model):
    key = models.CharField(max_length=50, unique=True)
    value = models.CharField(max_length=200)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+'
    )
    updated_at = models.DateTimeField(auto_now=True)

    def delete(self, *args, **kwargs):
        raise PermissionError('Settings cannot be deleted. Change the value instead.')

    def __str__(self):
        return f'{self.key} = {self.value}'