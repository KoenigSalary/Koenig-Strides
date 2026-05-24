# 🤖 Koenig-Stride – RMS Integration Guide

This guide explains how to register **Koenig-Stride** as an external app inside
the Koenig RMS portal (`rms.koenig-solutions.com`) using the
**Automation → Create-Your-Bot** page.

---

## 1. What you'll need

| Item | Source |
|---|---|
| Public URL of Strides | Streamlit Cloud URL (or internal hosting URL) |
| Logo / icon | `assets/koenig_logo.png` in this repo |
| Display name | `Koenig Stride` |
| Description | `AI-assisted payroll, tax, and HR Q&A platform` |
| (Optional) SSO secret | Generate a 32-byte random string, share with RMS dev team |

---

## 2. Three integration modes (pick one)

### Mode A — Simple external link (works today, zero RMS dev effort)

1. In RMS → **Automation → Create-Your-Bot**, fill in:
   * **Bot Name**: `Koenig Stride`
   * **URL**: `https://<your-streamlit-url>/?embed=true`
   * **Icon**: upload `koenig_logo.png`
   * **Visible to roles**: HR, Payroll Admin, All Employees (as desired)
2. Save. The tile appears in the RMS dashboard / sidebar.
3. Clicking it opens Strides; user logs in with their existing Strides
   credentials (admin / `Welcome@123` for first-time employees).

**`?embed=true` is the key flag** — it hides the Streamlit header/footer/menu
so the app looks native inside RMS.

---

### Mode B — Deep-link into a specific panel

Same as Mode A, but append `&panel=<name>` to jump straight to a panel:

| URL fragment | Lands on |
|---|---|
| `&panel=ask-sarika` | Ask Sarika chat |
| `&panel=employee-declaration` | Employee Declaration Portal |
| `&panel=my-tax-snapshot` | My Tax Snapshot |
| `&panel=payroll-tax-engine` | Payroll & Tax Engine (Admin) |
| `&panel=declaration-approval` | Declaration Approval (Admin) |
| `&panel=spoc` | SPOC contact list |

You can register multiple RMS tiles (one per deep-link panel) if needed.

---

### Mode C — Single Sign-On (no second login, recommended for prod)

Strides accepts a **signed JWT** in the `?token=` query param. When RMS injects
this token into the tile URL, the user is auto-logged-in to Strides as their
RMS identity.

#### Setup

1. **Generate a shared secret** (32+ random bytes, e.g.):
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
2. **Store the secret** on both sides:
   * **Strides side** — Streamlit Cloud → *Settings → Secrets*:
     ```toml
     RMS_SSO_SECRET = "paste-the-secret-here"
     ```
   * **RMS side** — store in RMS configuration (ask the RMS dev team to add it
     as a server-side config; **never** expose it to the browser).
3. **RMS mints a JWT** when the user clicks the Strides tile. Use the helper
   `rms_sso_token.py` shipped with this release (see §3 below) as a reference
   implementation in any language.
4. **The tile URL** becomes:
   ```
   https://<your-strides-url>/?embed=true&token=<JWT>
   ```
5. Strides verifies the signature, reads `user`/`name`/`role` from the
   payload, and skips its own login screen.

#### Expected JWT payload

```json
{
  "user": "1086",              // RMS employee ID (any string)
  "name": "Praveen Chaudhary", // displayed in the top-right
  "role": "Admin",             // "Admin" or "Employee"
  "exp": 1747939200            // unix expiry (recommend +5 minutes)
}
```

Algorithm: **HS256** (HMAC-SHA256 with the shared secret).

---

## 3. JWT generation snippets

### Python (RMS side, if it runs Python anywhere)

```python
import jwt, time
secret = "<RMS_SSO_SECRET>"
token = jwt.encode(
    {"user": "1086", "name": "Praveen Chaudhary",
     "role": "Admin", "exp": int(time.time()) + 300},
    secret, algorithm="HS256")
url = f"https://strides.example.com/?embed=true&token={token}"
```

### C# / .NET (matches RMS's ASP.NET stack)

```csharp
using System.IdentityModel.Tokens.Jwt;
using Microsoft.IdentityModel.Tokens;
using System.Security.Claims;
using System.Text;

var secret  = Encoding.UTF8.GetBytes(ConfigurationManager.AppSettings["RMS_SSO_SECRET"]);
var creds   = new SigningCredentials(new SymmetricSecurityKey(secret), SecurityAlgorithms.HmacSha256);
var jwt     = new JwtSecurityToken(
    claims: new[] {
        new Claim("user", currentUser.EmpId),
        new Claim("name", currentUser.FullName),
        new Claim("role", currentUser.IsAdmin ? "Admin" : "Employee")
    },
    expires: DateTime.UtcNow.AddMinutes(5),
    signingCredentials: creds);
var token   = new JwtSecurityTokenHandler().WriteToken(jwt);
var url     = $"https://strides.example.com/?embed=true&token={token}";
```

### Node.js

```js
const jwt = require('jsonwebtoken');
const token = jwt.sign(
  { user: '1086', name: 'Praveen Chaudhary', role: 'Admin' },
  process.env.RMS_SSO_SECRET,
  { algorithm: 'HS256', expiresIn: '5m' });
const url = `https://strides.example.com/?embed=true&token=${token}`;
```

---

## 4. Testing checklist

| # | Test | Expected |
|---|---|---|
| 1 | Open `https://<strides-url>/?embed=true` directly | Login screen, no Streamlit header/footer |
| 2 | Open `https://<strides-url>/?embed=true&panel=ask-sarika` and log in | After login, lands on Ask Sarika |
| 3 | Open with a valid signed token | Auto-logged-in as the token's user, no login screen |
| 4 | Open with an *expired* token | Falls through to login screen (no error pop-up) |
| 5 | Open with a token signed by a *wrong* secret | Falls through to login screen |
| 6 | Open inside an `<iframe>` from RMS | App renders (no `X-Frame-Options` block) |

---

## 5. Security notes

* **Always use HTTPS** for the tile URL — JWTs in the query string are visible
  to anyone who can read the URL.
* **Short expiry** (5 min recommended) — the token is single-use in practice;
  Streamlit creates a session cookie once verified.
* **Never** put `RMS_SSO_SECRET` in the front-end / JavaScript — only the RMS
  server should know it.
* If a token is leaked, **rotate `RMS_SSO_SECRET` on both sides** — all old
  tokens stop working immediately.
* For audit, RMS should log every token mint (who, when, for which tile).

---

## 6. Fallback / disabling SSO

If you only want Mode A or Mode B and **don't** want SSO at all, simply:
* Don't set `RMS_SSO_SECRET` in Streamlit secrets.
* Don't pass a `?token=` param.

The app will behave like a normal Streamlit app and show its own login screen.

---

## 7. Streamlit Cloud and iframes

Streamlit Cloud sends `X-Frame-Options: SAMEORIGIN` by default, which **blocks
iframe embedding from RMS's domain**. Two ways around this:

* **Open in a new tab** (Mode A simplest variant) — set the RMS tile's link
  target to `_blank`. No iframe issues.
* **Self-host Streamlit** behind your own reverse proxy (NGINX / IIS) and
  strip the header. The app code is already iframe-ready.

For most teams, opening in a new tab is the path of least resistance and
matches how RMS treats other "external apps" today.
