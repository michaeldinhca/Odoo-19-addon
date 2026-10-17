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
- `survey_theme`

### Purpose
- `survey_file_upload`: adds a "File Upload" question type to Survey, with
  per-question size/multi-file limits, AJAX (non-blocking) upload, and a
  real upload progress bar
- `survey_theme`: restyles the Survey taking flow (mobile-first, company
  logo, long-text-safe choice options) with a per-survey on/off toggle
- Clean-room builds (see each module's `CLAUDE.md`) — not ports of any
  third-party module


---

## Technical / Server Action Addons
Modules that extend Odoo's technical layer (server actions, automation rules,
scheduled actions).

### Modules
- `server_action_requests`

### Purpose
- `server_action_requests`: makes `requests` available inside Python code of
  server actions, automation rules and scheduled actions
- Needed after moving a database from Odoo Online to odoo.sh or on-premise:
  Odoo Online's SaaS build provides `requests` to server action code, the
  stable 19.0 build does not, so migrated actions fail with
  `name 'requests' is not defined`
- Exposes a restricted wrapper only (HTTP verbs `get`, `post`, `put`,
  `patch`, `delete`, `head`, `request` plus the exception classes); sessions,
  adapters and internals stay blocked by the sandbox
- No models, views or data; does nothing if the Odoo build already provides
  `requests`; uninstall to revert
- Security: only users who can edit server action code (Settings /
  Administration with developer mode) can use it. Keep API keys in System
  Parameters, not in the action code


---

## Notes
- Repository target version: Odoo 19
- Some modules may originate from older Odoo versions and require compatibility testing
- Install and test modules individually before production deployment
- Prefer Odoo standard workflow whenever possible
