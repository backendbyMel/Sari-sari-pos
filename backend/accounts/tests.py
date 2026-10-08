from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from config.testkit import client_for, make_cashier, make_owner

# Create your tests here.
OWNER_ONLY = [
    ('get', '/api/auth/owner-check/'),
    ('get', '/api/products/'),
    ('post', '/api/products/'),
    ('get', '/api/categories/'),
    ('get', '/api/units/'),
    ('get', '/api/price-tiers/'),
    ('get', '/api/restocks/'),
    ('post', '/api/restocks/'),
    ('post', '/api/stock-adjustments/'),
    ('get', '/api/stock-movements/'),
    ('get', '/api/users/'),
    ('post', '/api/users/'),
    ('get', '/api/shifts/'),
    ('post', '/api/shifts/1/close/'),
    ('post', '/api/shifts/1/reopen/'),
]
LOGIN_REQUIRED = OWNER_ONLY + [
    ('get', '/api/auth/me/'),
    ('get', '/api/products/lookup/?code=x'),
    ('post', '/api/sales/'),
    ('get', '/api/sales/recent/'),
    ('get', '/api/receipts/SR-000001/'),
    ('post', '/api/receipts/SR-000001/reprint/'),
    ('get', '/api/shifts/current/'),
    ('post', '/api/shifts/start/'),
    ('post', '/api/shifts/end/'),
]


def call(client, method, url):
    if method == 'get':
        return client.get(url)
    return client.post(url, {}, format='json')


class PermissionTests(TestCase):
    def test_nobody_logged_in_gets_401_everywhere(self):
        anonymous = client_for()
        for method, url in LOGIN_REQUIRED:
            with self.subTest(method=method, url=url):
                self.assertEqual(call(anonymous, method, url).status_code, 401)

    def test_cashier_gets_403_on_every_owner_endpoint(self):
        cashier = client_for(make_cashier())
        for method, url in OWNER_ONLY:
            with self.subTest(method=method, url=url):
                self.assertEqual(call(cashier, method, url).status_code, 403)

    def test_cashier_can_use_cashier_endpoints(self):
        cashier = client_for(make_cashier())
        self.assertEqual(cashier.get('/api/auth/me/').status_code, 200)
        self.assertEqual(cashier.get('/api/sales/recent/').status_code, 200)
        # 404 means "allowed in, but no such item" (not 403).
        self.assertEqual(cashier.get('/api/products/lookup/?code=x').status_code, 404)

    def test_owner_is_allowed_in(self):
        owner = client_for(make_owner())
        self.assertEqual(owner.get('/api/products/').status_code, 200)
        self.assertEqual(owner.get('/api/users/').status_code, 200)


class UserManagementTests(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.api = client_for(self.owner)

    def test_role_cannot_be_chosen_through_the_api(self):
        response = self.api.post(
            '/api/users/',
            {'username': 'newbie', 'password': 'Tindahan#2026', 'role': 'OWNER'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.get(username='newbie').role, 'CASHIER')

    def test_weak_password_refused(self):
        response = self.api.post(
            '/api/users/', {'username': 'weak', 'password': '12345678'}, format='json'
        )
        self.assertEqual(response.status_code, 400)

    def test_owner_accounts_are_not_listed_or_changeable(self):
        make_cashier()
        usernames = [u['username'] for u in self.api.get('/api/users/').data]
        self.assertIn('cash', usernames)
        self.assertNotIn('boss', usernames)
        response = self.api.patch(f'/api/users/{self.owner.id}/', {'is_active': False}, format='json')
        self.assertEqual(response.status_code, 404)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)

    def test_accounts_cannot_be_deleted(self):
        cashier = make_cashier()
        self.assertEqual(self.api.delete(f'/api/users/{cashier.id}/').status_code, 405)

    def test_no_secrets_in_the_user_list(self):
        cashier = make_cashier()
        cashier.set_pin('4821')
        cashier.save()
        text = self.api.get('/api/users/').content.decode().lower()
        for secret in ('password', 'hash', '4821'):
            self.assertNotIn(secret, text)


class LoginTests(TestCase):
    def setUp(self):
        cache.clear()   

    def tearDown(self):
        cache.clear()

    def login(self, username, password):
        return APIClient().post(
            '/api/auth/login/', {'username': username, 'password': password}, format='json'
        )

    def test_login_returns_tokens_and_role(self):
        make_cashier()
        response = self.login('cash', 'Cashier#Pass123')
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['role'], 'CASHIER')

    def test_wrong_password_refused(self):
        make_cashier()
        self.assertEqual(self.login('cash', 'wrong').status_code, 401)

    def test_disabled_account_cannot_log_in(self):
        cashier = make_cashier()
        cashier.is_active = False
        cashier.save()
        self.assertEqual(self.login('cash', 'Cashier#Pass123').status_code, 401)

    def test_token_stops_working_the_moment_the_account_is_disabled(self):
        cashier = make_cashier()
        token = self.login('cash', 'Cashier#Pass123').data['access']
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(client.get('/api/auth/me/').status_code, 200)
        cashier.is_active = False
        cashier.save()
        self.assertEqual(client.get('/api/auth/me/').status_code, 401)

    def test_login_is_rate_limited(self):
        make_cashier()
        for _ in range(10):
            self.assertEqual(self.login('cash', 'wrong').status_code, 401)
        self.assertEqual(self.login('cash', 'wrong').status_code, 429)


class PinTests(TestCase):
    def test_pin_is_stored_as_a_hash(self):
        user = make_cashier()
        user.set_pin('4821')
        self.assertNotIn('4821', user.pin_hash)
        self.assertTrue(user.check_pin('4821'))
        self.assertFalse(user.check_pin('1111'))

    def test_bad_pins_refused(self):
        user = make_cashier()
        for bad in ('12', 'abcd', '1234567'):
            with self.subTest(pin=bad):
                with self.assertRaises(ValueError):
                    user.set_pin(bad)