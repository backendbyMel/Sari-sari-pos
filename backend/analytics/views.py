from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.permissions import IsOwner
from .services import dashboard

# Create your views here.
class DashboardView(APIView):
    permission_classes = [IsOwner]

    def get(self, request):
        return Response(dashboard())