from django.test import TestCase
from config.testkit import client_for, make_cashier, make_owner
from core.models import Setting
from core.services import IDLE_KEY


class SettingsTests(TestCase):
    def setUp(self):
        self.owner = make_owner()
        self.owner_api = client_for(self.owner)
        self.cashier_api = client_for(make_cashier())

    def minutes_for_cashier(self):
        return self.cashier_api.get('/api/settings/public/').data['idle_logout_minutes']

    def test_the_default_is_15(self):
        self.assertEqual(self.minutes_for_cashier(), 15)

    def test_the_owner_sets_it_and_everyone_sees_it(self):
        response = self.owner_api.patch('/api/settings/', {'idle_logout_minutes': 5}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.minutes_for_cashier(), 5)
        self.assertEqual(Setting.objects.get(key=IDLE_KEY).updated_by, self.owner)

    def test_bad_values_are_refused(self):
        for bad in (0, 241, -3, 'abc', '', 1.5):
            with self.subTest(value=bad):
                response = self.owner_api.patch('/api/settings/', {'idle_logout_minutes': bad}, format='json')
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.minutes_for_cashier(), 15)

    def test_a_cashier_cannot_read_or_change_the_owner_settings(self):
        self.assertEqual(self.cashier_api.get('/api/settings/').status_code, 403)
        response = self.cashier_api.patch('/api/settings/', {'idle_logout_minutes': 1}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.minutes_for_cashier(), 15)

    def test_no_login_no_settings(self):
        self.assertEqual(client_for().get('/api/settings/public/').status_code, 401)

    def test_garbage_in_the_table_falls_back_to_the_default(self):
        Setting.objects.create(key=IDLE_KEY, value='banana')
        self.assertEqual(self.minutes_for_cashier(), 15)

    def test_settings_cannot_be_deleted(self):
        self.owner_api.patch('/api/settings/', {'idle_logout_minutes': 5}, format='json')
        with self.assertRaises(PermissionError):
            Setting.objects.get().delete()

    def test_credit_defaults_and_changes(self):
        data = self.cashier_api.get('/api/settings/public/').data
        self.assertEqual(data['default_credit_limit'], '500.00')
        self.assertEqual(data['credit_limit_mode'], 'warn')
        response = self.owner_api.patch(
            '/api/settings/', {'default_credit_limit': '750.50', 'credit_limit_mode': 'block'}, format='json')
        self.assertEqual(response.status_code, 200)
        data = self.cashier_api.get('/api/settings/public/').data
        self.assertEqual(data['default_credit_limit'], '750.50')
        self.assertEqual(data['credit_limit_mode'], 'block')
        self.assertEqual(self.minutes_for_cashier(), 15)   

    def test_bad_credit_settings_are_refused(self):
        for body in ({'default_credit_limit': '-1'}, {'default_credit_limit': 'abc'},
                     {'default_credit_limit': '1.234'}, {'credit_limit_mode': 'maybe'}):
            with self.subTest(body=body):
                self.assertEqual(self.owner_api.patch('/api/settings/', body, format='json').status_code, 400)
        self.assertEqual(self.cashier_api.get('/api/settings/public/').data['default_credit_limit'], '500.00')

    def test_a_cashier_cannot_change_the_credit_settings(self):
        response = self.cashier_api.patch('/api/settings/', {'credit_limit_mode': 'warn'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_overdue_days(self):
        self.assertEqual(self.cashier_api.get('/api/settings/public/').data['overdue_days'], 30)
        self.assertEqual(self.owner_api.patch('/api/settings/', {'overdue_days': 45}, format='json').status_code, 200)
        self.assertEqual(self.cashier_api.get('/api/settings/public/').data['overdue_days'], 45)
        for bad in (0, 366, 'abc'):
            with self.subTest(value=bad):
                self.assertEqual(self.owner_api.patch('/api/settings/', {'overdue_days': bad}, format='json').status_code, 400)
        self.assertEqual(self.cashier_api.patch('/api/settings/', {'overdue_days': 1}, format='json').status_code, 403)
        
    def test_cashier_topup_permission_setting(self):
        self.assertFalse(self.cashier_api.get('/api/settings/public/').data['cashier_can_topup'])
        self.assertEqual(self.owner_api.patch('/api/settings/', {'cashier_can_topup': True}, format='json').status_code, 200)
        self.assertTrue(self.cashier_api.get('/api/settings/public/').data['cashier_can_topup'])
        self.assertEqual(self.cashier_api.patch('/api/settings/', {'cashier_can_topup': False}, format='json').status_code, 403)