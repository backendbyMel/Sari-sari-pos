from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from accounts.permissions import IsOwner

from .exports import BUILDERS


class ExportView(APIView):
    permission_classes = [IsOwner]
    kind = None  

    def get(self, request):
        fmt = request.query_params.get('fmt', 'csv')
        if fmt not in ('csv', 'pdf'):
            raise ValidationError({'fmt': 'Use fmt=csv or fmt=pdf.'})
        return BUILDERS[self.kind](request.query_params, fmt)