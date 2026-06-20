# RMS → Koenig Stride · Integration Spec (updated for Form 12BB / 124)

This note confirms the RMS handoff behaviour remains simple, while the employee-facing tax declaration experience inside Koenig Stride has been updated for **Form 12BB / 124** for **Tax Year 2026-27**.

## TL;DR

Open Koenig Stride with the Koenig user email in the query string:

```
https://<strides-url>/?email=<user.email>
```

Strides will continue to auto-identify the user, but the tax declaration module now shows:

- **Form 12BB / 124 — Investment Declaration Form**
- **My Declaration** page with **Submit & Lock Declaration**
- Children declaration guidance inside the declaration journey
- Proof Submission hidden for now in the employee navigation

## RMS impact

No RMS-side payload change is required for this release. Existing email SSO / launch behaviour remains valid.

## Employee declaration experience to expect

1. User opens Koenig Stride from RMS
2. User selects **Old Regime** if declaration is required
3. User fills declaration items using **Next / Back**
4. User completes child declaration details where applicable
5. User goes to **My Declaration**
6. User certifies and clicks **Submit & Lock Declaration**

## Deep-link note

If RMS deep-links to the employee declaration area, update labels in your internal documentation to refer to:

- **Form 12BB / 124 Declaration**
- **My Declaration**

## No change to security expectation

Koenig-only email validation and current launch controls remain unchanged.
