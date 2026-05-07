# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo.tools import convert_file
from odoo.tests import tagged, TransactionCase
from odoo.tools.misc import file_path


IMPORT_MODELS_BY_BATCH = [
    'qbo.map.account',
    'qbo.map.tax',
    'qbo.map.taxcode',
    'qbo.map.partner',
    'qbo.map.product',
    'qbo.map.term',
    'qbo.map.payment.method',
]

request_client = 'odoo.addons.quickbooks_sync_online.quickbooks_api.AuthClient.refresh'


class IntuitCred:

    qbo_env = 'sandbox'

    company_id = 0000000000000000000
    client_id = 'client_id_kl3j4h5f234kl5jfh200Y'
    client_secret = 'client_secret_zlxjdfhbl34kuj5vh34'

    qb_access_token = 'access_token_kderW#$V%vSDFDFGDFGdfgGDRTH'
    qb_refresh_token = 'refresh_token_kjahc_SADfSDdghscnaseir34clkdfn'

    auth_url = 'https://appcenter.intuit.com/connect/oauth2?blablabla'
    sequrity_group = 'quickbooks_sync_online.qbo_security_group_manager'


@tagged('-at_install', 'post_install')
class QuickbooksInit(TransactionCase):

    def setUp(self):
        super(QuickbooksInit, self).setUp()

        self._load_xml('init_company.xml')

        self.company = self.env.ref('quickbooks_sync_online.test_odoo_company')

        self.qi = self.env['quickbooks.integration'].create({
            'name': 'Test QBO Odoo Company',
            'company_id': self.company.id,
            'state': 'active',
            'qb_client_id': IntuitCred.client_id,
            'qb_client_secret': IntuitCred.client_secret,
            'qb_company_id': IntuitCred.company_id,
            'qb_env': IntuitCred.qbo_env,
            'qb_is_us_company': True,
            'allow_out_invoice_export': True,
            'allow_in_invoice_export': True,
            'allow_out_refund_export': True,
            'allow_in_refund_export': True,
        })

        self.user = self.env['res.users'].with_context({
            'no_reset_password': True,
        }).create({
            'name': 'Test QBO Odoo User',
            'company_id': self.company.id,
            'company_ids': self.company.ids,
            'login': 'user',
            'email': 'user@intuit.com',
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref(IntuitCred.sequrity_group).id,
            ])],
        })

        env_ = self.env(
            context={
                'queue_job__no_delay': True,
                'allowed_company_ids': [self.company.id],
            },
        )
        self.env = env_

    def _load_xml(self, filename):
        pth = file_path(f'quickbooks_sync_online/tests/data/{filename}', ('xml',), self.env)
        convert_file(
            self.env,
            'quickbooks_sync_online',
            'tests/data/%s' % filename,
            {},
            'init',
            noupdate=False,
            pathname=pth,
        )

    def _set_up_connection(self):
        self.qi.write({
            'qb_access_token': IntuitCred.qb_access_token,
            'qb_refresh_token': IntuitCred.qb_refresh_token,
        })
