# Koenig Stride — Form 12BB / 124 Update Changelog

This release updates the tax compliance workflow for **Tax Year 2026-27** under the **Income-tax Act, 2025** and **Income-tax Rules, 2026**.

## Implemented in this release

- Form wording updated to **Form 12BB / 124 — Investment Declaration Form**.
- Tax year wording aligned to **Tax Year 2026-27**.
- Section labels now show the **new Act-style reference first** and the **earlier section in brackets**.
- Added **page-level Back / Next workflow navigation** across the employee flow: Tax Regime → Form 12BB / 124 Declaration → My Declaration → Monthly Allowances → Proof Submission.
- Added **item-level Back / Next navigation** in the declaration form.
- Mandatory fields now show an **asterisk (`*`)**.
- **Remarks** remain non-mandatory.
- Fixed **claim-type / section change refresh** so item options update immediately when the section changes.
- **Section 80E / Section 129 (Earlier 80E)** restricted to **Self / Spouse / Children**.
- **HRA annual rent** auto-calculates from **Monthly Rent × 12**.
- **Section 24(b)** updated to **Interest on home loan** with lender name, lender PAN, lender address, and property occupancy.
- **Children Declaration** is highlighted; child count and school / institution name are required.
- **Children Declaration amount entry removed**.
- **Submit & Lock Declaration** now uses the heading **Declaration by employee**.
- **Proof Submission** remains visible as an inactive step with the message that it will open in **February 2027**.
- Removed monthly allowance options: **Skill Development and Certification Programs** and **Other approved expenses as per company policy**.
- Monthly allowance claims are editable in more statuses, including submitted claims before review begins.
- Admin reports now support **Excel export** and **CSV export**.
- Admin approval / rejection / reopen controls are restricted to **Sarika Gupta** login in this release.

## Certification text

> I, .............. son/daughter of ...................... do hereby certify that the information given in the form is complete and correct.

## Updated files

- `compliance_module.py`
- `CHANGELOG_QUICKWINS.md`
- `RMS_DEV_HANDOFF.md`
- `RMS_INTEGRATION_GUIDE.md`
- `rms_sso_token.py`
- `requirements.txt`
- `keep-alive.yml`
