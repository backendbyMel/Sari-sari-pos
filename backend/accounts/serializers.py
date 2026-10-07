from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import password_validation
from rest_framework import serializers
from .models import User

class LoginSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['role'] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'role': self.user.role,
        }
        return data
PIN_FIELD_ERRORS = {'invalid': 'PIN must be 4 to 6 digits.'}


class UserSerializer(serializers.ModelSerializer):
    has_pin = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'role', 'is_active', 'has_pin',
            'last_login', 'date_joined',
        ]
        read_only_fields = [
            'id', 'username', 'role', 'has_pin', 'last_login', 'date_joined',
        ]

    def get_has_pin(self, obj):
        return bool(obj.pin_hash)


class CashierCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    pin = serializers.RegexField(
        r'^\d{4,6}$', required=False, allow_blank=True,
        write_only=True, error_messages=PIN_FIELD_ERRORS,
    )

    class Meta:
        model = User
        fields = ['username', 'password', 'pin']

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        pin = validated_data.pop('pin', '')
        user = User(**validated_data, role=User.Role.CASHIER)
        user.set_password(password)          
        if pin:
            user.set_pin(pin)                
        user.save()
        return user


class PasswordResetSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        password_validation.validate_password(value, self.context.get('user'))
        return value


class PinSetSerializer(serializers.Serializer):
    pin = serializers.RegexField(r'^\d{4,6}$', error_messages=PIN_FIELD_ERRORS)