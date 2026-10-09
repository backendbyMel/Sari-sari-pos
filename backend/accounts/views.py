from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView

from .permissions import IsCashierOrOwner, IsOwner
from .serializers import (
    CashierCreateSerializer, LoginSerializer, PasswordResetSerializer,
    PinLoginSerializer, PinSetSerializer, UserSerializer,
)
from rest_framework import status, viewsets
from .models import User
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from .services import attempt_pin_login

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
        user.pin_failed_attempts = 0
        user.pin_locked = False        
        user.save(update_fields=['pin_hash', 'pin_failed_attempts', 'pin_locked'])
        return Response({'detail': f'PIN set for {user.username}.'})

    @action(detail=True, methods=['post'], url_path='unlock-pin')
    def unlock_pin(self, request, pk=None):
        user = self.get_object()
        user.pin_failed_attempts = 0
        user.pin_locked = False
        user.save(update_fields=['pin_failed_attempts', 'pin_locked'])
        return Response({'detail': f'PIN unlocked for {user.username}.'})

class PinLoginRateThrottle(AnonRateThrottle):
    scope = 'pin_login'


PIN_FAILED = (
    'Wrong username or PIN. After 5 wrong tries a PIN is locked: '
    'use your password, or ask the owner to unlock it.'
)


class PinLoginView(APIView):
    authentication_classes = []        
    permission_classes = [AllowAny]    
    throttle_classes = [PinLoginRateThrottle]

    def post(self, request):
        form = PinLoginSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        user = attempt_pin_login(form.validated_data['username'], form.validated_data['pin'])
        if user is None:
            return Response({'detail': PIN_FAILED}, status=status.HTTP_401_UNAUTHORIZED)

        refresh = RefreshToken.for_user(user)
        refresh['username'] = user.username
        refresh['role'] = user.role
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': {'id': user.id, 'username': user.username, 'role': user.role},
        })