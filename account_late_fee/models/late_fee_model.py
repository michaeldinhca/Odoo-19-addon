from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class LateFeeModel(models.Model):
    _name = 'late.fee.model'
    _description = 'Late Fee Model'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        related='company_id.currency_id', store=True, readonly=True)

    is_company_default = fields.Boolean(
        string='Default for Company',
        help='The default Late Fee Model used for invoices/partners that '
             "don't specify one explicitly. Only one model can be the "
             'default per company.')

    computation_type = fields.Selection(
        [('percentage', 'Percentage of Overdue Amount'),
         ('fixed', 'Fixed Amount')],
        required=True, default='percentage')
    percentage = fields.Float(
        string='Percentage (%)', digits=(5, 2),
        help='Percentage of the overdue installment amount charged per '
             'period.')
    fixed_amount = fields.Monetary(
        string='Fixed Amount', currency_field='currency_id',
        help='Flat amount charged per period.')

    interval_type = fields.Selection(
        [('day', 'Day(s)'), ('week', 'Week(s)'), ('month', 'Month(s)')],
        required=True, default='month',
        help='Unit of the recurrence period used both for the grace '
             'period and, when recurring, for how often the fee '
             're-applies.')
    interval_number = fields.Integer(
        string='Every', default=1,
        help='Number of Interval Type units per period, e.g. Interval '
             'Type=Month, Every=1 means "every month".')
    grace_period_days = fields.Integer(
        string='Grace Period (Days)', default=0,
        help='Number of days after the installment due date before any '
             'fee becomes eligible.')

    recurrence = fields.Selection(
        [('once', 'One-Time'), ('recurring', 'Recurring')],
        required=True, default='once',
        help='One-Time: the fee is charged once per overdue installment. '
             'Recurring: the fee re-applies every period the installment '
             'remains unpaid, up to Max Occurrences.')
    max_occurrences = fields.Integer(
        string='Max Occurrences', default=0,
        help='Maximum number of times the fee can recur per installment. '
             '0 means unlimited.')

    late_fee_product_id = fields.Many2one(
        'product.product', string='Late Fee Product', required=True,
        domain=[('type', '=', 'service')],
        help='Product used for the late fee line. Its income account and '
             'taxes determine how the fee is booked.')
    late_fee_journal_id = fields.Many2one(
        'account.journal', string='Late Fee Journal',
        domain=[('type', '=', 'sale')],
        help='Journal used when creating a new late fee invoice. If '
             "empty, the original invoice's journal is used.")
    send_notification_email = fields.Boolean(
        string='Send Notification Email', default=True,
        help='If checked, the customer is emailed (CC company/salesperson) '
             'both when a fee is confirmed (a running summary, before any '
             'invoice exists) and when it is included on a consolidated '
             'invoice. If unchecked, fees still proceed normally but no '
             'email is ever sent for them.')
    mail_template_id = fields.Many2one(
        'mail.template', string='Summary Email Template',
        domain=[('model', '=', 'account.late.fee')],
        help='Sent when a fee is Confirmed: a running summary of every '
             'outstanding confirmed-but-not-yet-invoiced fee for that '
             'customer, before any invoice exists. Overrides the module '
             'default if set.')
    invoice_mail_template_id = fields.Many2one(
        'mail.template', string='Invoice Email Template',
        domain=[('model', '=', 'account.late.fee')],
        help='Sent when fees are included on a consolidated invoice. '
             'Overrides the module default if set.')
    additional_note = fields.Text(
        string='Additional Note',
        help='Optional extra text appended after the automatically '
             'generated fee explanation.')

    _percentage_positive = models.Constraint(
        'CHECK(percentage >= 0)',
        'The percentage must not be negative.',
    )
    _fixed_amount_positive = models.Constraint(
        'CHECK(fixed_amount >= 0)',
        'The fixed amount must not be negative.',
    )
    _max_occurrences_positive = models.Constraint(
        'CHECK(max_occurrences >= 0)',
        'Max Occurrences must not be negative.',
    )
    _interval_number_positive = models.Constraint(
        'CHECK(interval_number > 0)',
        'Every must be strictly positive.',
    )

    @api.constrains('computation_type', 'percentage', 'fixed_amount')
    def _check_amount(self):
        for model in self:
            if model.computation_type == 'percentage' and model.percentage <= 0:
                raise ValidationError(_(
                    'Set a percentage greater than 0 for "%s".', model.name))
            if model.computation_type == 'fixed' and model.fixed_amount <= 0:
                raise ValidationError(_(
                    'Set a fixed amount greater than 0 for "%s".', model.name))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered('is_company_default')._enforce_single_default()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get('is_company_default'):
            self._enforce_single_default()
        return res

    def _enforce_single_default(self):
        for record in self:
            if not record.is_company_default:
                continue
            self.search([
                ('company_id', '=', record.company_id.id),
                ('id', '!=', record.id),
                ('is_company_default', '=', True),
            ]).write({'is_company_default': False})

    def action_set_default(self):
        self.ensure_one()
        self.is_company_default = True

    def action_edit_summary_mail_template(self):
        self.ensure_one()
        return self._open_mail_template(
            self.mail_template_id, 'account_late_fee.mail_template_late_fee_summary')

    def action_edit_invoice_mail_template(self):
        self.ensure_one()
        return self._open_mail_template(
            self.invoice_mail_template_id, 'account_late_fee.mail_template_late_fee_notice')

    def _open_mail_template(self, override, default_xmlid):
        template = override or self.env.ref(default_xmlid, raise_if_not_found=False)
        if not template:
            raise UserError(_('No email template available to edit.'))
        return {
            'name': _('Edit Email Template'),
            'type': 'ir.actions.act_window',
            'res_model': 'mail.template',
            'res_id': template.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def _get_default(self, company):
        return self.search([
            ('company_id', '=', company.id),
            ('is_company_default', '=', True),
            ('active', '=', True),
        ], limit=1)
