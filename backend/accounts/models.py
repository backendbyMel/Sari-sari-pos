from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class CustomUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', 'OWNER')
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        OWNER = 'OWNER', 'Owner/Admin'
        CASHIER = 'CASHIER', 'Cashier'

    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.CASHIER
    )
    pin_hash = models.CharField(max_length=128, blank=True)
    pin_failed_attempts = models.PositiveSmallIntegerField(default=0)
    pin_locked = models.BooleanField(default=False)

    objects = CustomUserManager()

    def set_pin(self, raw_pin):
        if not (raw_pin.isdigit() and 4 <= len(raw_pin) <= 6):
            raise ValueError('PIN must be 4 to 6 digits.')
        self.pin_hash = make_password(raw_pin)

    def check_pin(self, raw_pin):
        return bool(self.pin_hash) and check_password(raw_pin, self.pin_hash)

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    def __str__(self):
        return f'{self.username} ({self.role})'