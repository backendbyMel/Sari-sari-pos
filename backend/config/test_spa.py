import tempfile
from pathlib import Path

from django.test import TestCase, override_settings


class SpaTests(TestCase):
    def test_app_addresses_get_the_page_and_api_misses_stay_404(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'index.html').write_text('<html>the app</html>')
            with override_settings(FRONTEND_DIST=Path(folder)):
                for url in ('/', '/owner/products', '/login'):
                    with self.subTest(url=url):
                        response = self.client.get(url)
                        self.assertEqual(response.status_code, 200)
                        self.assertIn(b'the app', b''.join(response.streaming_content))
                self.assertEqual(self.client.get('/api/does-not-exist/').status_code, 404)
                self.assertEqual(self.client.get('/assets/missing.js').status_code, 404)
                self.assertEqual(self.client.post('/owner/products').status_code, 405)

    def test_a_missing_build_is_a_clear_404(self):
        with tempfile.TemporaryDirectory() as folder:
            with override_settings(FRONTEND_DIST=Path(folder)):
                self.assertEqual(self.client.get('/').status_code, 404)