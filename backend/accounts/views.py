from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView

from .permissions import IsCashierOrOwner, IsOwner
from .serializers import LoginSerializer


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