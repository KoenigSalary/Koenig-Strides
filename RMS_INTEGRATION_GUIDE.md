# 🤖 Koenig-Stride – RMS Integration Guide (Email SSO)

This guide explains how to register **Koenig-Stride** as an external app inside
the Koenig RMS portal (`rms.koenig-solutions.com`) using the
**Automation → Create-Your-Bot** page, and how to enable single sign-on so the
employee never has to log in to Strides separately.

---

## 1. What you'll need

| Item | Source |
|---|---|
| Public URL of Strides | Streamlit Cloud URL (or internal hosting URL) |
| Logo / icon | `assets/koenig_logo.png` in this repo |
| Display name | `Koenig Stride` |
| Description | `AI-assisted payroll, tax, and HR Q&A platform` |
| (For SSO) Shared secret | Generate a 32-byte random string, share with RMS dev team |

---

## 2. Three integration modes (pick one)

### Mode A — Simple external link (works today, zero RMS dev effort)

1. In RMS → **Automation → Create-Your-Bot**, fill in:
   * **Bot Name**: `Koenig Stride`
   * **URL**: `https://<your-streamlit-url>/?embed=true`
   * **Icon**: upload `koenig_logo.png`
   * **Visible to roles**: HR, Payroll Admin, All Employees (as desired)
2. Save. The tile appears in the RMS dashboard / sidebar.
3. Clicking it opens Strides; user logs in with their Employee ID or via
   the legacy admin login.

**`?embed=true` is the key flag** — it hides the Streamlit header/footer/menu
so the app looks native inside RMS.

---

### Mode B — Deep-link into a specific panel

Same as Mode A, but append `&panel=<name>` to jump straight to a panel:

| URL fragment | Lands on |
|---|---|
| `&panel=ask-strides` | Ask Strides chat |
| `&panel=employee-declaration` | Employee Declaration Portal |
| `&panel=my-tax-snapshot` | My Tax Snapshot |
| `&panel=payroll-tax-engine` | Payroll & Tax Engine (Admin) |
| `&panel=declaration-approval` | Declaration Approval (Admin) |
| `&panel=question-analytics` | Question Analytics (Admin) |
| `&panel=admin-analytics` | Admin Analytics (Admin) |
| `&panel=spoc` | SPOC contact list |

You can register multiple RMS tiles (one per deep-link panel) if needed.

---

### Mode C — Single Sign-On via Email (recommended, no second login) ⭐

Strides accepts a **signed JWT** in the `?token=` query param. When RMS injects
this token into the tile URL, the user is auto-logged-in to Strides as their
RMS identity — using their Koenig email address.

**Strides automatically does the following for each new email:**

1. Verifies the JWT signature using `RMS_SSO_SECRET`
2. Confirms the email ends with `@koenig-solutions.com` (others are rejected)
3. Derives an internal user ID from the email
   (e.g. `praveen.chaudhary@koenig-solutions.com` → `praveen.chaudhary`)
4. Looks up Employee Master by email — if a match exists, it links the SSO
   identity to the existing payroll / tax / declaration records
5. Creates a users.csv row on first login (no password needed — SSO only)
6. Skips the login screen entirely

#### Setup

1. **Generate a shared secret** (32+ random bytes):
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
2. **Store the secret on both sides**:
   * **Strides side** — Streamlit Cloud → *Settings → Secrets*:
     ```toml
     RMS_SSO_SECRET = "paste-the-secret-here"

     # Optional: list of emails that should get Admin role on SSO login.
     # Comma- or whitespace-separated.
     RMS_ADMIN_EMAILS = "tax@koenig-solutions.com, praveen.chaudhary@koenig-solutions.com"
     ```
   * **RMS side** — store in RMS server-side configuration. **Never** expose
     it to the browser / JavaScript.
3. **RMS mints a JWT** when the user clicks the Strides tile (see §3 below
   for code snippets in Python, C# and Node.js).
4. **The tile URL** becomes:
   ```
   https://<your-strides-url>/?embed=true&token=<JWT>
   ```
5. Strides verifies the signature, reads `email` / `name` / `role` from the
   payload, links to the Employee Master, and logs the user in automatically.

#### Expected JWT payload

```json
{
  "email": "praveen.chaudhary@koenig-solutions.com",  // REQUIRED (Koenig email)
  "name":  "Praveen Chaudhary",                       // optional, recommended
  "role":  "Admin",                                   // optional ("Admin" | "Employee")
  "exp":   1747939200                                 // unix expiry (recommend +5 min)
}
```

Algorithm: **HS256** (HMAC-SHA256 with the shared secret).

#### Role resolution

Strides decides the role for an SSO user in this order:

1. If the token contains `"role": "Admin"` → Admin
2. Else if the email is in `RMS_ADMIN_EMAILS` (Streamlit secrets) → Admin
3. Otherwise → Employee

This means RMS can simply send `role` for known admins, OR you can manage the
admin list entirely on the Strides side via secrets — whichever is easier.

---

## 3. JWT generation snippets

### Python (RMS side, if it runs Python anywhere)

```python
import jwt, time
secret = "<RMS_SSO_SECRET>"
token = jwt.encode(
    {"email": "praveen.chaudhary@koenig-solutions.com",
     "name": "Praveen Chaudhary",
     "role": "Admin",
     "exp": int(time.time()) + 300},
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
        new Claim("email", currentUser.Email),       // praveen.chaudhary@koenig-solutions.com
        new Claim("name",  currentUser.FullName),
        new Claim("role",  currentUser.IsAdmin ? "Admin" : "Employee")
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
  { email: 'praveen.chaudhary@koenig-solutions.com',
    name: 'Praveen Chaudhary', role: 'Admin' },
  process.env.RMS_SSO_SECRET,
  { algorithm: 'HS256', expiresIn: '5m' });
const url = `https://strides.example.com/?embed=true&token=${token}`;
```

### Quick test from the command line

```bash
python3 rms_sso_token.py \
    --secret "your-shared-secret" \
    --email "praveen.chaudhary@koenig-solutions.com" \
    --name "Praveen Chaudhary" --role Admin \
    --base-url "https://your-strides-url" \
    --panel "my-tax-snapshot"
```

This prints a ready-to-use URL you can paste into a browser to verify SSO
end-to-end.

---

## 4. Plain-text fallback (dev/pilot only — NOT for production)

For pilot testing without setting up signed tokens, Strides can also accept a
plain `?email=` query param:

```
https://<your-strides-url>/?embed=true&email=praveen.chaudhary@koenig-solutions.com&name=Praveen%20Chaudhary&role=Admin
```

This is **disabled by default**. To enable for pilot:

```toml
# in Streamlit secrets
RMS_ALLOW_PLAIN_SSO = "true"
```

**Strongly discourage in production** — anyone who guesses an employee email
can log in as them. Use signed tokens (Mode C) for real deployments.

---

## 5. Testing checklist

| # | Test | Expected |
|---|---|---|
| 1 | Open `https://<strides-url>/?embed=true` directly | Login screen, no Streamlit header/footer |
| 2 | Open with valid token containing your Koenig email | Auto-logged-in as that employee, no login screen |
| 3 | Open with valid token but email `attacker@gmail.com` | Falls through to login screen (token rejected) |
| 4 | Open with a token signed by a *wrong* secret | Falls through to login screen |
| 5 | Open with an *expired* token | Falls through to login screen |
| 6 | Open with `&panel=my-tax-snapshot` plus a valid token | Auto-logged in and lands on the My Tax Snapshot panel |
| 7 | Open inside an `<iframe>` from RMS | App renders (no `X-Frame-Options` block) |
| 8 | First-time SSO user (not in users.csv yet) | Auto-created, linked to Employee Master if email matches |

---

## 6. Security notes

* **Always use HTTPS** for the tile URL — JWTs in the query string are visible
  to anyone who can read the URL.
* **Short expiry** (5 min recommended) — the token is single-use in practice;
  Streamlit creates a session cookie once verified.
* **Never** put `RMS_SSO_SECRET` in the front-end / JavaScript — only the RMS
  server should know it.
* **Only `@koenig-solutions.com` emails are accepted.** Other domains, even
  with a valid signature, are rejected.
* If a token is leaked, **rotate `RMS_SSO_SECRET` on both sides** — all old
  tokens stop working immediately.
* For audit, RMS should log every token mint (who, when, for which tile).
  Strides logs every SSO_LOGIN / SSO_REJECTED event in its own audit log.

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
