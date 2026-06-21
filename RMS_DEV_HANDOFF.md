# RMS → Koenig Stride · Integration Spec (updated for Form 12BB / 124)

This note confirms the RMS handoff behaviour remains simple, while the employee-facing tax declaration experience inside Koenig Stride has been updated for **Form 12BB / 124** for **Tax Year 2026-27**.

## TL;DR

Open Koenig Stride with the Koenig user email in the query string:

```
https://<strides-url>/?email=<user.email>
```

## Employee declaration experience to expect

1. User opens Koenig Stride from RMS
2. User selects **Old Regime** if declaration is required
3. User can move across the flow using **Back / Next** workflow navigation
4. User fills declaration items with immediate section-item refresh
5. User completes child declaration details where applicable
6. User goes to **My Declaration**
7. User completes **Declaration by employee** and clicks **Submit & Lock Declaration**
8. Proof Submission remains visible as an inactive step and is scheduled to open in **February 2027**

## Admin note

In this release, declaration approval / rejection / reopen controls are restricted to **Sarika Gupta** login.

## RMS impact

No RMS-side payload change is required for this release. Existing email SSO / launch behaviour remains valid.
