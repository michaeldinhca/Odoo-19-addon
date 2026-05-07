# Copyright 2020 VentorTech OU
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import api, models


class QueueJob(models.Model):
    _inherit = 'queue.job'

    @api.model
    def cancel_failed_jobs_by_identity_key(self, identity_key: str):
        self.search([
            ('state', '=', 'failed'),
            ('identity_key', '=', identity_key),
        ]).button_cancelled()
