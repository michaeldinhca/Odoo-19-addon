# Survey Signature

Adds a genuinely new **Signature** question type to Odoo Survey, so a
respondent can sign directly on the survey page as their answer - using
Odoo's own signature-pad widget, the same one used to sign a quotation or
invoice on the customer portal.

![status](https://img.shields.io/badge/status-v1-orange)
![odoo](https://img.shields.io/badge/Odoo-19.0%20Community-714B67)
![license](https://img.shields.io/badge/license-LGPL--3.0-blue)

## Features (v1.0.0)

- **New "Signature" question type**, selectable alongside the stock types
  (Text, Choice, Matrix, etc.).
- **Reuses Odoo's own core `NameAndSignature` component** - not a
  reimplementation. Respondents get the familiar "Auto / Draw / Load" tabs:
  type a name for an auto-generated cursive signature, draw with mouse or
  touch, or upload an image of a signature. See [`CLAUDE.md`](CLAUDE.md) for
  how this is wired in without copying any of that component's code.
- **Mandatory Answer** works like any other question type - an empty
  signature on a required question blocks submission with the question's
  own configured error message.
- **Results & backend**: the signature image and signer name are shown on
  the survey's results page for each respondent, and on the response's own
  Answers tab in the backend.

## Requirements

- Odoo **19.0 Community** (or Enterprise - no Enterprise-only APIs used).
- Standard app: `survey` (declared as a dependency, installed automatically).
- Pairs well with `survey_theme` (same repo) - the signature widget inherits
  that module's card/shape styling automatically when both are installed,
  no extra configuration.

## Installation

1. Copy (or `git clone`) this repository's `survey_signature/` folder into
   your Odoo `addons` path.
2. Restart the Odoo server, or enable Developer Mode and go to
   **Apps → Update Apps List**.
3. Search for **Survey Signature** and click **Install**.
4. Open a survey → add a question → set **Question Type** to **Signature**.

## License

LGPL-3.0 - see [`LICENSE`](LICENSE).

## Author

NGYN Solutions Inc. — https://ngynsolutions.com
