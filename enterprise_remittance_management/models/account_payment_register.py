import logging
import uuid
from collections import defaultdict

from markupsafe import Markup

from odoo import Command, _, models
from odoo.exceptions import UserError
from odoo.tools import float_repr, format_amount

_logger = logging.getLogger(__name__)

DOCUMENT_TYPE_BY_MOVE_TYPE = {
    'in_invoice': 'bill',
    'in_receipt': 'bill',
    'in_refund': 'credit',
}


class AccountPaymentRegister(models.TransientModel):
    """Capture the allocation snapshot inside the native Register Payment flow.

    The hook sits on _reconcile_payments(), the last step of _create_payments(). At that point the
    wizard has already paired every created payment with exactly the journal items it will be
    reconciled against (``to_process``), and nothing has been reconciled yet. Because the hook lives
    on the model, both native "Create Payment" buttons are covered without touching the view.
    """
    _inherit = 'account.payment.register'

    # ------------------------------------------------------------------
    # Extension points
    # ------------------------------------------------------------------
    def _remittance_in_scope(self, payment):
        """Which payments get an allocation snapshot. Vendor payments only by default."""
        return payment.partner_type == 'supplier'

    # ------------------------------------------------------------------
    # Hook
    # ------------------------------------------------------------------
    def _reconcile_payments(self, to_process, edit_mode=False):
        snapshots = self._remittance_snapshot_before(to_process)
        result = super()._reconcile_payments(to_process, edit_mode=edit_mode)
        if snapshots:
            self._remittance_snapshot_after(snapshots)
        return result

    # ------------------------------------------------------------------
    # Phase 1: read everything that native reconciliation is about to change
    # ------------------------------------------------------------------
    def _remittance_snapshot_before(self, to_process):
        run_ref = uuid.uuid4().hex[:12].upper()
        snapshots = []
        for vals in to_process:
            payment = vals.get('payment')
            lines = vals.get('to_reconcile')
            if not payment or not lines or not self._remittance_in_scope(payment):
                continue
            if not payment.company_id.remittance_capture_enabled:
                continue
            try:
                snapshots.append(self._remittance_read_before(payment, lines, run_ref))
            except Exception as error:  # noqa: BLE001 - never let the audit layer break a payment (unless strict)
                self._remittance_capture_failed(payment, error)
        return snapshots

    def _remittance_read_before(self, payment, lines, run_ref):
        payable_types = payment._get_valid_payment_account_types()
        payment_lines = payment.move_id.line_ids.filtered(lambda line: line.account_type in payable_types)
        touched = lines | payment_lines
        existing_partials = self.env['account.partial.reconcile'].search(self._remittance_partial_domain(touched))

        docs = {}
        for move in lines.move_id:
            selected = lines.filtered(lambda line, move=move: line.move_id == move)
            first = selected[0]
            sign = -1 if first.account_type == 'liability_payable' else 1
            currency = first.currency_id or first.company_currency_id
            doc_lines = move.line_ids.filtered(
                lambda line: line.account_id in selected.account_id and line.partner_id == first.partner_id)
            due_dates = [line.date_maturity for line in selected if line.date_maturity]
            docs[move.id] = {
                'move': move,
                'selected': selected,
                'doc_lines': doc_lines,
                'sign': sign,
                'currency': currency,
                'vendor': first.partner_id.commercial_partner_id,
                'document_type': DOCUMENT_TYPE_BY_MOVE_TYPE.get(move.move_type, 'other'),
                'document_date': move.invoice_date or move.date,
                'due_date': min(due_dates) if due_dates else move.invoice_date_due,
                'original': currency.round(sign * sum(doc_lines.mapped('amount_currency'))),
                'due_before': currency.round(sign * sum(doc_lines.mapped('amount_residual_currency'))),
                'previous_note': self._remittance_previous_settlement_note(doc_lines, currency),
            }
        return {
            'payment': payment,
            'lines': lines,
            'payment_lines': payment_lines,
            'existing_partial_ids': set(existing_partials.ids),
            'docs': docs,
            'run_ref': run_ref,
        }

    @staticmethod
    def _remittance_partial_domain(lines):
        return ['|', ('debit_move_id', 'in', lines.ids), ('credit_move_id', 'in', lines.ids)]

    def _remittance_previous_settlement_note(self, doc_lines, currency):
        """Explain offsets that an EARLIER registration left on these lines (typically after its payment
        was cancelled while keeping the bill/credit offset), so the history stays understandable."""
        line_ids = set(doc_lines.ids)
        rows = self.env['enterprise.remittance.reconciliation'].search([
            ('kind', '=', 'offset'), ('partial_id', '!=', False),
            '|', ('debit_line_ref', 'in', list(line_ids)), ('credit_line_ref', 'in', list(line_ids)),
        ])
        notes = []
        for registration, group in self._remittance_group_by_registration(rows):
            amount = sum(
                row.credit_amount_currency if row.credit_line_ref in line_ids else row.debit_amount_currency
                for row in group)
            notes.append(_(
                "%(amount)s already offset by %(registration)s",
                amount=format_amount(self.env, amount, currency), registration=registration.name))
        return "; ".join(notes) or False

    @staticmethod
    def _remittance_group_by_registration(rows):
        grouped = defaultdict(lambda: rows.browse())
        for row in rows:
            grouped[row.registration_id] |= row
        return grouped.items()

    # ------------------------------------------------------------------
    # Phase 2: what the native reconciliation actually created
    # ------------------------------------------------------------------
    def _remittance_snapshot_after(self, snapshots):
        for snapshot in snapshots:
            payment = snapshot['payment']
            try:
                with self.env.cr.savepoint():
                    self._remittance_write_snapshot(snapshot)
            except UserError:
                raise
            except Exception as error:  # noqa: BLE001 - see _remittance_capture_failed
                self._remittance_capture_failed(payment, error)

    def _remittance_write_snapshot(self, snapshot):
        payment = snapshot['payment']
        lines, payment_lines = snapshot['lines'], snapshot['payment_lines']
        touched = lines | payment_lines
        partials = self.env['account.partial.reconcile'].search([
            *self._remittance_partial_domain(touched),
            ('id', 'not in', list(snapshot['existing_partial_ids'])),
        ], order='id')
        payment_line_ids, source_line_ids = set(payment_lines.ids), set(lines.ids)
        exchange_moves = partials.exchange_move_id

        totals = {move_id: defaultdict(float) for move_id in snapshot['docs']}
        trail = []
        for partial in partials:
            debit, credit = partial.debit_move_id, partial.credit_move_id
            if (debit.move_id | credit.move_id) & exchange_moves:
                kind = 'exchange'
            elif debit.id in payment_line_ids or credit.id in payment_line_ids:
                kind = 'payment'
            elif debit.id in source_line_ids and credit.id in source_line_ids:
                kind = 'offset'
            else:
                kind = 'other'
            trail.append(Command.create(self._remittance_trail_vals(partial, kind)))
            for line, side in ((debit, 'debit'), (credit, 'credit')):
                if line.id not in source_line_ids:
                    continue
                # A payable line sits on the credit side for a bill (positive) and on the debit side for a credit (negative).
                side_sign = 1 if side == 'credit' else -1
                own = partial.credit_amount_currency if side == 'credit' else partial.debit_amount_currency
                counterpart = partial.debit_amount_currency if side == 'credit' else partial.credit_amount_currency
                doc = totals[line.move_id.id]
                doc['partial_count'] += 1
                doc['applied_company'] += side_sign * partial.amount
                if kind == 'payment':
                    doc['payment_applied'] += side_sign * own
                    doc['payment_amount'] += side_sign * counterpart
                elif kind == 'offset':
                    doc['offset_applied'] += side_sign * own
                else:
                    doc['other_applied'] += side_sign * own

        payment_currency = payment.currency_id
        diagnostics = []
        allocation_commands = []
        allocated_in_payment_currency = 0.0
        debug_rows = []
        for move_id, doc in snapshot['docs'].items():
            currency = doc['currency']
            figures = totals[move_id]
            payment_applied = currency.round(figures['payment_applied'])
            offset_applied = currency.round(figures['offset_applied'])
            applied = currency.round(payment_applied + offset_applied)
            remaining = currency.round(doc['sign'] * sum(doc['doc_lines'].mapped('amount_residual_currency')))
            expected_remaining = currency.round(doc['due_before'] - applied - figures['other_applied'])
            line_diagnostic = False
            if not currency.is_zero(remaining - expected_remaining):
                line_diagnostic = _(
                    "Remaining %(remaining)s differs from due before %(due)s minus applied %(applied)s.",
                    remaining=format_amount(self.env, remaining, currency),
                    due=format_amount(self.env, doc['due_before'], currency),
                    applied=format_amount(self.env, applied, currency))
                diagnostics.append("%s: %s" % (doc['move'].display_name, line_diagnostic))
            elif not figures['partial_count']:
                line_diagnostic = _("No reconciliation was created for this document.")
                diagnostics.append("%s: %s" % (doc['move'].display_name, line_diagnostic))
            allocated_in_payment_currency += figures['payment_amount']
            allocation_commands.append(Command.create({
                'vendor_id': doc['vendor'].id,
                'move_id': doc['move'].id,
                'document_name': doc['move'].name or False,
                'document_ref': doc['move'].ref or False,
                'document_type': doc['document_type'],
                'document_date': doc['document_date'],
                'due_date': doc['due_date'],
                'currency_id': currency.id,
                'original_amount': doc['original'],
                'previously_settled_amount': currency.round(doc['original'] - doc['due_before']),
                'amount_due_before': doc['due_before'],
                'payment_applied': payment_applied,
                'offset_applied': offset_applied,
                'amount_applied': applied,
                'amount_remaining': remaining,
                'payment_amount': payment_currency.round(figures['payment_amount']),
                'applied_amount_company': payment.company_id.currency_id.round(figures['applied_company']),
                'previous_settlement_note': doc['previous_note'],
                'diagnostic': line_diagnostic,
            }))
            debug_rows.append("%s|%s|%s" % (
                doc['vendor'].id, doc['move'].id, float_repr(doc['due_before'], currency.decimal_places)))

        counterpart_lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_type in payment._get_valid_payment_account_types())
        settled = payment_currency.round(sum(counterpart_lines.mapped('amount_currency')))
        net = payment_currency.round(payment.amount if payment.payment_type == 'outbound' else -payment.amount)
        writeoff = payment_currency.round(settled - net)
        unallocated = payment_currency.round(settled - allocated_in_payment_currency)
        if not payment_currency.is_zero(writeoff) and not payment._seek_for_lines()[2]:
            diagnostics.append(_(
                "The payment entry settles %(settled)s but the payment amount is %(net)s and no "
                "write-off or discount line explains the difference.",
                settled=format_amount(self.env, settled, payment_currency),
                net=format_amount(self.env, net, payment_currency)))

        diagnostic = "\n".join(diagnostics)
        if diagnostic and payment.company_id.remittance_strict_mode:
            raise UserError(_(
                "The payment allocation could not be reconciled to the payment, so the registration "
                "was cancelled (strict allocation check is enabled):\n%s", diagnostic))

        # sudo: end users only have read access to audit records; they are created by this trusted capture.
        registration = self.env['enterprise.remittance.registration'].sudo().with_context(
            mail_create_nolog=True).create({
                'name': payment.name or _("Payment %s", payment.id),
                'company_id': payment.company_id.id,
                'payment_id': payment.id,
                'run_ref': snapshot['run_ref'],
                'origin': 'registered',
                'partner_id': payment.partner_id.id,
                'payment_type': payment.payment_type,
                'payment_date': payment.date,
                'memo': payment.memo or False,
                'currency_id': payment_currency.id,
                'payment_amount': payment.amount,
                'net_amount': net,
                'settled_amount': settled,
                'writeoff_amount': writeoff,
                'unallocated_amount': unallocated,
                'diagnostic': diagnostic or False,
                'has_diagnostic': bool(diagnostic),
                'debug_snapshot': "\n".join(debug_rows),
                'allocation_ids': allocation_commands,
                'reconciliation_ids': trail,
            })
        payment.message_post(
            body=Markup("<p>%s <b>%s</b>: %s</p>") % (
                _("Remittance allocation recorded"), registration.name, registration._remittance_format_net()),
            subtype_xmlid='mail.mt_note')
        return registration

    @staticmethod
    def _remittance_trail_vals(partial, kind):
        return {
            'kind': kind,
            'partial_id': partial.id,
            'partial_ref': partial.id,
            'debit_line_ref': partial.debit_move_id.id,
            'credit_line_ref': partial.credit_move_id.id,
            'debit_move_id': partial.debit_move_id.move_id.id,
            'credit_move_id': partial.credit_move_id.move_id.id,
            'debit_document': partial.debit_move_id.move_id.name or partial.debit_move_id.move_id.display_name,
            'credit_document': partial.credit_move_id.move_id.name or partial.credit_move_id.move_id.display_name,
            'amount': partial.amount,
            'debit_currency_id': partial.debit_currency_id.id,
            'credit_currency_id': partial.credit_currency_id.id,
            'debit_amount_currency': partial.debit_amount_currency,
            'credit_amount_currency': partial.credit_amount_currency,
        }

    def _remittance_capture_failed(self, payment, error):
        """A failure of the audit layer must not silently lose data, nor block a payment unless the
        company asked for strict mode."""
        if payment.company_id.remittance_strict_mode:
            raise UserError(_(
                "The payment allocation could not be recorded and strict allocation check is enabled: %s", error)
            ) from error
        _logger.exception("Remittance allocation capture failed for payment %s", payment.id)
        payment.message_post(
            body=_("The remittance allocation could not be recorded for this payment (%s). "
                   "The payment itself is unaffected; its remittance slip will use the legacy fallback.", error),
            subtype_xmlid='mail.mt_note')
