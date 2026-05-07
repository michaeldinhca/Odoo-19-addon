# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import fields, models, _
from odoo.exceptions import ValidationError

from ..quickbooks_api import Scopes
from ..tools import generate_token


class QuickbooksAuthWizard(models.TransientModel):
    _name = 'quickbooks.auth.wizard'
    _description = 'QuickBooks Authentication Wizard'

    qi_id = fields.Many2one(
        comodel_name='quickbooks.integration',
        required=True,
        ondelete='cascade',
    )

    client_id = fields.Char(
        related='qi_id.qb_client_id',
        readonly=False,
    )

    client_secret = fields.Char(
        related='qi_id.qb_client_secret',
        readonly=False,
    )

    environment = fields.Selection(
        related='qi_id.qb_env',
        readonly=False,
    )

    access_granted = fields.Boolean(
        related='qi_id.qb_access_granted',
    )

    state_token = fields.Char(
        string='State Token',
        default=lambda self: self._generate_state_token(),
    )

    request_in_progress = fields.Boolean(
        string='Request in Progress',
    )

    redirect_uri = fields.Char(
        string='Redirect URI',
        default=lambda self: self.qi_id.get_redirect_uri(),
        readonly=True,
    )

    def action_get_app_access(self):
        self.ensure_one()

        if not self.client_id or not self.client_secret:
            raise ValidationError(_('Please set Client ID and Client Secret first.'))

        self.request_in_progress = True
        token = self._update_state_token()

        # The access_tocken here is not defined yet, so we need to exclude it from the auth-client creation
        client = self.qi_id \
            ._get_qbo_auth_client(exclude_access_token=True)

        # The state_token is used to prevent CSRF attacks.
        # Also we join to him the wizard id to identify the wizard in the callback handler.
        client.state_token = token

        url = client.get_authorization_url([Scopes.ACCOUNTING])

        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_revoke_app_access(self):
        self.ensure_one()

        self.qi_id.revoke_qbo_access_settings()

        return self.action_open_form()

    def action_refresh_access_token(self):
        self.ensure_one()

        self.qi_id.refresh_qbo_access_token()

        return self.action_open_form()

    def _update_state_token(self):
        token = self._generate_state_token()
        self.state_token = token

        return token

    def _generate_state_token(self):
        return f'{generate_token()}.{self.id}'

    def action_open_form(self):
        self.ensure_one()

        action = self.env.ref('quickbooks_sync_online.action_view_quickbooks_integration_authentication').read()[0]
        action['res_id'] = self.id

        return action

    def action_close(self):
        return {
            'type': 'ir.actions.act_window_close',
        }
