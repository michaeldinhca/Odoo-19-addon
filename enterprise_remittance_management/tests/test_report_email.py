import re
from datetime import timedelta

import lxml.html

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import RemittanceCommon

REPORT = 'enterprise_remittance_management.report_remittance_slip'


class RemittanceRenderCommon(RemittanceCommon):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean(text):
        return re.sub(r'\s+', ' ', (text or '').replace('\xa0', ' ')).strip()

    def _html(self, payment):
        content, _fmt = self.env['ir.actions.report']._render_qweb_html(REPORT, payment.ids)
        return content.decode()

    def _tables(self, html):
        """{section title: (rows of cell texts, row css classes)} for the detail tables of the slip."""
        root = lxml.html.fromstring(html)
        tables = {}
        for table in root.xpath('//table[contains(@class, "remittance-table")]'):
            title = self._clean(table.xpath('preceding-sibling::h5[1]')[0].text_content())
            body_rows = table.xpath('.//tbody/tr')
            tables[title] = (
                [[self._clean(cell.text_content()) for cell in row.xpath('./td')] for row in body_rows],
                [row.get('class') or '' for row in body_rows],
            )
        return tables

    def _summary(self, html):
        root = lxml.html.fromstring(html)
        return {
            self._clean(row.xpath('./th')[0].text_content()): self._clean(row.xpath('./td')[0].text_content())
            for row in root.xpath('//table[contains(@class, "remittance-summary")]//tr')
        }


@tagged('post_install', '-at_install')
class TestRemittanceSlip(RemittanceRenderCommon):

    # ------------------------------------------------------------------
    # Structure
    # ------------------------------------------------------------------
    def test_report_is_bound_to_payments_as_a_pdf_report(self):
        report = self.env.ref('enterprise_remittance_management.action_report_remittance_slip')
        self.assertEqual(report.model, 'account.payment')
        self.assertEqual(report.report_type, 'qweb-pdf')
        self.assertEqual(report.binding_model_id.model, 'account.payment')
        self.assertEqual(report.binding_type, 'report')
        self.assertTrue(self.env.ref(REPORT))
        bill = self._bill(self.vendor_a, 10.0)
        payment = self._register(bill)
        # discard_logo_check: skip Odoo's one-time "configure your document layout" step for a fresh company.
        action = payment.with_context(discard_logo_check=True).action_print_remittance_slip()
        self.assertEqual(action['report_name'], REPORT)
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertIn('Remittance Slip', report._render_qweb_html(REPORT, payment.ids)[0].decode())

    def test_native_payment_receipt_is_untouched_and_still_renders(self):
        bill = self._bill(self.vendor_a, 10.0)
        payment = self._register(bill)
        native = self.env.ref('account.action_report_payment_receipt')
        self.assertEqual(native.report_name, 'account.report_payment_receipt')
        html = native._render_qweb_html('account.report_payment_receipt', payment.ids)[0].decode()
        self.assertIn('Payment Receipt', html)
        template = self.env.ref('account.mail_template_data_payment_receipt')
        self.assertNotIn(self.env.ref('enterprise_remittance_management.action_report_remittance_slip'),
                         template.report_template_ids)

    def test_pdf_render_entry_point(self):
        bill = self._bill(self.vendor_a, 10.0)
        payment = self._register(bill)
        report = self.env.ref('enterprise_remittance_management.action_report_remittance_slip')
        content, fmt = report._render_qweb_pdf(report, payment.ids)
        self.assertTrue(content)
        # Odoo returns the HTML in test mode; a real run returns the PDF.
        self.assertTrue(content.startswith(b'%PDF') or b'Remittance Slip' in content)

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------
    def test_one_bill(self):
        bill = self._bill(self.vendor_a, 500.0, ref='V-INV-1')
        payment = self._register(bill)
        payment.remittance_note = 'Thank you for your patience'

        html = self._html(payment)

        text = self._clean(lxml.html.fromstring(html).text_content())
        self.assertIn('Remittance Slip', text)
        self.assertIn('Vendor A', text)
        self.assertIn(payment.name, text)
        self.assertIn('Thank you for your patience', text)
        self.assertNotIn('DRAFT', text)
        tables = self._tables(html)
        self.assertEqual(list(tables), ['Bills Paid'])
        rows, classes = tables['Bills Paid']
        self.assertEqual(len(rows), 1)
        self.assertIn('V-INV-1', rows[0][0])
        self.assertIn(bill.name, rows[0][0])
        for cell in rows[0][3:6]:                 # original, due before payment, applied
            self.assertIn('500.00', cell)
        self.assertIn('0.00', rows[0][6])         # remaining after payment
        self.assertNotIn('remittance-remaining', classes[0])
        summary = self._summary(html)
        self.assertIn('500.00', summary['Bills Paid'])
        self.assertIn('0.00', summary['Credits Applied'])
        self.assertIn('500.00', summary['Net Payment Sent to Vendor'])

    def test_grouped_bills_are_sorted_deterministically(self):
        newer = self._bill(self.vendor_a, 9.67, ref='B-NEW', date=self.bill_date + timedelta(days=5))
        older_b = self._bill(self.vendor_a, 30.0, ref='B-OLD-B')
        older_a = self._bill(self.vendor_a, 50.41, ref='B-OLD-A')
        payment = self._register(newer | older_b | older_a, group=True)

        rows, _classes = self._tables(self._html(payment))['Bills Paid']

        self.assertEqual([row[0].split()[0] for row in rows], ['B-OLD-A', 'B-OLD-B', 'B-NEW'])
        self.assertIn('90.08', self._summary(self._html(payment))['Bills Paid'])

    def test_mixed_credit_is_inbound_and_credits_are_negative(self):
        bill = self._bill(self.vendor_a, 1461.32, ref='BILL-1')
        credit = self._credit(self.vendor_a, 2185.19, ref='CN-1')
        payment = self._register(bill | credit, group=True)

        html = self._html(payment)
        tables = self._tables(html)

        # The bill that was offset against the credit (not reconciled with the payment entry) is still on the slip.
        self.assertEqual(sorted(tables), ['Bills Paid', 'Credits Applied'])
        bill_row = tables['Bills Paid'][0][0]
        credit_row = tables['Credits Applied'][0][0]
        self.assertIn('BILL-1', bill_row[0])
        self.assertIn('1,461.32', bill_row[5])
        self.assertIn('CN-1', credit_row[0])
        self.assertRegex(credit_row[3], r'-.*2,185\.19')
        self.assertRegex(credit_row[5], r'-.*2,185\.19')
        summary = self._summary(html)
        self.assertRegex(summary['Credits Applied'], r'-.*2,185\.19')
        self.assertIn('723.87', summary['Net Payment Received from Vendor'])
        self.assertNotIn('Net Payment Sent to Vendor', summary)
        # Bills paid plus (negative) credits applied is exactly the signed net payment.
        data = payment._remittance_slip_data()
        bills = sum(amount for _cur, amount in data['totals']['bills'])
        credits = sum(amount for _cur, amount in data['totals']['credits'])
        self.assertAlmostEqual(bills + credits, data['net'])
        self.assertAlmostEqual(data['net'], -723.87)

    def test_partial_payment_flags_remaining_balances(self):
        bill_1 = self._bill(self.vendor_a, 500.0, ref='B1')
        bill_2 = self._bill(self.vendor_a, 300.0, ref='B2')
        payment = self._register(bill_1 | bill_2, group=True, amount=600.0)

        html = self._html(payment)
        rows, classes = self._tables(html)['Bills Paid']

        flagged = [row[0].split()[0] for row, css in zip(rows, classes) if 'remittance-remaining' in css]
        self.assertEqual(flagged, ['B2'])
        remaining_cell = [row for row in rows if row[0].startswith('B2')][0][6]
        self.assertIn('200.00', remaining_cell)
        self.assertIn('Highlighted lines still have a balance', self._clean(lxml.html.fromstring(html).text_content()))

    def test_multicurrency_amounts_are_labelled_with_their_own_currency(self):
        eur = self.setup_other_currency('EUR')
        bill = self._bill(self.vendor_a, 300.0, ref='EUR-1', currency=eur)
        payment = self._register(bill, currency=self.company.currency_id)

        html = self._html(payment)
        rows, _classes = self._tables(html)['Bills Paid']

        self.assertIn(eur.symbol, rows[0][3])                     # document amounts in EUR
        self.assertNotIn(self.company.currency_id.symbol, rows[0][3])
        self.assertIn('paid', rows[0][5])                         # share of the payment, in the payment currency
        self.assertIn(self.company.currency_id.symbol, rows[0][5])
        summary = self._summary(html)
        self.assertIn(eur.symbol, summary['Bills Paid'])
        self.assertIn(self.company.currency_id.symbol, summary['Net Payment Sent to Vendor'])
        self.assertIn('currency of each document', self._clean(lxml.html.fromstring(html).text_content()))

    def test_note_is_optional_and_configurable(self):
        bill = self._bill(self.vendor_a, 10.0)
        payment = self._register(bill)
        self.assertNotIn('Note:', self._clean(lxml.html.fromstring(self._html(payment)).text_content()))
        payment.remittance_note = 'Ref 42'
        self.assertIn('Note: Ref 42', self._clean(lxml.html.fromstring(self._html(payment)).text_content()))
        self.company.remittance_show_note = False
        self.assertNotIn('Ref 42', self._html(payment))

    def test_draft_and_cancelled_payments_are_labelled(self):
        bill = self._bill(self.vendor_a, 10.0)
        payment = self._register(bill)
        payment.action_draft()
        self.assertIn('DRAFT', self._html(payment))
        payment.action_cancel()
        self.assertIn('CANCELLED', self._html(payment))

    # ------------------------------------------------------------------
    # Legacy payments (no snapshot)
    # ------------------------------------------------------------------
    def test_legacy_payment_gets_a_clearly_labelled_fallback(self):
        self.company.remittance_capture_enabled = False
        bill = self._bill(self.vendor_a, 250.0, ref='OLD-1')
        payment = self._register(bill)
        self.assertFalse(payment.remittance_registration_ids)

        data = payment._remittance_slip_data()
        html = self._html(payment)

        self.assertEqual(data['source'], 'legacy')
        self.assertIn('recorded before allocation tracking', self._clean(lxml.html.fromstring(html).text_content()))
        rows, _classes = self._tables(html)['Bills Paid']
        self.assertIn('OLD-1', rows[0][0])
        self.assertIn('250.00', rows[0][5])
        # Balances before payment are not known: never invented.
        self.assertEqual(rows[0][4], 'n/a')
        self.assertEqual(rows[0][6], 'n/a')

    def test_legacy_payment_that_current_data_cannot_explain_prints_no_table(self):
        self.company.remittance_capture_enabled = False
        bill = self._bill(self.vendor_a, 60.0, ref='OLD-1')
        payment = self._register(bill, amount=100.0)      # 40 left on account: reconciliation does not explain 100

        data = payment._remittance_slip_data()
        html = self._html(payment)

        self.assertEqual(data['source'], 'unavailable')
        self.assertFalse(self._tables(html))
        self.assertIn('cannot be shown reliably', self._clean(lxml.html.fromstring(html).text_content()))

    def test_legacy_fallback_does_not_pretend_to_be_the_full_selection(self):
        self.company.remittance_capture_enabled = False
        bill = self._bill(self.vendor_a, 1461.32, ref='BILL-1')
        credit = self._credit(self.vendor_a, 2185.19, ref='CN-1')
        payment = self._register(bill | credit, group=True)

        html = self._html(payment)
        tables = self._tables(html)

        # Only what natively reconciles to the payment: the offset bill is missing, and the slip says so.
        self.assertEqual(list(tables), ['Credits Applied'])
        self.assertIn('may not show the complete original selection',
                      self._clean(lxml.html.fromstring(html).text_content()))


@tagged('post_install', '-at_install')
class TestRemittanceEmail(RemittanceRenderCommon):

    def setUp(self):
        super().setUp()
        self.template = self.env.ref('enterprise_remittance_management.mail_template_remittance')

    def _body(self, payment):
        return self._clean(lxml.html.fromstring(
            self.template._render_field('body_html', payment.ids)[payment.id]).text_content())

    def test_template_is_a_payment_template_with_the_slip_attached(self):
        self.assertEqual(self.template.model, 'account.payment')
        self.assertEqual(self.template.report_template_ids,
                         self.env.ref('enterprise_remittance_management.action_report_remittance_slip'))

    def test_outbound_multi_bill_email(self):
        bill_1 = self._bill(self.vendor_a, 80.08, ref='B1')
        bill_2 = self._bill(self.vendor_a, 9.67, ref='B2')
        payment = self._register(bill_1 | bill_2, group=True)

        body = self._body(payment)

        self.assertIn('Dear Vendor A', body)
        self.assertIn(payment.name, body)
        self.assertIn('has issued a net payment of', body)
        self.assertIn('89.75', body)
        for expected in ('B1', 'B2', '80.08', '9.67'):
            self.assertIn(expected, body)
        subject = self.template._render_field('subject', payment.ids)[payment.id]
        self.assertIn(payment.name, subject)

    def test_inbound_email_with_credit_lists_the_bill_hidden_by_the_offset(self):
        bill = self._bill(self.vendor_a, 1461.32, ref='BILL-1')
        credit = self._credit(self.vendor_a, 2185.19, ref='CN-1')
        payment = self._register(bill | credit, group=True)
        self.assertNotIn(bill, self._documents_reconciled_with_payment(payment))

        body = self._body(payment)

        self.assertIn('received a net amount of', body)
        self.assertIn('723.87', body)
        self.assertIn('BILL-1', body)           # not lost although the offset came before the payment
        self.assertIn('CN-1 (credit)', body)
        self.assertRegex(body, r'-\D{0,3}2,185\.19')
        # Vendor facing: nothing internal.
        registration = self._registration(payment)
        for internal in (registration.run_ref, 'approval', 'Reconciliation', 'debug'):
            self.assertNotIn(internal, body)

    def test_best_regards_is_not_duplicated_by_the_signature(self):
        bill = self._bill(self.vendor_a, 10.0)
        payment = self._register(bill)
        for signature, expected_count in (
            (False, 1),
            ('<p>Best regards,<br/>Accounts Payable</p>', 1),
            ('<p>Kind regards, Accounts</p>', 0),
            ('<p>Accounts Payable</p>', 1),
        ):
            with self.subTest(signature=signature):
                self.env.user.signature = signature
                body = self._body(payment)
                self.assertEqual(body.count('Best regards'), expected_count, body)
                if signature:
                    self.assertIn('Accounts', body)

    def test_legacy_payment_email_has_no_misleading_table(self):
        self.company.remittance_capture_enabled = False
        payment = self._register(self._bill(self.vendor_a, 10.0))
        body = self._body(payment)
        self.assertIn('attached remittance slip lists the documents', body)
        html = self.template._render_field('body_html', payment.ids)[payment.id]
        self.assertNotIn('<table', html)

    def test_composer_attaches_the_slip_and_addresses_the_vendor(self):
        bill = self._bill(self.vendor_a, 1461.32, ref='BILL-1')
        credit = self._credit(self.vendor_a, 2185.19, ref='CN-1')
        payment = self._register(bill | credit, group=True)

        action = payment.action_send_remittance()
        self.assertEqual(action['res_model'], 'mail.compose.message')
        composer = self.env['mail.compose.message'].with_context(**action['context']).create({})

        self.assertEqual(composer.template_id, self.template)
        self.assertIn(payment.name, composer.subject)
        self.assertIn(self.vendor_a, composer.partner_ids)
        self.assertIn('BILL-1', composer.body)
        attachments = composer.attachment_ids
        self.assertEqual(len(attachments), 1)
        self.assertIn('Remittance Slip', attachments.name)
        self.assertTrue(attachments.raw)
        self.assertTrue(attachments.raw.startswith(b'%PDF') or b'BILL-1' in attachments.raw)

        composer._action_send_mail()
        sent = payment.message_ids.filtered(lambda message: message.message_type == 'comment')[:1]
        self.assertTrue(sent)
        self.assertIn('Remittance Slip', ' '.join(sent.attachment_ids.mapped('name')))
        self.assertIn(self.vendor_a, sent.partner_ids)

    def test_sending_needs_a_template(self):
        self.template.unlink()
        payment = self._register(self._bill(self.vendor_a, 10.0))
        with self.assertRaises(UserError):
            payment.action_send_remittance()
