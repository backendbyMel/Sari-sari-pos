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
    ('get', '/api/shifts/1/payouts/'),
    ('post', '/api/shifts/1/report/generate/'),
    ('get', '/api/settings/'),
    ('post', '/api/users/1/unlock-pin/'),
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
    ('post', '/api/shifts/payouts/'),
    ('get', '/api/shifts/summary/'),
    ('get', '/api/shifts/mine/'),
    ('get', '/api/shifts/1/report/'),
    ('get', '/api/settings/public/'),
    ('get', '/api/customers/'),
    ('post', '/api/customers/'),
    ('get', '/api/customers/1/'),
    ('post', '/api/utang/payments/'),
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

class PinLoginTests(TestCase):
    URL = '/api/auth/pin-login/'

    def setUp(self):
        cache.clear()   # the PIN rate limit is remembered in the cache
        self.cashier = make_cashier()
        self.cashier.set_pin('4821')
        self.cashier.save()
        self.owner = make_owner()
        self.owner_api = client_for(self.owner)

    def tearDown(self):
        cache.clear()

    def pin_login(self, username, pin):
        return APIClient().post(self.URL, {'username': username, 'pin': pin}, format='json')

    def test_the_right_pin_logs_in_and_the_token_works(self):
        response = self.pin_login('cash', '4821')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['user']['role'], 'CASHIER')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        self.assertEqual(client.get('/api/auth/me/').data['username'], 'cash')
        self.assertEqual(client.get('/api/auth/owner-check/').status_code, 403)

    def test_every_failure_gives_the_same_answer(self):
        make_cashier('nopin')                                   # a cashier with no PIN
        disabled = make_cashier('gone')
        disabled.set_pin('1111')
        disabled.is_active = False
        disabled.save()
        answers = [
            self.pin_login('cash', '0000'),      # wrong PIN
            self.pin_login('nobody', '4821'),    # unknown user
            self.pin_login('nopin', '4821'),     # no PIN set
            self.pin_login('gone', '1111'),      # disabled
        ]
        for response in answers:
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.data, answers[0].data)

    def test_five_wrong_tries_lock_the_pin_but_not_the_password(self):
        for _ in range(5):
            self.assertEqual(self.pin_login('cash', '0000').status_code, 401)
        self.cashier.refresh_from_db()
        self.assertTrue(self.cashier.pin_locked)
        self.assertEqual(self.pin_login('cash', '4821').status_code, 401)   # even the right PIN
        password = APIClient().post(
            '/api/auth/login/', {'username': 'cash', 'password': 'Cashier#Pass123'}, format='json')
        self.assertEqual(password.status_code, 200)

    def test_a_correct_pin_resets_the_counter(self):
        for _ in range(3):
            self.pin_login('cash', '0000')
        self.assertEqual(self.pin_login('cash', '4821').status_code, 200)
        for _ in range(4):
            self.pin_login('cash', '0000')
        self.cashier.refresh_from_db()
        self.assertFalse(self.cashier.pin_locked)
        self.assertEqual(self.cashier.pin_failed_attempts, 4)

    def test_the_owner_can_unlock_and_a_cashier_cannot(self):
        for _ in range(5):
            self.pin_login('cash', '0000')
        url = f'/api/users/{self.cashier.id}/unlock-pin/'
        self.assertEqual(client_for(self.cashier).post(url).status_code, 403)
        self.assertEqual(self.owner_api.post(url).status_code, 200)
        self.assertEqual(self.pin_login('cash', '4821').status_code, 200)

    def test_a_new_pin_also_unlocks(self):
        for _ in range(5):
            self.pin_login('cash', '0000')
        self.owner_api.post(f'/api/users/{self.cashier.id}/set-pin/', {'pin': '9753'}, format='json')
        self.assertEqual(self.pin_login('cash', '9753').status_code, 200)

    def test_the_user_list_shows_the_lock(self):
        for _ in range(5):
            self.pin_login('cash', '0000')
        row = [u for u in self.owner_api.get('/api/users/').data if u['username'] == 'cash'][0]
        self.assertTrue(row['pin_locked'])
        self.assertNotIn('pin_failed_attempts', row)

    def test_the_owner_cannot_use_a_pin(self):
        self.owner.set_pin('4821')
        self.owner.save()
        self.assertEqual(self.pin_login('boss', '4821').status_code, 401)

    def test_badly_formed_requests(self):
        for body in ({'username': 'cash', 'pin': '12'}, {'username': 'cash', 'pin': 'abcd'},
                     {'username': 'cash'}, {'pin': '4821'}):
            with self.subTest(body=body):
                self.assertEqual(APIClient().post(self.URL, body, format='json').status_code, 400)

    def test_pin_login_is_rate_limited(self):
        for _ in range(10):
            self.assertEqual(self.pin_login('nobody', '0000').status_code, 401)
        self.assertEqual(self.pin_login('nobody', '0000').status_code, 429)