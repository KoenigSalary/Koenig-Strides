# Koenig Stride — Form 12BB / 124 Update Changelog

This release updates the **tax compliance workflow files** for **Tax Year 2026-27** under the **Income-tax Act, 2025** and **Income-tax Rules, 2026**.

## ✅ Implemented in this release

- Declaration wording updated to **Form 12BB / 124 — Investment Declaration Form**.
- Tax year wording aligned to **Tax Year 2026-27**.
- Section labels now show the **new Act-style reference first** and the **earlier section in brackets** for employee clarity.
- Added **Next / Back navigation** inside the declaration item workflow.
- Mandatory fields now show an **asterisk (`*`)**.
- **Remarks** kept non-mandatory.
- Fixed **Item** selection refresh when the user changes the claim type / section.
- **Section 80E** flow restricted to **Self / Spouse / Children** declarations.
- **HRA annual rent** now auto-calculates from **Monthly rent × 12**.
- **Section 24(b)** flow renamed to **Interest on home loan** and now captures lender name, lender PAN, lender address, and whether the property is self occupied or rented.
- **Proof Submission** panel is intentionally hidden for now, while backend support remains in place.
- Removed monthly allowance options: **Skill Development and Certification Programs** and **Other approved expenses as per company policy**.
- Monthly allowance claims are now **editable even after submission** until review begins.
- Added **Children Declaration** highlight so employees know to fill the child count and school / institution details.
- Added **Submit & Lock Declaration** with certification text on **My Declaration**.

## 🧾 Certification format implemented

> I, .............. son/daughter of ...................... do hereby certify that the information given in the form is complete and correct.

## 📦 Updated files

- `compliance_module.py`
- `CHANGELOG_QUICKWINS.md`
- `RMS_DEV_HANDOFF.md`
- `RMS_INTEGRATION_GUIDE.md`
- `rms_sso_token.py`
- `requirements.txt`
- `keep-alive.yml`
