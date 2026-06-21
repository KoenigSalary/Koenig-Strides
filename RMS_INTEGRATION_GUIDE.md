# Koenig-Stride – RMS Integration Guide (updated for Form 12BB / 124)

This guide explains how to register Koenig Stride as an external app inside RMS and what changed in the tax-declaration journey for **Tax Year 2026-27**.

## What changed in this release

The employee declaration flow now includes:

- Form 12BB / 124 wording
- new Act-style section labels with earlier section references
- page-level and item-level Back / Next navigation
- mandatory-field asterisks
- immediate section-to-item refresh in declaration entry
- child declaration reminder and required school detail
- no amount field for Children Declaration
- HRA monthly-rent based annual-rent calculation
- Submit & Lock Declaration under **Declaration by employee**
- Proof Submission shown as an inactive step until **February 2027**
- admin review / reopen actions limited to **Sarika Gupta** login

## Launch options

Your existing launch and SSO options remain valid. No protocol change is required for this tax-form release.

### Email launch

```
https://<your-streamlit-url>/?embed=true&email=praveen.chaudhary@koenig-solutions.com
```

### Signed token launch

```
https://<your-streamlit-url>/?embed=true&token=<JWT>
```

## Suggested employee menu labels

- **Tax Regime**
- **Form 12BB / 124 Declaration**
- **My Declaration**
- **Monthly Allowances**
- **Proof Submission**

## Proof Submission note

Keep the Proof Submission step visible but inactive in employee communications. The in-app message states that it will open in **February 2027** for uploading proofs toward the investment declaration.
