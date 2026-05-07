# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import re

from werkzeug.exceptions import BadRequest

from odoo import http
from odoo.exceptions import ValidationError


def get_number_after_dot(s):
    match = re.search(r'\.(\d+)$', s)
    if match:
        return int(match.group(1))
    return None


class QboCallbackController(http.Controller):

    @http.route('/qbo/callback', type='http', auth='user')
    def qbo_callback(self, state, code, realmId, *args, **kw):
        """QuickBooks callback response handler."""

        wizard_id = get_number_after_dot(state)

        if not wizard_id:
            return BadRequest('Bad csrf! Rejected!')

        wizard = http.request.env['quickbooks.auth.wizard'].sudo().browse(wizard_id).exists()
        if not wizard:
            return BadRequest(f'Quickbooks Auth Wizard (id={wizard_id}) not found! Rejected!')

        if state != wizard.state_token:
            return BadRequest('Quickbooks Auth Wizard invalid csrf! Rejected!')

        qi = wizard.qi_id.exists()
        if not qi:
            return BadRequest(f'Quickbooks Connection not found! Rejected!')

        # The access_tocken here is not defined yet, so we need to exclude it from the auth-client creation
        client = qi._get_qbo_auth_client(exclude_access_token=True)
        client.get_bearer_token(code, realm_id=realmId)

        qi._update_from_quth_client(client, qb_company_id=realmId)

        try:
            qbo_company = qi._validate_intuit_company_info()
        except ValidationError as e:
            qi._update_from_quth_client(client, qb_company_id=False)
            return BadRequest(e.args[0])

        qi._update_from_qbo_company_info(qbo_company)
        qi.action_active()

        # Redirect back to authentication form (for both success and error cases)
        return http.request.redirect(f'/odoo/qi-connection/{qi.id}')
