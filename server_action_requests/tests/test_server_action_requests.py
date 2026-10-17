# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.server_action_requests.models import ir_actions_server


class FakeResponse:
    status_code = 200
    text = '{"userId": "42"}'

    def json(self):
        return {'userId': '42'}


@tagged('post_install', '-at_install')
class TestServerActionRequests(TransactionCase):

    def _make_action(self, code):
        return self.env['ir.actions.server'].create({
            'name': 'requests test',
            'model_id': self.env.ref('base.model_res_partner').id,
            'state': 'code',
            'code': code,
        })

    def test_post_available_and_response_usable(self):
        partner = self.env['res.partner'].create({'name': 'Req Test'})
        action = self._make_action(
            "resp = requests.post('https://example.invalid/hook', "
            "data=json.dumps({'id': record.id}), timeout=5)\n"
            "data = resp.json()\n"
            "if resp.status_code == 200 and data.get('userId'):\n"
            "    record.write({'ref': data['userId']})\n"
        )
        # wrap_module copied the function onto the wrapper, so patch it there
        with patch.object(ir_actions_server.safe_requests, 'post', return_value=FakeResponse()) as mocked:
            action.with_context(active_model='res.partner', active_id=partner.id).run()
        self.assertEqual(partner.ref, '42')
        mocked.assert_called_once()

    def test_exceptions_catchable(self):
        partner = self.env['res.partner'].create({'name': 'Req Test 2'})
        action = self._make_action(
            "try:\n"
            "    raise requests.exceptions.Timeout('slow')\n"
            "except requests.exceptions.RequestException as e:\n"
            "    record.write({'ref': 'caught'})\n"
        )
        action.with_context(active_model='res.partner', active_id=partner.id).run()
        self.assertEqual(partner.ref, 'caught')

    def test_internals_not_reachable(self):
        action = self._make_action("requests.Session()\n")
        with self.assertRaises(Exception):
            action.with_context(active_model='res.partner', active_id=self.env.user.partner_id.id).run()
