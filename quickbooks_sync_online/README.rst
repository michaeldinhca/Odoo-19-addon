====================================
Odoo QuickBooks Online Connector PRO
====================================

|

Change Log
##########

|

* 2.1.0 (2026-04-30)
    - [NEW] Added import and export of customers with related addresses (billing, shipping, parent) to maintain contact structure.
    - [FIX] Fixed issue with bill payments import.
    - [FIX] Fixed issue with export product as category.
    - [FIX] Implemented various bug fixes and performance enhancements to improve overall stability and user experience.

* 2.0.0 (2026-04-11)
    - [NEW] Created a dedicated view to easily manage QuickBooks connections.
    - [NEW] Moved connection-related settings from the Settings menu to the new Connections view for user experience.
    - [NEW] Added Odoo configuration file validator.
    - [FIX] Implemented various bug fixes and performance enhancements to improve overall stability and user experience.

* 1.3.0 (2026-03-19)
    - [IMP] Refactored batch export processing to a job-based approach, where each record is handled individually, improving scalability and reliability.
    - [IMP] Centralized exception handling by logging all errors within jobs instead of records, enabling clearer tracking and easier debugging.
    - [IMP] Added automatic product export triggered by changes in cost or price, ensuring data stays up to date.
    - [FIX] Other minor fixes and performance improvements implemented to enhance overall stability.

* 1.2.11 (2025-11-14)
    - Fixed issue with updating products to QuickBooks ("send storable as consumable" option) for Odoo 18.0 and greater.
    - Fixed issue with sending stock to QuickBooks by scheduled action.
    - Fixed pending status after job processing.
    - Fixed tests warnings.

* 1.2.10 (2025-09-26)
    - NEW! Added the ability send products stock to QuickBooks.
    - Fixed issue with manual updating partners to QuickBooks.
    - Fixed issue with taxcode mappings in the multicompany mode.
    - Other minor fixes and improvements regarding non US companies.

* 1.2.9 (2025-08-14)
    - Correction of taxable flag calculation for invoices issued outside the US.

* 1.2.8 (2025-05-19)
    - Migrated to the 75 minorversion of Quickbooks REST API.
    - Fixed and impoved logic for "Get QuickBooks Taxes" function (applicable for US companies).
    - Fixed products batch export.
    - Added "Is QuickBooks Taxable" field with default value on each product in Odoo (for manual adjustment).
    - Send exchange rates for customer invoices, credit notes, vendor bills, refunds, and payments.
    - Other minor fixes and improvements.

* 1.2.7 (2024-12-02)
    - Map the Odoo invoice Reference field to the QuickBooks invoice Memo field.
    - Made several small improvements to enhance overall performance and stability.

* 1.2.6 (2024-10-04)
    - Added the ability to export invoices with the tax included/excluded property for non-US companies (GB, AU, IN, CA).
    - UI improvements for QuickBooks global settings and mappings.
    - Enhanced verbose logging for debugging purposes.
    - Updated the version of the python-quickbooks library to 0.9.10 in dependencies.
    - Each received payment is now registered in a separate background job to avoid impacting other registrations in batch.
    - Other minor fixes and improvements.

* 1.2.5 (2024-03-14)
    - Do not export invoices / payments to QuickBooks that should not be exported (from the past, linked to the company not connected to QuickBooks etc.).
    - When exporting product to the QuickBooks set inventory date to the past to avoid issues with creating invoices with those products.
    - Fixed scheduled action that is exporting invoices & payments to take into account proper companies that are linked to QuickBooks.
    - Updated (and recommended) version of the python-quickbooks library to 0.9.6 in dependencies. Should be manually updated on your server or odoo.sh!

* 1.2.4 (2023-12-29)
    - More detailed description of import/export tasks.
    - Fix for exporting the Bill payments.
    - Fix for running actions on the map objects.

* 1.2.3 (2023-09-21)
    - Fixed the error "Company not defined during ... " during sending requests to QuickBooks API.

* 1.2.2 (2023-03-03)
    - Avoid sending same invoice twice if synchronization happening after payment for the Odoo invoice is registered.
    - Added additional information logs to simply taxes calculation from QuickBooks on sales order and invoice.

* 1.2.1 (2022-11-04)
    - Fix for parsing partner's name during import contacts.

* 1.2.0 (2022-10-28)
    - NEW! Support invoice synchronization in different currencies for the same Customer/Vendor.
    - Added support for product variants synchronization from Odoo to QuickBooks. Every variant is created as new product in QuickBooks with unique name containing attribute name(s) and value(s).
    - Other small fixes and improvements.

* 1.1.3 (2022-10-22)
    - Fix for importing more than 100 accounts by one time.

* 1.1.2 (2022-09-19)
    - Fix for parsing last payment date from Quickbooks module settings.

* 1.1.1 (2022-08-30)
    - Improved functionality of working with Taxes on Invoice for non-US based companies.

* 1.1.0 (2022-08-17)
    - Added customer reference for vendor bill export.

* 1.0.6 (2022-07-25)
    - Added possibility export storable product as consumable.
    - Marking invoice line as taxable in more advanced way. Analyzing tax on the invoice line itself and on the product as well.
    - Fixed adding company name to QuickBooks when it has parent company.

* 1.0.5 (2022-05-05)
    - Additional pop-up messages for clicking button "Get QuickBooks Taxes".

* 1.0.4 (2022-04-26)
    - Improved Getting Taxes from QuickBooks on Sales Orders. Now no need to manually export every product individually, export of all products will be launched recursively.
    - "Get QuickBooks Taxes" functionality is disabled in case "Sync Products" is switched off.
    - Getting QuickBooks Taxes button is adapted to take into account "Sync Products as Categories" setting. In this case it will be needed to set "To QuickBooks Product Type" field on category level to tell QuickBooks if it is Storable or Service Category.
    - Fix impossibility to export invoices from Odoo if taxes are disabled in QuickBooks.
    - Fix error in saving Odoo Settings in case there is no Quickbooks Settings defined (issue with empty Default Stock Valuation Account).

* 1.0.3 (2022-03-15)
    - Fix for error when clicking on "Get QuickBooks Taxes" button after they were manually changed.
    - Improved "Get QuickBooks Tax" functionality for Sales Orders and Invoices (now if product is non-taxable - Taxes will be emptied out on SO/Invoice line).

* 1.0.2 (2022-02-10)
    - Bug fixes and other minor improvements.

* 1.0.1 (2021-10-01)
    - Initial version.
