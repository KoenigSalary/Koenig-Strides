# RMS → Koenig Stride · Integration Spec (for the RMS dev team)

This document confirms what your RMS portal needs to do when a user clicks the
**Koenig Stride** tile. It matches your existing example:

> `https://goodies-management-portal-6493.taskade.app?email=aditya.sharma@koenig-solutions.com`

---

## TL;DR

Open Strides with the user's Koenig email in the query string:

```
https://<strides-url>/?email=<user.email>
```

That's it. No token, no signature, no extra headers. Strides will:

1. Read the email
2. Verify it ends with `@koenig-solutions.com` (else reject)
3. Auto-create the user on first visit
4. Log them in
5. Strip the email from the address bar after login
6. Record the entry in Strides' audit log

---

## URL parameters

| Param | Required | Purpose |
|---|---|---|
| `email` | **yes** | Koenig email address — used as identity (must end with `@koenig-solutions.com`) |
| `embed` | optional | Set to `true` to hide Streamlit chrome (header/footer/menu). Recommended for iframe use. |
| `panel` | optional | Deep-link to a specific panel after login. Slugs: `ask-strides`, `spoc`, `user-management`, `knowledge-base`, `question-analytics`, `admin-analytics`. |
| `name` | optional | Display name. If omitted, Strides derives it from the email (`aditya.sharma` → "Aditya Sharma"). |
| `role` | optional | `Employee` (default) or `Admin`. Admins can also be configured server-side via `RMS_ADMIN_EMAILS` secret without RMS sending this param. |

---

## Examples

```text
# Simplest — what you described
https://<strides-url>/?email=aditya.sharma@koenig-solutions.com

# Recommended for embedding inside RMS
https://<strides-url>/?email=aditya.sharma@koenig-solutions.com&embed=true

# Deep-link straight to Ask Strides
https://<strides-url>/?email=aditya.sharma@koenig-solutions.com&panel=ask-strides

# With explicit name & admin role
https://<strides-url>/?email=praveen.chaudhary@koenig-solutions.com&name=Praveen%20Chaudhary&role=Admin
```

---

## What Strides does on its side

| When | Behaviour |
|---|---|
| `?email=foo@koenig-solutions.com` | ✅ Auto-login as that user |
| `?email=foo@gmail.com` | ❌ Rejected. User sees the "open via RMS" gate |
| No `?email` and no `?token` | Shows "Please open Strides from the RMS portal" page |
| `?admin=true` | Shows the admin login form (escape hatch for emergencies) |
| Any URL params: `?email`, `?name`, `?role`, `?token`, `?user` | Stripped from the address bar after login completes |

Every successful entry is logged to `audit_log` (action = `SSO_LOGIN`,
target_id = email). Every rejected entry is logged as `SSO_REJECTED`.

---

## On your side

Just construct the URL when the user clicks the tile. No code changes needed
beyond what you've already planned. The minimal C# example:

```csharp
var stridesUrl = $"https://<your-strides-url>/?email={HttpUtility.UrlEncode(currentUser.Email)}";
Response.Redirect(stridesUrl);
```

If you want the iframe-friendly variant:

```csharp
var stridesUrl = $"https://<your-strides-url>/?email={HttpUtility.UrlEncode(currentUser.Email)}&embed=true";
```

---

## Security note

This setup trusts that **only the RMS portal can launch Strides URLs in
practice**. If the Streamlit URL is shared/known outside RMS, anyone who knows
a colleague's email could impersonate them by typing the URL manually. Two
mitigations to keep in mind:

1. **Don't publicise the Streamlit URL** — only expose it through the RMS tile.
2. **When ready, upgrade to signed tokens** (`?token=<JWT>`). Strides already
   supports this path; see `RMS_INTEGRATION_GUIDE.md` for the spec and
   `rms_sso_token.py` for a reference implementation.

For pilot / small team use the plain `?email=` flow is acceptable. For
production roll-out to many employees, plan to upgrade to JWT within
30 days.
