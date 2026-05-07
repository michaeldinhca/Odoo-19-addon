# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

from odoo import api, models, fields, _
from odoo.tools import ormcache
from odoo.exceptions import ValidationError, UserError

from ...tools import QboCompanyInfo
from ...quickbooks_api import (
    AuthClient,
    AuthClientError,
    QuickBooksClient,
    QboClassManager,
    QBO_API_VERSION,
)


_logger = logging.getLogger(__name__)


class QuickbooksIntegrationAuthMixin(models.AbstractModel):
    _name = 'quickbooks.integration.auth.mixin'
    _description = 'Quickbooks Integration Auth Mixin'

    qb_client_id = fields.Char(
        string='Client ID',
    )

    qb_client_secret = fields.Char(
        string='Client Secret',
    )

    qb_env = fields.Selection(
        selection=[
            ('production', 'Production'),
            ('sandbox', 'Development'),
        ],
        string='Environment',
        default='production',
    )

    qb_access_token = fields.Text(
        string='Access Token',
    )

    qb_refresh_token = fields.Char(
        string='Refresh Token',
    )

    qb_company_id = fields.Char(
        string='Company Id',
    )

    qb_company_info = fields.Char(
        string='QuickBooks Company Info',
    )

    qb_is_us_company = fields.Boolean(
        string='QuickBooks Is US Company',
    )

    qb_access_granted = fields.Boolean(
        string='Access Granted',
        compute='_compute_qbo_access_granted',
    )

    def _compute_qbo_access_granted(self):
        for rec in self:
            rec.qb_access_granted = bool(
                rec.qb_company_id
                and rec.qb_client_id
                and rec.qb_client_secret
                and rec.qb_access_token
                and rec.qb_refresh_token
            )

    def get_redirect_uri(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url').rstrip('/')
        return f'{base_url}/qbo/callback'

    def get_qbo_env(self):
        """Using QuickBooks company for production or developing."""
        if not self.qb_env:
            self.qb_env = 'production'
        return self.qb_env

    def ensure_qbo_us_company(self):
        self.ensure_one()
        if not self.qb_is_us_company:
            raise UserError(_('%s: The feature is allowed only for the US companies.') % self.display_name)

    @ormcache(
        'self',
        'self.qb_refresh_token',
        'self.qb_access_token',
    )
    def get_quickbooks_api_client(self):
        self.ensure_one()

        if not self.qb_company_id or not self.qb_refresh_token:
            raise ValidationError(_(
                '%s: "QuickBooks refresh token" or "QuickBooks company ID" are not defined.'
            ) % self.name)

        qb = QuickBooksClient(
            auth_client=self._get_qbo_auth_client(),
            company_id=self.qb_company_id,
            refresh_token=self.qb_refresh_token,
            minorversion=QBO_API_VERSION,
        )

        qb.quickbooks_integration_id = self.id

        return qb

    def _get_qbo_auth_client(self, exclude_access_token=False):
        self.ensure_one()

        params = {
            'client_id': self.qb_client_id,
            'client_secret': self.qb_client_secret,
            'redirect_uri': self.get_redirect_uri(),
            'access_token': self.qb_access_token,
            'environment': self.get_qbo_env(),
        }

        if exclude_access_token:
            params.pop('access_token')

        return AuthClient(**params)

    def revoke_qbo_access_settings(self):
        if self.qb_access_granted:
            try:
                client = self._get_qbo_auth_client()
                client.revoke(token=self.qb_refresh_token)
            except AuthClientError as ex:
                _logger.error(ex.args)

        result = self.write({
            'qb_env': 'production',
            'qb_client_id': False,
            'qb_client_secret': False,
            'qb_company_id': False,
            'qb_access_token': False,
            'qb_refresh_token': False,
        })

        self._compute_qbo_access_granted()

        _logger.info('QuickBooks access has been revoked.')
        return result

    @api.model
    def refresh_qbo_access_token(self):
        for record in self.search([]).filtered(lambda r: r.qb_access_granted):
            try:
                record._refresh_qbo_access_token()
            except Exception as ex:
                _logger.error('%s: QuickBooks Access Token refresh failed --> %s', record.display_name, ex.args[0])

    def _refresh_qbo_access_token(self):
        _logger.info('Refresh QuickBooks access token')

        client = self._get_qbo_auth_client()
        client.refresh(refresh_token=self.qb_refresh_token)

        self._update_from_quth_client(client)

        _logger.info('%s: QuickBooks Access Token has been successfully updated', self.name)
        return True

    def _validate_intuit_company_info(self) -> QboCompanyInfo:
        self.ensure_one()

        qbo_company = self._fetch_qbo_company_info()

        if not qbo_company.validate_country(self.company_id.country_id.code):
            raise ValidationError(_(
                '%s: Different countries for Odoo company and QuickBooks company are not allowed!'
            ) % self.name)

        if not qbo_company.validate_home_currency(self.currency_id.name):
            raise ValidationError(_(
                '%s: Different currencies for Odoo company and QuickBooks company are not allowed!'
            ) % self.name)

        return qbo_company

    def _update_from_quth_client(self, client: AuthClient, **kw):
        self.write({
            **kw,
            'qb_access_token': client.access_token,
            'qb_refresh_token': client.refresh_token,
        })
        self._compute_qbo_access_granted()

    def _update_from_qbo_company_info(self, qbo_company: QboCompanyInfo, **kw):
        self.write({
            **kw,
            'qb_company_info': qbo_company.address_format(),
            'qb_is_us_company': qbo_company.is_us_company,
        })

    def _fetch_qbo_company_info(self):
        try:
            client = self.get_quickbooks_api_client()

            Preferences = QboClassManager.get_class('Preferences')
            preferences = Preferences.get(qb=client)

            CompanyCurrency = QboClassManager.get_class('CompanyCurrency')
            currency_list = CompanyCurrency.all(qb=client)

            CompanyInfo = QboClassManager.get_class('CompanyInfo')
            company_info = CompanyInfo.get(self.qb_company_id, qb=client)
        except Exception as ex:
            raise ValidationError('%s: %s' % (self.name, ex.args[0]))

        return QboCompanyInfo(preferences, company_info, currency_list)

    def check_quickbooks_connection(self):
        is_ok = True

        try:
            qb_company_info = self._fetch_qbo_company_info()
            self._update_from_qbo_company_info(qb_company_info)
        except Exception as ex:
            is_ok = False
            _logger.error('%s: QuickBooks Connection check failed --> %s', self.name, ex.args[0])

        ttype = 'success' if is_ok else 'warning'
        message = 'successful' if is_ok else 'failed'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'{self.name}: Connection to QuickBooks is {message}!',
                'type': ttype,
                'sticky': False,
            }
        }

    def action_open_auth_wizard(self):
        self.ensure_one()
        action = self.env.ref('quickbooks_sync_online.action_view_quickbooks_integration_authentication').read()[0]

        action['context'] = {
            'default_qi_id': self.id,
        }

        return action

    def print_quickbooks_settings(self):
        self.ensure_one()
        qbo_company = self._fetch_qbo_company_info()

        data = {
            'COMPANY': qbo_company.get_qbo_company_info(),
            'COMPANY CURRENCIES': qbo_company.get_qbo_external_currencies(),
            'COMPANY PREFERENCE': qbo_company.get_qbo_preference(),
        }

        return self.env['quickbooks.help.wizard'] \
            .create_and_run_as_json(_('QUICKBOOKS COMPANY SETTINGS'), data)
