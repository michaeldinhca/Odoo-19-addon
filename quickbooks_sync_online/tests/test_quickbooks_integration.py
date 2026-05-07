# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from unittest.mock import patch

from odoo.tests import tagged
from odoo.exceptions import ValidationError

from .config.intuit_case import IntuitCred, QuickbooksInit, request_client
from ..quickbooks_api import QuickBooksClient, AuthClient


@tagged('-at_install', '-standard', 'post_install', 'qbo_test_connection')
class TestQuickbooksIntegration(QuickbooksInit):

    def setUp(self):
        super(TestQuickbooksIntegration, self).setUp()

    def test_qi_get_qbo_env(self):
        env = self.qi.get_qbo_env()
        self.assertEqual(env, 'sandbox')

    def test_qi_redirect_uri(self):
        su = self.env['ir.config_parameter'].sudo()
        redirect_uri_ = su.get_param('web.base.url') + '/qbo/callback'
        self.assertEqual(self.qi.get_redirect_uri(), redirect_uri_)

    def test_qi_cron_nex_call(self):
        self.qi._compute_automation_points()
        cron = self.env.ref(
            'quickbooks_sync_online.trigget_send_invoices_to_qb_cron',
            raise_if_not_found=False,
        )
        if cron:
            self.assertEqual(self.qi.auto_export_next_call_point, cron.nextcall)

    def test_qi_auth_client(self):
        client = self.qi._get_qbo_auth_client()
        self.assertIsInstance(client, AuthClient)

    @patch(request_client)
    def test_qi_get_qbo_client(self, *args):
        with self.assertRaises(ValidationError):
            self.qi.get_quickbooks_api_client()

        self.qi.write({
            'qb_refresh_token': IntuitCred.qb_refresh_token,
        })
        qbo_object = self.qi.get_quickbooks_api_client()
        self.assertIsInstance(qbo_object, QuickBooksClient)

    def test_qi_intuit_company_info(self):
        self._set_up_connection()
        self.assertTrue(self.qi.qb_is_us_company)
