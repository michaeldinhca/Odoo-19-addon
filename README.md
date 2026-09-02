# Odoo 19 Addons Repository

## Warranty Addons
Core warranty and serial number management modules.

### Modules
- `bi_all_in_one_warranty_registration`
- `bi_pos_warranty`
- `bi_warranty_registration`
- `bi_website_warranty_registration`
- `v9_sale_invoice_serial`

### Purpose
- Warranty registration
- Warranty claim management
- Serial number tracking
- POS warranty support
- Website warranty registration


---

## Shopify Integration Addons
Modules related to Shopify synchronization and background processing.

### Modules
- `integration`
- `integration_queue_job`
- `integration_shopify`

### Purpose
- Shopify order synchronization
- Product synchronization
- Customer synchronization
- Queue/background job processing
- Shopify connector framework


---

## Accounting / QuickBooks Addons
Modules related to accounting integrations.

### Modules
- `quickbooks_sync_online`

### Purpose
- QuickBooks Online synchronization
- Accounting data integration
- Financial sync support


---

## Survey Addons
Modules extending the standard Survey app.

### Modules
- `survey_file_upload`

### Purpose
- Adds a "File Upload" question type to Survey, with per-question size/multi-file
  limits and AJAX (non-blocking) upload
- Clean-room build (see `survey_file_upload/CLAUDE.md`) — not a port of any
  third-party module


---

## Notes
- Repository target version: Odoo 19
- Some modules may originate from older Odoo versions and require compatibility testing
- Install and test modules individually before production deployment
- Prefer Odoo standard workflow whenever possible
