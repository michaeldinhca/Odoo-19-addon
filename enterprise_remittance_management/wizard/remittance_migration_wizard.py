import logging
import re
from collections import defaultdict

from odoo import Command, _, fields, models
from odoo.exceptions import AccessError
from odoo.tools import float_repr

_logger = logging.getLogger(__name__)

# One entry per line, ";" or ", " followed by the next "digits|" entry.
_SNAPSHOT_SEPARATOR = re.compile(r'[\r\n;]+|,\s+(?=\d+\|)')
_DOCUMENT_TYPE_BY_MOVE_TYPE = {'in_invoice': 'bill', 'in_receipt': 'bill', 'in_refund': 'credit'}


def parse_legacy_snapshot(text):
    """Parse the readable legacy snapshot, one ``Vendor ID|Move ID|Amount`` entry per line.

    Credits carry a negative amount, for example ``5018|36444|-2185.19``.
    Nothing is repaired or guessed: every entry that is not clean is returned as an error. This is a pure
    function (no environment), so the reasons are plain English.

    :return: (entries, errors) where entries are dicts with vendor_id, move_id, amount and raw, and
             errors are (position, raw text, reason) tuples.
    """
    entries, errors, seen = [], [], set()
    for position, raw in enumerate(_SNAPSHOT_SEPARATOR.split(text or ''), start=1):
        raw = raw.strip()
        if not raw:
            continue
        parts = [part.strip() for part in raw.split('|')]
        if len(parts) != 3:
            errors.append((position, raw, "expected 3 values separated by |, found %s" % len(parts)))
            continue
        try:
            vendor_id, move_id, amount = int(parts[0]), int(parts[1]), float(parts[2])
        except ValueError:
            errors.append((position, raw, "vendor id, move id and amount must be numbers"))
            continue
        if vendor_id <= 0 or move_id <= 0:
            errors.append((position, raw, "ids must be positive"))
        elif move_id in seen:
            errors.append((position, raw, "document %s appears more than once" % move_id))
        else:
            seen.add(move_id)
            entries.append({'vendor_id': vendor_id, 'move_id': move_id, 'amount': amount, 'raw': raw})
    return entries, errors


class RemittanceMigrationWizard(models.TransientModel):
    """Optional utility that imports legacy Studio allocation data into the addon's relational model.

    It only reads the legacy fields through their configured technical names, so a fresh installation
    never needs Studio, and the same tool works on any database where those names are configured.
    Malformed, ambiguous or inconsistent rows are reported and skipped: no historical value is invented.
    It never disables or edits legacy actions, automations or reports.
    """
    _name = 'enterprise.remittance.migration.wizard'
    _description = 'Legacy Allocation Migration'

    # Legacy naming, editable so the tool is not tied to one database
    legacy_snapshot_field = fields.Char(
        string="Snapshot Field on Payment", default='x_studio_payment_allocation_snapshot',
        help="Text field on account.payment holding the readable Vendor ID|Move ID|Amount snapshot.")
    legacy_line_model = fields.Char(
        string="Allocation Line Model", default='x_payment_allocation_l',
        help="Technical name of the legacy allocation line model.")
    legacy_lines_field = fields.Char(
        string="Lines Field on Payment", default='x_studio_invoice_bill_lines',
        help="One2many on account.payment pointing to the legacy allocation lines (used to find legacy artifacts).")
    legacy_payment_field = fields.Char(string="Payment Field", default='x_studio_payment_id')
    legacy_move_field = fields.Char(string="Document Field", default='x_studio_move_id')
    legacy_total_field = fields.Char(string="Document Total Field", default='x_studio_document_total')
    legacy_before_field = fields.Char(string="Balance Before Payment Field", default='x_studio_balance_before_payment')
    legacy_applied_field = fields.Char(string="Applied Amount Field", default='x_studio_value')
    legacy_remaining_field = fields.Char(string="Remaining Field", default='x_studio_remaining')
    legacy_currency_field = fields.Char(string="Currency Field", default='x_studio_currency_id')
    credits_stored_positive = fields.Boolean(
        string="Legacy Credits Are Positive Numbers",
        help="Tick only if the legacy lines store credit amounts as positive numbers. They are then negated "
             "on import so credits are negative, as everywhere in this addon.")

    report = fields.Text(readonly=True)
    issue_count = fields.Integer(readonly=True)
    payment_count = fields.Integer(string="Payments Found", readonly=True)
    migrated_count = fields.Integer(string="Payments Migrated", readonly=True)
    skipped_count = fields.Integer(string="Payments Skipped", readonly=True)

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------
    def action_scan(self):
        return self._run(dry_run=True)

    def action_migrate(self):
        return self._run(dry_run=False)

    def action_find_legacy_artifacts(self):
        self._check_rights()
        lines = [_("Legacy artifacts that reference the old allocation data. Nothing was changed: "
                   "disable them manually, and only after the new addon has been validated.")]
        tokens = [token for token in (self.legacy_snapshot_field, self.legacy_line_model, self.legacy_lines_field,
                                      'x_studio_move_id_list') if token]
        artifacts = self._find_legacy_artifacts(tokens)
        if not artifacts:
            lines.append(_("No legacy artifact found."))
        lines += ["%s | %s | %s" % (kind, record_id, name) for kind, record_id, name in artifacts]
        self.report = "\n".join(lines)
        return self._reopen()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _check_rights(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only Settings administrators can run the legacy migration."))

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }

    def _find_legacy_artifacts(self, tokens):
        """Server actions, automation rules and views/report templates that mention the legacy names."""
        found = []
        code_domain = [('code', 'ilike', token) for token in tokens]
        server_actions = self.env['ir.actions.server']
        if code_domain:
            server_actions = server_actions.search(['|'] * (len(code_domain) - 1) + code_domain)
        found += [('Server action', action.id, action.name) for action in server_actions]
        if self.env.registry.get('base.automation') is not None and \
                'action_server_ids' in self.env['base.automation']._fields:
            for rule in self.env['base.automation'].search([('action_server_ids', 'in', server_actions.ids)]):
                found.append(('Automation rule', rule.id, rule.name))
        for token in tokens:
            for view in self.env['ir.ui.view'].search([('arch_db', 'ilike', token)]):
                found.append(('View / report template', view.id, view.display_name))
        seen, unique = set(), []
        for item in found:
            if item[:2] not in seen:
                seen.add(item[:2])
                unique.append(item)
        return unique

    def _legacy_setup(self):
        """Resolve the configured legacy names, or explain what is missing."""
        payment_fields = self.env['account.payment']._fields
        line_model = self.env.registry.get(self.legacy_line_model or '')
        problems = []
        if self.legacy_snapshot_field and self.legacy_snapshot_field not in payment_fields:
            problems.append(_("Field %s does not exist on payments.", self.legacy_snapshot_field))
        if line_model is None:
            problems.append(_("Model %s does not exist.", self.legacy_line_model))
        else:
            line_fields = self.env[self.legacy_line_model]._fields
            required = ('legacy_payment_field', 'legacy_move_field', 'legacy_before_field',
                        'legacy_applied_field', 'legacy_remaining_field')
            optional = ('legacy_total_field', 'legacy_currency_field')
            for name in required + optional:
                if (self[name] or name in required) and self[name] not in line_fields:
                    problems.append(_("Field %(field)s does not exist on %(model)s.",
                                      field=self[name], model=self.legacy_line_model))
        return line_model is not None and not problems, problems

    # ------------------------------------------------------------------
    # The only two places that read the legacy data dynamically
    # ------------------------------------------------------------------
    def _legacy_lines_by_payment(self):
        """:return: {payment id: [dict(label, move, currency, total, before, applied, remaining)]}"""
        lines = defaultdict(list)
        for line in self.env[self.legacy_line_model].search([(self.legacy_payment_field, '!=', False)]):
            lines[line[self.legacy_payment_field].id].append({
                'label': "%s#%s" % (self.legacy_line_model, line.id),
                'move': line[self.legacy_move_field],
                'currency': line[self.legacy_currency_field] if self.legacy_currency_field else False,
                'total': line[self.legacy_total_field] if self.legacy_total_field else None,
                'before': line[self.legacy_before_field] or 0.0,
                'applied': line[self.legacy_applied_field] or 0.0,
                'remaining': line[self.legacy_remaining_field] or 0.0,
            })
        return lines

    def _legacy_snapshot_payments(self):
        """:return: {payment id: legacy snapshot text} for payments that carry one."""
        if not self.legacy_snapshot_field:
            return {}
        payments = self.env['account.payment'].search([(self.legacy_snapshot_field, '!=', False)])
        return {payment.id: payment[self.legacy_snapshot_field] for payment in payments}

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------
    def _run(self, dry_run):
        self.ensure_one()
        self._check_rights()
        ready, problems = self._legacy_setup()
        if not ready:
            self.write({'report': "\n".join([_("Nothing to migrate.")] + problems), 'issue_count': len(problems),
                        'payment_count': 0, 'migrated_count': 0, 'skipped_count': 0})
            return self._reopen()

        lines_by_payment = self._legacy_lines_by_payment()
        snapshot_by_payment = self._legacy_snapshot_payments()
        payments = self.env['account.payment'].browse(set(lines_by_payment) | set(snapshot_by_payment)).filtered(
            lambda payment: payment.partner_type == 'supplier')

        report, migrated, skipped, issue_total = [], 0, 0, 0
        for payment in payments.sorted('id'):
            if payment.remittance_registration_ids:
                report.append("%s: %s" % (payment.display_name, _("already has a remittance record, left untouched")))
                skipped += 1
                continue
            vals, issues = self._build_registration_vals(
                payment, lines_by_payment.get(payment.id, []), snapshot_by_payment.get(payment.id, ''))
            issue_total += len(issues)
            for issue in issues:
                report.append("%s: %s" % (payment.display_name, issue))
            if not vals['allocation_ids']:
                skipped += 1
                report.append("%s: %s" % (payment.display_name, _("no reliable allocation line, payment skipped")))
                continue
            if not dry_run:
                # sudo: audit records are read-only for end users; the migration is restricted to Settings administrators.
                self.env['enterprise.remittance.registration'].sudo().with_context(mail_create_nolog=True).create(vals)
            migrated += 1
        header = _("%(mode)s: %(payments)s payments found, %(migrated)s %(verb)s, %(skipped)s skipped, %(issues)s issues.",
                   mode=_("Dry run") if dry_run else _("Migration"), payments=len(payments), migrated=migrated,
                   verb=_("can be migrated") if dry_run else _("migrated"), skipped=skipped, issues=issue_total)
        self.write({
            'report': "\n".join([header] + report), 'issue_count': issue_total, 'payment_count': len(payments),
            'migrated_count': migrated, 'skipped_count': skipped,
        })
        return self._reopen()

    def _build_registration_vals(self, payment, legacy_lines, snapshot_text):
        """Turn the legacy data of one payment into registration values, plus the list of issues found.

        A legacy line is imported only when it is complete, consistent (before - applied = remaining), uses
        the expected sign convention and agrees with the snapshot text. Otherwise it is reported and left out.
        """
        issues = []
        entries, errors = parse_legacy_snapshot(snapshot_text)
        issues += [_("snapshot entry %(position)s %(raw)r ignored: %(reason)s", position=p, raw=raw, reason=reason)
                   for p, raw, reason in errors]
        entry_by_move = {entry['move_id']: entry for entry in entries}
        currency = payment.currency_id
        allocation_commands, used_moves = [], set()
        for line in legacy_lines:
            move, label = line['move'], line['label']
            if not move:
                issues.append(_("%s has no document, skipped", label))
                continue
            if move.id in used_moves:
                issues.append(_("%(label)s: document %(move)s appears more than once, skipped",
                                label=label, move=move.display_name))
                continue
            doc_type = _DOCUMENT_TYPE_BY_MOVE_TYPE.get(move.move_type, 'other')
            doc_currency = line['currency'] or move.currency_id
            values = {name: line[name] for name in ('before', 'applied', 'remaining')}
            values['total'] = line['total'] if line['total'] is not None else 0.0
            if self.credits_stored_positive and doc_type == 'credit':
                values = {name: -value for name, value in values.items()}
            problem = self._line_problem(doc_type, values, doc_currency)
            entry = entry_by_move.get(move.id)
            vendor = move.partner_id.commercial_partner_id
            if not problem and entry:
                if entry['vendor_id'] != vendor.id:
                    problem = _("snapshot vendor id %(snapshot)s differs from the document vendor %(vendor)s",
                                snapshot=entry['vendor_id'], vendor=vendor.id)
                elif not doc_currency.is_zero(entry['amount'] - values['before']):
                    problem = _("snapshot amount %(snapshot)s differs from the balance before payment %(before)s",
                                snapshot=entry['amount'], before=values['before'])
            if problem:
                issues.append("%s (%s): %s" % (label, move.display_name, problem))
                continue
            used_moves.add(move.id)
            allocation_commands.append(Command.create({
                'vendor_id': vendor.id,
                'move_id': move.id,
                'document_name': move.name or False,
                'document_ref': move.ref or False,
                'document_type': doc_type,
                'document_date': move.invoice_date or move.date,
                'due_date': move.invoice_date_due,
                'currency_id': doc_currency.id,
                'original_amount': values['total'],
                'previously_settled_amount': doc_currency.round(values['total'] - values['before']),
                'amount_due_before': values['before'],
                'payment_applied': 0.0,
                'offset_applied': 0.0,
                'amount_applied': values['applied'],
                'amount_remaining': values['remaining'],
                'payment_amount': 0.0,
                'applied_amount_company': 0.0,
                'split_known': False,
                'legacy_source': label,
            }))
        legacy_moves = {line['move'].id for line in legacy_lines if line['move']}
        for move_id, entry in entry_by_move.items():
            if move_id not in legacy_moves:
                issues.append(_("snapshot entry %(raw)r has no allocation line: not imported, no value is invented",
                                raw=entry['raw']))
        net = currency.round(payment.amount if payment.payment_type == 'outbound' else -payment.amount)
        applied_signed = sum(command[2]['amount_applied'] for command in allocation_commands)
        if allocation_commands and not currency.is_zero(applied_signed - net):
            issues.append(_("applied amounts total %(applied)s but the net payment is %(net)s: the legacy selection "
                            "may be incomplete", applied=applied_signed, net=net))
        diagnostic = "\n".join(issues)
        return {
            'name': payment.name or _("Payment %s", payment.id),
            'company_id': payment.company_id.id,
            'payment_id': payment.id,
            'origin': 'migrated',
            'partner_id': payment.partner_id.id,
            'payment_type': payment.payment_type,
            'payment_date': payment.date,
            'memo': payment.memo or False,
            'currency_id': currency.id,
            'payment_amount': payment.amount,
            'net_amount': net,
            'settled_amount': net,
            'writeoff_amount': 0.0,
            'unallocated_amount': currency.round(net - applied_signed) if allocation_commands else 0.0,
            'diagnostic': diagnostic or False,
            'has_diagnostic': bool(diagnostic),
            'debug_snapshot': "\n".join(
                "%s|%s|%s" % (e['vendor_id'], e['move_id'], float_repr(e['amount'], currency.decimal_places))
                for e in entries),
            'allocation_ids': allocation_commands,
        }, issues

    def _line_problem(self, doc_type, values, currency):
        """Reject a legacy line that is internally inconsistent or uses another sign convention."""
        before, applied, remaining = values['before'], values['applied'], values['remaining']
        if not currency.is_zero(before - applied - remaining):
            return _("balance before payment %(before)s minus applied %(applied)s is not the remaining %(remaining)s",
                     before=before, applied=applied, remaining=remaining)
        if doc_type == 'credit' and any(value > 0 for value in values.values()):
            return _("credit with positive amounts: tick 'Legacy Credits Are Positive Numbers' if that is the convention")
        if doc_type == 'bill' and any(value < 0 for value in values.values()):
            return _("bill with negative amounts")
        return False
