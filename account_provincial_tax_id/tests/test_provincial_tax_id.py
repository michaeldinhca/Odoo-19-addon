from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestProvincialTaxId(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fiscal_position_assigned = cls.env['account.fiscal.position'].create({
            'name': 'Assigned Fiscal Position',
            'company_id': cls.company_data['company'].id,
            'provincial_tax_id': 'ASSIGNED-123',
        })
        cls.fiscal_position_fallback = cls.env['account.fiscal.position'].create({
            'name': 'Fallback Fiscal Position',
            'company_id': cls.company_data['company'].id,
            'provincial_tax_id': 'FALLBACK-456',
        })
        cls.fiscal_position_blank = cls.env['account.fiscal.position'].create({
            'name': 'Blank Fiscal Position',
            'company_id': cls.company_data['company'].id,
        })
        cls.partner_a.property_account_position_id = cls.fiscal_position_fallback

    def _create_invoice(self, **extra_vals):
        vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test product', 'quantity': 1, 'price_unit': 100.0,
            })],
        }
        vals.update(extra_vals)
        return self.env['account.move'].create(vals)

    def test_own_fiscal_position_wins_over_fallback(self):
        """A document's own fiscal_position_id is always honored, even when
        the partner's property_account_position_id would resolve to a
        different one."""
        move = self._create_invoice(fiscal_position_id=self.fiscal_position_assigned.id)
        result = self.env['account.fiscal.position']._get_document_provincial_fiscal_position(move)
        self.assertEqual(result, self.fiscal_position_assigned)
        self.assertEqual(result.provincial_tax_id, 'ASSIGNED-123')

    def test_fallback_resolves_via_partner_when_unset(self):
        """When the document has no fiscal_position_id of its own, fall back
        to resolving one from the partner (per the company's configured
        address source).

        account.move auto-computes fiscal_position_id from the partner's
        property_account_position_id on create, so fiscal_position_id must
        be explicitly cleared here to exercise the fallback branch (rather
        than the "already assigned" branch, which also happens to land on
        the same fiscal position in this case)."""
        move = self._create_invoice(fiscal_position_id=False)
        self.assertFalse(move.fiscal_position_id)
        result = self.env['account.fiscal.position']._get_document_provincial_fiscal_position(move)
        self.assertEqual(result, self.fiscal_position_fallback)
        self.assertEqual(result.provincial_tax_id, 'FALLBACK-456')

    def test_fiscal_position_without_provincial_tax_id_returns_empty(self):
        """A resolvable fiscal position with no Provincial Tax ID configured
        should not be treated as applicable -> no line should be printed."""
        move = self._create_invoice(fiscal_position_id=self.fiscal_position_blank.id)
        result = self.env['account.fiscal.position']._get_document_provincial_fiscal_position(move)
        self.assertFalse(result)

    def test_no_fiscal_position_returns_false(self):
        """No resolvable fiscal position at all -> no error, no value."""
        self.partner_a.property_account_position_id = False
        move = self._create_invoice(fiscal_position_id=False)
        result = self.env['account.fiscal.position']._get_document_provincial_fiscal_position(move)
        self.assertFalse(result)

    def test_blank_record_returns_false(self):
        result = self.env['account.fiscal.position']._get_document_provincial_fiscal_position(self.env['account.move'])
        self.assertFalse(result)
