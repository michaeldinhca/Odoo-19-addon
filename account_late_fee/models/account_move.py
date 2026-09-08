from odoo import api, fields, models, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    late_fee_model_id = fields.Many2one(
        'late.fee.model', string='Late Fee Model',
        domain="[('company_id', '=', company_id)]",
        help='Late Fee Model used for this invoice. If empty, the '
             "company's default model is used.")
    late_fee_exempt = fields.Boolean(
        string='Exempt from Late Fees',
        help='If checked, this invoice will never be charged a late fee, '
             'regardless of Late Fee Model configuration.')

    late_fee_ids = fields.One2many(
        'account.late.fee', 'move_id', string='Late Fees Charged',
        help='Late fees charged against installments of this invoice.')
    related_late_fee_ids = fields.One2many(
        'account.late.fee', 'fee_move_id', string='Late Fees Applied Here',
        help='Late fees whose charge landed on this invoice (either as an '
             'added line, or as a dedicated late fee invoice).')
    late_fee_status = fields.Selection(
        [('none', 'No Fee'), ('pending', 'Pending Review'),
         ('applied', 'Fee Applied')],
        compute='_compute_late_fee_status', store=True, readonly=True)
    late_fee_last_applied_date = fields.Date(
        compute='_compute_late_fee_status', store=True, readonly=True)
    late_fee_count = fields.Integer(compute='_compute_late_fee_count')

    @api.depends('late_fee_ids')
    def _compute_late_fee_count(self):
        for move in self:
            move.late_fee_count = len(move.late_fee_ids)

    @api.depends('late_fee_ids.state', 'late_fee_ids.confirmed_date')
    def _compute_late_fee_status(self):
        for move in self:
            fees = move.late_fee_ids
            if fees.filtered(lambda f: f.state == 'draft'):
                move.late_fee_status = 'pending'
            elif fees.filtered(lambda f: f.state == 'confirmed'):
                move.late_fee_status = 'applied'
            else:
                move.late_fee_status = 'none'
            confirmed = fees.filtered(lambda f: f.state == 'confirmed' and f.confirmed_date)
            move.late_fee_last_applied_date = (
                max(confirmed.mapped('confirmed_date')).date()
                if confirmed else False)

    def action_view_late_fees(self):
        self.ensure_one()
        return {
            'name': _('Late Fees'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.late.fee',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.late_fee_ids.ids)],
        }
