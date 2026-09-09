from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    provincial_tax_id_source = fields.Selection(
        [('delivery', 'Delivery/Shipping Address'),
         ('invoice', 'Invoice/Billing Address')],
        string="Provincial Tax ID Source",
        default='delivery',
        help="Address used to resolve a fiscal position for the Provincial "
             "Tax ID on documents that do not carry their own fiscal "
             "position (e.g. Delivery Slips). Documents with their own "
             "fiscal position (Sales Orders, Invoices, ...) always use it "
             "directly, regardless of this setting.")
