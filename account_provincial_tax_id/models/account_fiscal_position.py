from odoo import fields, models


class AccountFiscalPosition(models.Model):
    _inherit = 'account.fiscal.position'

    provincial_tax_id = fields.Char(
        string="Provincial Tax ID",
        help="Secondary tax registration number (e.g. a provincial tax ID) "
             "for this fiscal position, printed under the company's main "
             "tax ID on document headers. Leave blank for fiscal positions "
             "that don't need one.")

    def _get_document_provincial_fiscal_position(self, record):
        """Resolve the fiscal position whose Provincial Tax ID applies to a
        business document, so the report can print both its name and its
        Provincial Tax ID (e.g. "Manitoba Tax ID: 163809-7").

        Prefers the fiscal position already assigned to the document
        (e.g. sale.order/account.move fiscal_position_id), so manual
        overrides and existing tax computation are always respected.
        Falls back to resolving a fiscal position from the document's
        partner (per the company's configured Delivery/Invoice address
        preference) only for documents with no fiscal_position_id field
        of their own (e.g. stock.picking).

        :return: an account.fiscal.position record with a Provincial Tax ID
            set, or an empty recordset if none applies.
        """
        empty = self.env['account.fiscal.position']
        if not record:
            return empty

        fiscal_position = empty
        if 'fiscal_position_id' in record._fields and record.fiscal_position_id:
            fiscal_position = record.fiscal_position_id
        else:
            company = record.company_id if 'company_id' in record._fields and record.company_id else self.env.company
            source = company.provincial_tax_id_source or 'delivery'
            if source == 'delivery':
                partner = getattr(record, 'partner_shipping_id', False) or getattr(record, 'partner_id', False)
            else:
                partner = getattr(record, 'partner_invoice_id', False) or getattr(record, 'partner_id', False)
            if partner:
                fiscal_position = self.env['account.fiscal.position'].sudo().with_company(company)._get_fiscal_position(partner)

        # sudo(): the acting report user (e.g. a portal user viewing an
        # invoice/SO PDF) may not have read access to account.fiscal.position.
        fiscal_position = fiscal_position.sudo()
        return fiscal_position if fiscal_position.provincial_tax_id else empty
