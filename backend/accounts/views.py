from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView

from .permissions import IsCashierOrOwner, IsOwner
from .serializers import (
    CashierCreateSerializer, LoginSerializer, PasswordResetSerializer,
    PinSetSerializer, UserSerializer,
)
from rest_framework import status, viewsets
from .models import User

class LoginRateThrottle(AnonRateThrottle):
    scope = 'login'


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_classes = [LoginRateThrottle]


@api_view(['GET'])
@permission_classes([IsCashierOrOwner])
def me(request):
    user = request.user
    return Response({'id': user.id, 'username': user.username, 'role': user.role})


@api_view(['GET'])
@permission_classes([IsOwner])
def owner_check(request):
    return Response({'message': 'Welcome, Owner. Cashiers cannot see this.'})


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.filter(role=User.Role.CASHIER).order_by('username')
    permission_classes = [IsOwner]
    serializer_class = UserSerializer
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def create(self, request, *args, **kwargs):
        form = CashierCreateSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        user = form.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        user = self.get_object()
        form = PasswordResetSerializer(data=request.data, context={'user': user})
        form.is_valid(raise_exception=True)
        user.set_password(form.validated_data['new_password'])
        user.save(update_fields=['password'])
        return Response({'detail': f'Password reset for {user.username}.'})

    @action(detail=True, methods=['post'], url_path='set-pin')
    def set_pin(self, request, pk=None):
        user = self.get_object()
        form = PinSetSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        user.set_pin(form.validated_data['pin'])
        user.save(update_fields=['pin_hash'])
        return Response({'detail': f'PIN set for {user.username}.'})