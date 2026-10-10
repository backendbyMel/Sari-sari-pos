import re

from django.test import TestCase
from django.urls import get_resolver

from config.testkit import client_for, make_cashier, make_owner
PUBLIC = {'api/auth/login/', 'api/auth/refresh/', 'api/auth/pin-login/'}
CASHIER_OK = {
    'api/auth/me/',
    'api/products/lookup/',
    'api/sales/', 'api/sales/recent/', 'api/receipts/1/', 'api/receipts/1/reprint/',
    'api/customers/', 'api/customers/1/', 'api/utang/payments/',
    'api/shifts/start/', 'api/shifts/current/', 'api/shifts/end/', 'api/shifts/payouts/',
    'api/shifts/summary/', 'api/shifts/mine/', 'api/shifts/wallets-to-check/',
    'api/shifts/1/report/',
    'api/load/products/', 'api/load/send/', 'api/load/mine/', 'api/load/1/fail/',
    'api/ewallet/quote/', 'api/ewallet/cash-in/', 'api/ewallet/cash-out/', 'api/ewallet/mine/',
    'api/wallets/topup/',
    'api/settings/public/',
}


def normalize(raw):
    raw = re.sub(r'\(\?P<\w+>[^)]*\)', '1', raw)    # router patterns
    raw = re.sub(r'<[^>]+>', '1', raw)              # path() converters
    return raw.replace('^', '').replace('$', '').replace('\\', '')


def all_paths():
    found = set()

    def walk(patterns, prefix):
        for pattern in patterns:
            if hasattr(pattern, 'url_patterns'):     
                walk(pattern.url_patterns, prefix + str(pattern.pattern))
            else:
                found.add(normalize(prefix + str(pattern.pattern)))

    walk(get_resolver().url_patterns, '')
    return sorted(p for p in found if not p.startswith('admin/'))


def status_of(client, method, path):
    response = getattr(client, method)('/' + path)
    if getattr(response, 'streaming', False):
        b''.join(response.streaming_content)         
    return response.status_code


class RouteSecurityTests(TestCase):
    def test_the_walker_really_found_the_routes(self):
        paths = all_paths()
        self.assertGreater(len(paths), 50)
        for path in PUBLIC | CASHIER_OK:             # catches a stale or misspelled list entry
            self.assertIn(path, paths)

    def test_nobody_logged_in_is_refused_everywhere_except_the_login_doors(self):
        anonymous = client_for()
        for path in all_paths():
            if path in PUBLIC:
                continue
            for method in ('get', 'post'):
                with self.subTest(path=path, method=method):
                    self.assertEqual(status_of(anonymous, method, path), 401)

    def test_a_cashier_is_refused_everywhere_not_on_the_allowed_list(self):
        cashier = client_for(make_cashier())
        for path in all_paths():
            if path in PUBLIC or path in CASHIER_OK:
                continue
            for method in ('get', 'post'):
                with self.subTest(path=path, method=method):
                    self.assertEqual(status_of(cashier, method, path), 403)

    def test_the_owner_is_never_locked_out_of_a_route(self):
        owner = client_for(make_owner())
        for path in all_paths():
            if path in PUBLIC:
                continue
            for method in ('get', 'post'):
                with self.subTest(path=path, method=method):
                    self.assertNotIn(status_of(owner, method, path), (401, 403))