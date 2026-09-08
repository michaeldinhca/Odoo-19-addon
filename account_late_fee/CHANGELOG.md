# Changelog

All notable changes to this module are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [19.0.1.0.0] - 2026-09-08

### Added
- Initial release: Late Fee Models (percentage/fixed, day/week/month,
  one-time or recurring with a cap), per-installment overdue detection
  respecting multi-installment payment terms, nightly cron generating
  draft fees, manual review/confirm workflow, same-invoice vs. new-invoice
  application (with automatic safe fallback when the original invoice was
  already sent or can't be reset to draft), self-explanatory fee
  descriptions reused across invoice lines and the customer email,
  partner/invoice exemptions, and company settings.
