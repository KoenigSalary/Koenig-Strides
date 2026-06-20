# 🤖 Koenig-Stride – RMS Integration Guide (updated for Form 12BB / 124)

This guide explains how to register **Koenig Stride** as an external app inside RMS and what changed in the tax-declaration journey for **Tax Year 2026-27**.

## What changed in this release

The employee declaration flow now uses **Form 12BB / 124** wording and includes:

- new Act-style section labels with earlier section references
- Next / Back navigation
- mandatory-field asterisks
- child declaration reminder and required school detail
- HRA monthly-rent based annual-rent calculation
- Submit & Lock Declaration on **My Declaration**
- Proof Submission hidden for now

## RMS launch modes

Your existing launch and SSO options remain valid. No protocol change is required for this tax-form release.

### Mode A — Simple external link

```
https://<your-streamlit-url>/?embed=true
```

### Mode B — Email launch

```
https://<your-streamlit-url>/?embed=true&email=praveen.chaudhary@koenig-solutions.com
```

### Mode C — Signed token launch

```
https://<your-streamlit-url>/?embed=true&token=<JWT>
```

## Suggested RMS labels

For employee-facing menus or tiles, use these names:

- **Form 12BB / 124 Declaration**
- **My Declaration**
- **Monthly Allowances**

## Important employee-flow note

Employees who need to claim **Children Education Allowance** should be guided to add the dedicated child declaration item and complete child-count and school details before using **Submit & Lock Declaration**.

## Proof Submission

The Proof Submission page is intentionally hidden in this release. RMS should not expose or document it for employee use right now.

## SSO reminder

Only `@koenig-solutions.com` identities should be allowed into Koenig Stride. Continue using your existing email or token-based launch setup.
