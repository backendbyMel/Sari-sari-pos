from django.conf import settings
from django.http import FileResponse, Http404
from django.views.decorators.http import require_safe


@require_safe
def serve_spa(request, path=''):
    index = settings.FRONTEND_DIST / 'index.html'
    if not index.is_file():
        raise Http404('The app has not been built. Run "npm run build" in the frontend folder.')
    response = FileResponse(index.open('rb'), content_type='text/html; charset=utf-8')
    response['Cache-Control'] = 'no-cache'      
    return response