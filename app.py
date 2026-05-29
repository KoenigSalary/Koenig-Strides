import streamlit as st
import pandas as pd
from pathlib import Path
import base64
import hashlib
import html
import io
import re
import uuid
from datetime import datetime
import sqlite3
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    from openai import OpenAI
    AI_AVAILABLE = True
except Exception:
    AI_AVAILABLE = False

# =====================================================
# KOENIG STRIDE - POLISHED LOGIN UI + RESPONSIVE
# Streamlit-native layout, no broken HTML wrappers
# =====================================================

st.set_page_config(
    page_title="Koenig Stride",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =====================================================
# RMS EMBED / SSO LAYER
# Allows Koenig-Stride to be embedded inside RMS as an external app.
# Supports query params:
#   ?embed=true                   → hide Streamlit chrome (header/footer/menu)
#   ?panel=ask-strides            → deep-link to a specific panel after login
#                                   (legacy alias ?panel=ask-sarika still works)
#   ?email=<koenig email>         → RMS-issued email identity (plain, dev mode)
#   ?user=<emp_id>&role=<r>       → legacy RMS-issued ID identity (plain, dev mode)
#   ?token=<signed_jwt>           → RMS-issued signed token (prod mode, preferred)
# In prod, the token is verified using RMS_SSO_SECRET in st.secrets.
# Tokens MUST contain a `email` (preferred) or `user` claim, optional `name`/`role`.
# Only `@koenig-solutions.com` email addresses are accepted.
# If verification fails or token is absent, user falls through to normal login.
# =====================================================

ALLOWED_SSO_DOMAIN = "@koenig-solutions.com"

try:
    _qp = dict(st.query_params)
except Exception:
    try:
        _qp = {k: (v[0] if isinstance(v, list) and v else v) for k, v in st.experimental_get_query_params().items()}
    except Exception:
        _qp = {}

EMBED_MODE = str(_qp.get("embed", "")).lower() in ("1", "true", "yes")
RMS_USER_PARAM = str(_qp.get("user", "")).strip()
RMS_EMAIL_PARAM = str(_qp.get("email", "")).strip()
RMS_NAME_PARAM = str(_qp.get("name", "")).strip()
RMS_ROLE_PARAM = str(_qp.get("role", "")).strip()
RMS_TOKEN_PARAM = str(_qp.get("token", "")).strip()
DEEP_LINK_PANEL = str(_qp.get("panel", "")).strip()
# Admin escape-hatch: open /?admin=true to expose the admin login form.
# Without this flag, the login screen is hidden (employees come via RMS only).
ADMIN_OVERRIDE = str(_qp.get("admin", "")).lower() in ("1", "true", "yes")


def _is_allowed_koenig_email(email):
    """True if the email is non-empty and ends with @koenig-solutions.com."""
    if not email:
        return False
    email = email.strip().lower()
    return email.endswith(ALLOWED_SSO_DOMAIN) and "@" in email and len(email) > len(ALLOWED_SSO_DOMAIN)


def _employee_id_from_email(email):
    """praveen.chaudhary@koenig-solutions.com → 'praveen.chaudhary'.
    Returns lower-case localpart, safe to use as a Strides user_id."""
    if not email or "@" not in email:
        return ""
    return email.split("@", 1)[0].strip().lower()


def _name_from_email(email):
    """Derive a display name from an email.
    praveen.chaudhary@koenig-solutions.com → 'Praveen Chaudhary'."""
    local = _employee_id_from_email(email)
    if not local:
        return ""
    parts = [p for p in local.replace("_", ".").replace("-", ".").split(".") if p]
    return " ".join(p.capitalize() for p in parts) if parts else local


def _is_admin_email(email):
    """Check if an email is in the configured RMS_ADMIN_EMAILS list.
    Accepts comma- or whitespace-separated emails in st.secrets."""
    if not email:
        return False
    try:
        raw = st.secrets.get("RMS_ADMIN_EMAILS", "")
    except Exception:
        raw = ""
    if not raw:
        return False
    if isinstance(raw, (list, tuple)):
        admin_set = {str(e).strip().lower() for e in raw if e}
    else:
        admin_set = {e.strip().lower() for e in re.split(r"[,\s]+", str(raw)) if e.strip()}
    return email.strip().lower() in admin_set


def _verify_rms_sso_token(token):
    """Verify an RMS-issued JWT and return the payload, or None if invalid.

    Expected payload shape:
        {"email": "<koenig email>",   # preferred
         "user":  "<emp_id>",         # legacy, optional
         "name":  "<full_name>",
         "role":  "Employee|Admin",
         "exp":   <unix_ts>}

    Requires RMS_SSO_SECRET in st.secrets (HMAC-SHA256 shared secret with RMS).
    PyJWT is preferred; if not installed, a minimal HMAC verification fallback
    keeps the app working without an extra dependency.
    """
    if not token:
        return None
    try:
        secret = st.secrets.get("RMS_SSO_SECRET", "")
    except Exception:
        secret = ""
    if not secret:
        return None
    try:
        try:
            import jwt  # type: ignore
            return jwt.decode(token, secret, algorithms=["HS256"])
        except ImportError:
            # Minimal fallback: HS256 JWT verification using only stdlib
            import hmac, json as _json
            parts = token.split(".")
            if len(parts) != 3:
                return None
            header_b64, payload_b64, sig_b64 = parts

            def _b64url_decode(s):
                pad = "=" * (-len(s) % 4)
                return base64.urlsafe_b64decode(s + pad)

            signing_input = f"{header_b64}.{payload_b64}".encode()
            expected_sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
            actual_sig = _b64url_decode(sig_b64)
            if not hmac.compare_digest(expected_sig, actual_sig):
                return None
            payload = _json.loads(_b64url_decode(payload_b64))
            # Expiry check
            if "exp" in payload:
                import time as _time
                if _time.time() > float(payload["exp"]):
                    return None
            return payload
    except Exception:
        return None


# Hide Streamlit chrome when embedded
if EMBED_MODE:
    st.markdown(
        """
        <style>
            #MainMenu, footer, header {visibility: hidden !important;}
            .stApp [data-testid="stToolbar"] {display: none !important;}
            .stApp [data-testid="stDecoration"] {display: none !important;}
            .block-container {padding-top: 1rem !important;}
        </style>
        """,
        unsafe_allow_html=True,
    )

BASE_DIR = Path(__file__).parent
EXCEL_PATH = BASE_DIR / "knowledge" / "Koenig_VoiceBot_FAQ_Master.xlsx"
LOGO_PATH = BASE_DIR / "assets" / "koenig_logo.png"
SARIKA_PATH = BASE_DIR / "assets" / "sarika.png"
USERS_PATH = BASE_DIR / "users.csv"
DB_PATH = BASE_DIR / "koenig_stride.db"


DEFAULT_EMPLOYEE_PASSWORD = "Welcome@123"

# Admin password is loaded from Streamlit Secrets (recommended) and falls back
# to a built-in default only for first-time bootstrap. Set ADMIN_PASSWORD in
# Streamlit Cloud → Settings → Secrets so the source code never ships a secret.
try:
    DEFAULT_ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "admin123")
except Exception:
    DEFAULT_ADMIN_PASSWORD = "admin123"

# When True, typing the default password Welcome@123 will auto-reset any
# numeric employee account back to that password. Convenient for pilots, but
# unsafe for production. Toggle off via st.secrets["ALLOW_DEFAULT_PWD_RESET"]=false.
try:
    ALLOW_DEFAULT_PWD_RESET = bool(st.secrets.get("ALLOW_DEFAULT_PWD_RESET", False))
except Exception:
    ALLOW_DEFAULT_PWD_RESET = False

# =====================================================
# IMAGE HELPERS
# =====================================================

def image_to_base64(path):
    if path.exists():
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""

LOGO_B64 = image_to_base64(LOGO_PATH)
SARIKA_B64 = image_to_base64(SARIKA_PATH)

def img_html(b64, css_class="", style=""):
    if not b64:
        return ""
    return f"<img class='{css_class}' style='{style}' src='data:image/png;base64,{b64}'>"

# =====================================================
# CSS
# =====================================================

st.markdown("""
<style>
:root {
    --blue-darker:#04123d;
    --blue-dark:#061b55;
    --blue-mid:#0b3ba7;
    --blue:#155be8;
    --blue-light:#1f6bff;
    --bg:#eef3fb;
    --card:#ffffff;
    --border:#dbe3ef;
    --text:#111827;
    --muted:#64748b;
}

html, body, [class*="css"] {
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
    -webkit-font-smoothing: antialiased;
}

[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at 8% 12%, rgba(21,91,232,.08), transparent 35%),
        radial-gradient(circle at 92% 88%, rgba(6,27,85,.07), transparent 40%),
        var(--bg);
}

.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 1320px;
}

#MainMenu, footer, header {
    visibility:hidden;
}

[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[data-testid="stHeaderActionElements"],
.stDeployButton,
.viewerBadge_container__1QSob,
.viewerBadge_link__qRIco,
.viewerBadge_text__1JaDK,
.styles_terminalButton__JBj5Y,
a[href*="streamlit.io/cloud"],
a[href*="share.streamlit.io"],
footer,
footer a {
    display:none !important;
    visibility:hidden !important;
}

/* Suppress the floating 'Manage app' button (owner-only, but cleaner for everyone) */
#root > div:nth-child(1) > div.withScreencast > div > div > footer { display: none !important; }

/* ---------- LOGIN PAGE ---------- */

/* Mark the login page body so we can scope styles. */
body.is-login-page [data-testid="stHeader"] { display:none; }

.logo-img {
    width:220px;
    max-width:100%;
    height:auto;
}

/* The dark login card is the FIRST column on the login page.
   We target the column container directly so Streamlit widgets render
   INSIDE the styled card (instead of escaping a raw <div>). */
body.is-login-page [data-testid="column"]:first-child {
    background:
        radial-gradient(circle at 18% 6%, rgba(255,255,255,.10), transparent 38%),
        radial-gradient(circle at 88% 92%, rgba(255,255,255,.08), transparent 40%),
        linear-gradient(160deg,#04123d 0%,#06339a 55%,#0a52d6 100%);
    color:white;
    padding:42px 38px !important;
    border-radius:24px;
    box-shadow:0 22px 55px rgba(15,23,42,.22);
    position:relative;
    overflow:hidden;
}

body.is-login-page [data-testid="column"]:first-child::before {
    content:"";
    position:absolute;
    top:-60px; right:-60px;
    width:220px; height:220px;
    background:radial-gradient(circle, rgba(255,255,255,.10), transparent 70%);
    border-radius:50%;
    pointer-events:none;
    z-index:0;
}

body.is-login-page [data-testid="column"]:first-child > div {
    position:relative;
    z-index:1;
}

body.is-login-page [data-testid="column"]:first-child h1,
body.is-login-page [data-testid="column"]:first-child h2,
body.is-login-page [data-testid="column"]:first-child h3,
body.is-login-page [data-testid="column"]:first-child label,
body.is-login-page [data-testid="column"]:first-child p,
body.is-login-page [data-testid="column"]:first-child span,
body.is-login-page [data-testid="column"]:first-child div {
    color:white;
}

/* Force text input labels white inside the dark login card */
body.is-login-page [data-testid="column"]:first-child div[data-testid="stTextInput"] label p,
body.is-login-page [data-testid="column"]:first-child div[data-testid="stRadio"] label p {
    color:white !important;
    font-weight:700 !important;
    font-size:14px !important;
    letter-spacing:.2px;
}

/* Inputs stay light so text remains readable */
div[data-testid="stTextInput"] input {
    border-radius:12px;
    min-height:48px;
    border:1px solid #d6deec;
    background:#ffffff;
    color:#0f172a;
    font-size:15px;
    padding:10px 14px;
    transition:border .15s ease, box-shadow .15s ease;
}

div[data-testid="stTextInput"] input:focus {
    border-color:var(--blue) !important;
    box-shadow:0 0 0 3px rgba(21,91,232,.18) !important;
    outline:none !important;
}

/* Radio button look inside the dark card */
body.is-login-page [data-testid="column"]:first-child div[data-testid="stRadio"] > div {
    gap: 18px !important;
}

body.is-login-page [data-testid="column"]:first-child div[role="radiogroup"] label {
    background:rgba(255,255,255,.08);
    border:1px solid rgba(255,255,255,.22);
    border-radius:10px;
    padding:8px 14px;
}

body.is-login-page [data-testid="column"]:first-child div[role="radiogroup"] label:hover {
    background:rgba(255,255,255,.16);
}

.login-divider {
    border-top:1px solid rgba(255,255,255,.22);
    border-bottom:1px solid rgba(255,255,255,.22);
    padding:24px 0;
    margin:8px 0 28px 0;
}

.login-brand-row {
    display:flex;
    align-items:center;
    gap:14px;
}

.login-bot-icon {
    background:linear-gradient(135deg,#1f6bff,#155be8);
    color:white;
    height:46px;
    width:46px;
    min-width:46px;
    border-radius:50%;
    display:inline-flex;
    align-items:center;
    justify-content:center;
    font-weight:900;
    font-size:22px;
    box-shadow:0 6px 18px rgba(21,91,232,.45);
}

.login-card-title {
    color:white;
    font-size:30px;
    margin:0;
    letter-spacing:-0.3px;
    font-weight:900;
}

.login-tagline {
    margin:14px 0 0 60px;
    font-weight:600;
    font-size:14px;
    opacity:.92;
    letter-spacing:.2px;
    color:white;
}

.login-help {
    border-top:1px solid rgba(255,255,255,.22);
    padding-top:24px;
    margin-top:28px;
    text-align:center;
    font-size:14px;
    line-height:1.6;
    color:white;
}

/* ---------- BRAND (right side / header) ---------- */

.brand-row {
    display:flex;
    align-items:center;
    gap:14px;
}

.bot-icon {
    background:linear-gradient(135deg,#155be8,#0b3ba7);
    color:white;
    height:50px;
    width:50px;
    min-width:50px;
    border-radius:50%;
    display:inline-flex;
    align-items:center;
    justify-content:center;
    font-weight:900;
    font-size:24px;
    box-shadow:0 6px 16px rgba(21,91,232,.35);
}

.brand-title {
    font-size:38px;
    font-weight:900;
    color:var(--text);
    margin:0;
    letter-spacing:-0.5px;
}

.brand-subtitle {
    margin-left:64px;
    margin-top:4px;
    color:#334155;
    font-size:15px;
    font-weight:500;
}

.user-pill {
    background:white;
    border:1px solid var(--border);
    padding:12px 18px;
    border-radius:18px;
    box-shadow:0 8px 24px rgba(15,23,42,.06);
    font-weight:800;
}

/* ---------- HERO ---------- */

.hero {
    background:
        radial-gradient(circle at 86% 42%, rgba(255,255,255,.18), transparent 32%),
        linear-gradient(135deg,#04123d 0%,#0a3aae 55%,#155be8 100%);
    color:white;
    padding:46px 52px;
    border-radius:24px;
    box-shadow:0 16px 40px rgba(15,23,42,.18);
    margin-bottom:22px;
}

.hero h2 {
    font-size:34px;
    margin:0 0 14px 0;
    color:white;
    font-weight:900;
    letter-spacing:-0.4px;
}

.hero p {
    color:white;
    font-size:18px;
    line-height:1.55;
    margin:0;
    opacity:.95;
}

/* Hero on the LOGIN page is slightly different */
.login-hero {
    margin-top: 6px;
}

/* ---------- CARDS ---------- */

.card {
    background:white;
    border:1px solid var(--border);
    border-radius:22px;
    box-shadow:0 14px 35px rgba(15,23,42,.08);
    padding:24px;
    margin-bottom:20px;
}

.avatar-img {
    width:150px;
    height:150px;
    border-radius:50%;
    object-fit:cover;
    border:4px solid #1471d8;
    box-shadow:0 8px 24px rgba(15,23,42,.16);
}

.online {
    color:#15803d;
    font-weight:800;
}

.side-item {
    padding:14px 16px;
    border-radius:14px;
    font-weight:800;
    margin:8px 0;
}

.side-item-active {
    background:#eaf2ff;
    color:#0b55d9;
}

.primary-start button {
    background:linear-gradient(90deg,#0b55d9,#155be8) !important;
    color:white !important;
    border:none !important;
    border-radius:14px !important;
    min-height:58px !important;
    font-size:18px !important;
    box-shadow:0 10px 24px rgba(21,91,232,.28) !important;
}

.stButton > button {
    border-radius:10px !important;
    font-weight:700 !important;
    min-height:40px;
    padding:0px 8px !important;
    margin-bottom:6px !important;

    border:1px solid var(--border) !important;
    background:white !important;
    color:#111827 !important;

    box-shadow:0 3px 10px rgba(15,23,42,.04) !important;

    transition:
        transform .08s ease,
        box-shadow .15s ease,
        background .15s ease;
}

hr {
    margin-top:8px !important;
    margin-bottom:8px !important;
}

section[data-testid="stSidebar"] .block-container {
    padding-top:0.4rem !important;
    padding-bottom:0.4rem !important;
}

.stButton > button:hover {
    background:#eff6ff !important;
    border-color:#93c5fd !important;
    transform:translateY(-1px);
}

/* The two login buttons should look primary */
div[data-testid="stForm"] {
    border:1px solid var(--border);
    background:#ffffff;
    padding:22px;
    border-radius:18px;
    box-shadow:0 12px 28px rgba(15,23,42,.06);
}

div[data-testid="stFormSubmitButton"] button {
    background:linear-gradient(90deg,#0b55d9,#155be8) !important;
    color:white !important;
    border:none !important;
    box-shadow:0 8px 20px rgba(21,91,232,.30) !important;
}

/* Employee/Admin Login button (lives inside the dark card column) */
body.is-login-page [data-testid="column"]:first-child .stButton > button {
    background:linear-gradient(90deg,#1f6bff,#0b55d9) !important;
    color:white !important;
    border:none !important;
    min-height:54px !important;
    font-size:16px !important;
    font-weight:800 !important;
    box-shadow:0 10px 24px rgba(21,91,232,.40) !important;
    letter-spacing:.2px;
    margin-top:8px;
}

body.is-login-page [data-testid="column"]:first-child .stButton > button:hover {
    background:linear-gradient(90deg,#2b78ff,#1156e0) !important;
    transform:translateY(-1px);
}

/* ---------- ANSWER BUBBLES ---------- */

.answer-box {
    background:#f0fdf4;
    border:1px solid #bbf7d0;
    border-radius:16px;
    padding:16px;
    margin:10px 0;
}

.protected-box {
    background:#fff7ed;
    border-left:6px solid #f97316;
    border-top:1px solid #fed7aa;
    border-right:1px solid #fed7aa;
    border-bottom:1px solid #fed7aa;
    border-radius:16px;
    padding:16px;
    margin:10px 0;
}

.user-bubble {
    background:#dbeafe;
    border:1px solid #bfdbfe;
    border-radius:16px;
    padding:15px 17px;
    margin:10px 0;
}

.bot-bubble {
    background:#f8fafc;
    border:1px solid #e2e8f0;
    border-radius:16px;
    padding:15px 17px;
    margin:10px 0;
}

.small-text {
    font-size:12px;
    color:var(--muted);
}

.selected-pill {
    display:inline-block;
    background:#dbeafe;
    color:#1e3a8a;
    border:1px solid #bfdbfe;
    padding:9px 14px;
    border-radius:999px;
    font-weight:800;
    margin-bottom:16px;
}

.footer-line {
    margin-top:34px;
    padding:20px 0;
    border-top:1px solid #d8e0ef;
    color:#64748b;
    display:flex;
    justify-content:space-between;
    flex-wrap:wrap;
    gap:10px;
    font-size:13px;
}

/* ---------- RESPONSIVE ---------- */

/* Tablet */
@media only screen and (max-width: 1100px) {
    .block-container { padding-left:1rem; padding-right:1rem; }
    .login-card { min-height:auto; padding:34px 28px; }
    .hero { padding:36px 32px; }
    .brand-title { font-size:32px; }
    .brand-subtitle { font-size:14px; }
}

/* Tablet — narrow the login card padding */
@media only screen and (max-width: 1100px) {
    body.is-login-page [data-testid="column"]:first-child {
        padding:34px 28px !important;
    }
}

/* Mobile */
@media only screen and (max-width: 760px) {
    .block-container { padding-left:0.6rem; padding-right:0.6rem; padding-top:0.5rem; }

    body.is-login-page [data-testid="column"]:first-child {
        padding:28px 22px !important;
        border-radius:20px;
        margin-bottom:18px;
    }
    .login-card-title { font-size:24px; }
    .login-tagline { margin-left:58px; font-size:13px; }
    .login-divider { padding:18px 0; margin:6px 0 20px 0; }
    .login-help { padding-top:18px; font-size:13px; }

    .brand-title { font-size:26px; }
    .brand-subtitle { margin-left:0; margin-top:8px; font-size:13px; }
    .brand-row { flex-wrap:wrap; }

    .hero {
        padding:26px 22px;
        border-radius:20px;
    }
    .hero h2 { font-size:24px; }
    .hero p { font-size:15px; }

    .avatar-img { width:120px; height:120px; }

    .card { padding:18px; border-radius:18px; }

    .user-pill { font-size:13px; padding:10px 14px; }

    .footer-line {
        flex-direction:column;
        text-align:center;
    }

    .stButton > button {
        font-size:15px !important;
        min-height:48px !important;
    }
}

/* Very small screens */
@media only screen and (max-width: 420px) {
    body.is-login-page [data-testid="column"]:first-child {
        padding:22px 16px !important;
    }
    .login-card-title { font-size:21px; }
    .login-bot-icon { height:40px; width:40px; min-width:40px; font-size:19px; }
    .login-tagline { margin-left:54px; }
    .brand-title { font-size:22px; }
    .bot-icon { height:42px; width:42px; min-width:42px; font-size:20px; }
    .hero h2 { font-size:21px; }
    .hero p { font-size:14px; }
}
</style>
""", unsafe_allow_html=True)

# =====================================================
# USER MANAGEMENT
# =====================================================

# Password hashing: bcrypt for new hashes, SHA-256 verify kept for legacy
# users.csv rows so existing accounts keep working until they next log in.
try:
    import bcrypt  # pip install bcrypt (added to requirements.txt)
    _BCRYPT_AVAILABLE = True
except Exception:
    _BCRYPT_AVAILABLE = False


def _legacy_sha256(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """Return a salted bcrypt hash. Falls back to SHA-256 only if bcrypt is
    unavailable (which should not happen once requirements.txt is honoured)."""
    if _BCRYPT_AVAILABLE:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    return _legacy_sha256(password)


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against either a bcrypt hash (new) or a SHA-256 hex
    digest (legacy). Returns True if it matches either format."""
    if not stored_hash:
        return False
    stored = str(stored_hash)
    # bcrypt hashes start with $2a$, $2b$, or $2y$
    if _BCRYPT_AVAILABLE and stored.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
        except Exception:
            return False
    # Legacy SHA-256 hex digest (64 chars)
    return _legacy_sha256(password) == stored

def validate_password_strength(password):
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    if not any(c.isupper() for c in password):
        return False, "Password must include at least one capital letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must include at least one number."
    if not any(not c.isalnum() for c in password):
        return False, "Password must include at least one special character."
    return True, ""

def init_users_file():
    if not USERS_PATH.exists():
        df = pd.DataFrame([{
            "user_id": "admin",
            "password_hash": hash_password(DEFAULT_ADMIN_PASSWORD),
            "role": "Admin",
            "first_login": "False",
            "active": "True",
            "display_name": "Admin"
        }])
        df.to_csv(USERS_PATH, index=False)

def load_users():
    init_users_file()
    df = pd.read_csv(USERS_PATH, dtype=str).fillna("")
    for col in ["user_id", "password_hash", "role", "first_login", "active", "display_name"]:
        if col not in df.columns:
            df[col] = ""
    return df

def save_users(df):
    for col in ["user_id", "password_hash", "role", "first_login", "active", "display_name"]:
        if col in df.columns:
            df[col] = df[col].astype(str)
    df.to_csv(USERS_PATH, index=False)

def bool_from_str(value):
    return str(value).strip().lower() in ["true", "1", "yes", "y"]

def ensure_employee_exists(emp_id):
    df = load_users()
    emp_id = str(emp_id).strip()
    if emp_id not in df["user_id"].astype(str).tolist():
        new_row = pd.DataFrame([{
            "user_id": emp_id,
            "password_hash": hash_password(DEFAULT_EMPLOYEE_PASSWORD),
            "role": "Employee",
            "first_login": "True",
            "active": "True",
            "display_name": f"Employee {emp_id}"
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        save_users(df)

def authenticate_user(user_id, password):
    user_id = str(user_id).strip()
    df = load_users()
    match = df[df["user_id"].astype(str) == user_id]

    # Auto-create numeric employee on first attempt
    if match.empty and user_id.isdigit():
        ensure_employee_exists(user_id)
        df = load_users()
        match = df[df["user_id"].astype(str) == user_id]

    if match.empty:
        return False, "User not found.", None

    row = match.iloc[0]

    if not bool_from_str(row.get("active", "True")):
        return False, "This user is inactive. Please contact admin.", None

    # Standard password check (handles both bcrypt and legacy SHA-256 hashes)
    stored = str(row.get("password_hash", ""))
    if verify_password(password, stored):
        # Silently upgrade legacy SHA-256 hashes to bcrypt on successful login.
        if _BCRYPT_AVAILABLE and not stored.startswith(("$2a$", "$2b$", "$2y$")):
            try:
                first_login_flag = bool_from_str(row.get("first_login", "False"))
                update_user_password(user_id, password, first_login=first_login_flag)
                # Refresh row to reflect new hash
                df_refreshed = load_users()
                refreshed = df_refreshed[df_refreshed["user_id"].astype(str) == user_id]
                if not refreshed.empty:
                    row = refreshed.iloc[0]
            except Exception:
                pass  # Don't block login if upgrade fails
        return True, "", row

    # Optional fallback (controlled by ALLOW_DEFAULT_PWD_RESET in st.secrets).
    # When enabled, typing Welcome@123 resets the employee back to the default
    # password and forces a change on next login. Disable for production.
    if ALLOW_DEFAULT_PWD_RESET and user_id.isdigit() and password == DEFAULT_EMPLOYEE_PASSWORD:
        update_user_password(user_id, DEFAULT_EMPLOYEE_PASSWORD, first_login=True)
        df = load_users()
        refreshed = df[df["user_id"].astype(str) == user_id]
        if not refreshed.empty:
            return True, "", refreshed.iloc[0]

    return False, "Invalid password.", None

def update_user_password(user_id, new_password, first_login=False):
    df = load_users()
    idx = df[df["user_id"].astype(str) == str(user_id)].index
    if len(idx) == 0:
        return False

    df.loc[idx, "password_hash"] = hash_password(new_password)
    df.loc[idx, "first_login"] = "True" if first_login else "False"
    save_users(df)
    try:
        write_audit_log(
            "PASSWORD_UPDATED",
            target_id=str(user_id),
            details=f"first_login={first_login}",
        )
    except Exception:
        pass
    return True

def reset_employee_password(emp_id):
    ensure_employee_exists(emp_id)
    result = update_user_password(emp_id, DEFAULT_EMPLOYEE_PASSWORD, first_login=True)
    try:
        write_audit_log("ADMIN_RESET_PASSWORD", target_id=str(emp_id))
    except Exception:
        pass
    return result

# =====================================================
# SESSION
# =====================================================

defaults = {
    "logged_in": False,
    "role": None,
    "employee_id": None,
    "employee_name": None,
    "must_change_password": False,
    "menu_open": False,
    "selected_module": None,
    "chat_history": [],
    "show_change_password": False,
    "selected_panel": "Home",
    "start_completed": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =====================================================
# LOGIN
# =====================================================

def login_screen():
    # Login-page-specific styling (centered single card, original brand colors)
    st.markdown("""
    <style>
    .login-page-bg { margin-top: -20px; }
    /* Tighten Streamlit's default vertical spacing on the login screen */
    .block-container { padding-top: 0.5rem !important; }
    .login-stack {
        max-width: 500px;
        margin: 0 auto;
        text-align: center;
    }
    .login-logo-wrap {
        text-align: center;
        margin-bottom: 6px;
    }
    .login-logo-wrap img {
        width: 170px;
        max-width: 60%;
        height: auto;
        display: inline-block;
    }
    .login-title-row {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        margin-bottom: 2px;
    }
    .login-title-icon {
        background: linear-gradient(135deg,#155be8,#0b3ba7);
        color: white;
        height: 36px; width: 36px; min-width: 36px;
        border-radius: 50%;
        display: inline-flex; align-items: center; justify-content: center;
        font-weight: 900; font-size: 17px;
        box-shadow: 0 4px 12px rgba(21,91,232,.30);
    }
    .login-title-text {
        font-size: 24px;
        font-weight: 900;
        color: #04123d;
        letter-spacing: -0.3px;
        margin: 0;
        line-height: 1.1;
    }
    .login-subtitle {
        color: #334155;
        font-size: 12px;
        font-weight: 600;
        margin: 0 0 12px 0;
    }
    .login-hero-card {
        background:
            radial-gradient(circle at 86% 42%, rgba(255,255,255,.18), transparent 32%),
            linear-gradient(135deg,#04123d 0%,#0a3aae 55%,#155be8 100%);
        color: white;
        padding: 16px 22px;
        border-radius: 16px;
        box-shadow: 0 10px 28px rgba(15,23,42,.16);
        margin: 0 auto 14px auto;
        max-width: 500px;
        text-align: center;
    }
    .login-hero-card h2 {
        color: white;
        font-size: 18px;
        margin: 0 0 4px 0;
        font-weight: 900;
        letter-spacing: -0.2px;
    }
    .login-hero-card p {
        color: white;
        font-size: 13px;
        margin: 0;
        opacity: 0.95;
        line-height: 1.4;
    }
    .sarika-wrap {
        text-align: center;
        margin: 4px auto 10px auto;
    }
    .sarika-wrap img {
        width: 78px; height: 78px;
        border-radius: 50%;
        object-fit: cover;
        border: 3px solid #1471d8;
        box-shadow: 0 6px 16px rgba(15,23,42,.18);
    }
    .sarika-caption {
        margin-top: 4px;
        font-weight: 800;
        color: #0b3ba7;
        font-size: 13px;
    }
    .sarika-online {
        color: #15803d;
        font-weight: 700;
        font-size: 11px;
        margin-top: 1px;
    }
    .login-form-card {
        background: white;
        border: 1px solid var(--border);
        border-radius: 16px;
        box-shadow: 0 12px 30px rgba(15,23,42,.08);
        padding: 18px 22px;
        max-width: 500px;
        margin: 0 auto 10px auto;
    }
    .login-form-heading {
        font-size: 15px;
        font-weight: 800;
        color: #04123d;
        margin: 0 0 8px 0;
        text-align: left;
    }
    /* Compact form inputs inside the login form */
    .login-form-card div[data-testid="stTextInput"] { margin-bottom: 6px; }
    .login-form-card div[data-testid="stTextInput"] input {
        min-height: 40px !important;
        font-size: 14px !important;
        padding: 6px 12px !important;
    }
    .login-form-card div[data-testid="stTextInput"] label p {
        font-size: 13px !important;
        margin-bottom: 2px !important;
    }
    .login-form-card div[data-testid="stRadio"] { margin-bottom: 6px; }
    .login-form-card div[data-testid="stRadio"] label p {
        font-size: 13px !important;
    }
    .login-form-card .stButton > button {
        min-height: 44px !important;
        font-size: 14px !important;
        margin-top: 6px;
    }
    .login-help-foot {
        text-align: center;
        color: #64748b;
        font-size: 12px;
        margin-top: 2px;
        line-height: 1.5;
    }
    .login-help-foot b { color: #0b3ba7; }

    @media only screen and (max-width: 600px) {
        .login-title-text { font-size: 20px; }
        .login-hero-card { padding: 14px 16px; }
        .login-hero-card h2 { font-size: 16px; }
        .login-form-card { padding: 16px 14px; }
        .login-logo-wrap img { width: 140px; }
        .sarika-wrap img { width: 68px; height: 68px; }
    }
    </style>
    <div class='login-page-bg'></div>
    """, unsafe_allow_html=True)

    # Centered column wrapper (wider side spacers => narrower center => more compact look)
    spacer_l, center, spacer_r = st.columns([1, 2, 1])

    with center:
        # 1. Logo (original color, untouched)
        if LOGO_B64:
            st.markdown(
                f"<div class='login-logo-wrap'><img src='data:image/png;base64,{LOGO_B64}'></div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown("<div class='login-logo-wrap'><h2 style='color:#04123d;'>KOENIG</h2></div>", unsafe_allow_html=True)

        # 2. Koenig Stride title (under logo, brand-colored)
        st.markdown("""
        <div class='login-stack'>
            <div class='login-title-row'>
                <div class='login-title-icon'>☻</div>
                <h1 class='login-title-text'>Koenig Stride</h1>
            </div>
            <div class='login-subtitle'>Tax &amp; Entity Nexus Assistant — Step Forward</div>
        </div>
        """, unsafe_allow_html=True)

        # 3. Welcome hero (under title)
        st.markdown("""
        <div class='login-hero-card'>
            <h2>Welcome to Koenig Stride</h2>
            <p>Your secure internal assistant for tax, salary, entity and SPOC guidance.</p>
        </div>
        """, unsafe_allow_html=True)

        # 5. Login form
        st.markdown("<div class='login-form-card'>", unsafe_allow_html=True)
        st.markdown("<div class='login-form-heading'>🔐 Sign in to continue</div>", unsafe_allow_html=True)

        # Employee login removed — employees now access Strides exclusively
        # via the RMS portal (which passes ?email=<koenig email>). This screen
        # is reachable only via the ?admin=true escape hatch and shows ONLY
        # the admin credentials form.
        st.caption("🔓 Admin access — employees should open Strides from RMS instead.")
        user_id = st.text_input("Admin Username", value="admin")
        password = st.text_input("Password", type="password")
        if st.button("Admin Login", use_container_width=True, type="primary"):
            ok, msg, row = authenticate_user(user_id, password)
            if ok and row.get("role") == "Admin":
                st.session_state.logged_in = True
                st.session_state.role = "Admin"
                st.session_state.employee_id = "admin"
                st.session_state.employee_name = row.get("display_name", "Admin")
                st.session_state.must_change_password = bool_from_str(row.get("first_login", "False"))
                try:
                    write_audit_log("LOGIN_SUCCESS", target_id="admin", details="role=Admin; via_admin_override")
                except Exception:
                    pass
                st.rerun()
            elif ok:
                st.error("This is not an admin account.")
            else:
                try:
                    write_audit_log("LOGIN_FAILED", target_id=str(user_id).strip(), details=f"role=Admin; reason={msg}")
                except Exception:
                    pass
                st.error(msg)

        st.markdown("</div>", unsafe_allow_html=True)

        # 6. Help footer
        st.markdown("""
        <div class='login-help-foot'>
            <b>❔ Need help?</b><br>
            Contact your administrator for assistance.
        </div>
        """, unsafe_allow_html=True)

def _render_rms_only_gate():
    """Show a friendly 'access via RMS' page when no SSO identity is present.
    Employees never see a login form — only this gate."""
    rms_url = "https://rms.koenig-solutions.com"
    try:
        rms_url = st.secrets.get("RMS_PORTAL_URL", rms_url) or rms_url
    except Exception:
        pass
    st.markdown("""
    <style>
      .rms-gate-wrap { max-width: 560px; margin: 80px auto 0 auto; text-align: center; }
      .rms-gate-card {
        background: linear-gradient(135deg,#04123d 0%,#0a3aae 55%,#155be8 100%);
        color: white; padding: 36px 28px; border-radius: 18px;
        box-shadow: 0 12px 32px rgba(15,23,42,.18);
      }
      .rms-gate-title { font-size: 22px; font-weight: 900; margin: 0 0 8px 0; }
      .rms-gate-sub   { font-size: 14px; opacity: 0.92; margin: 0 0 22px 0; line-height: 1.55; }
      .rms-gate-btn {
        display: inline-block; background: white; color: #04123d;
        font-weight: 800; padding: 11px 24px; border-radius: 10px;
        text-decoration: none; box-shadow: 0 4px 14px rgba(0,0,0,.16);
      }
      .rms-gate-foot { font-size: 12px; color: #475569; margin-top: 22px; }
      .rms-gate-foot a { color: #155be8; font-weight: 600; }
    </style>
    """, unsafe_allow_html=True)
    st.markdown(f"""
    <div class='rms-gate-wrap'>
      <div class='rms-gate-card'>
        <div class='rms-gate-title'>🔐 Please open Koenig Stride from the RMS portal</div>
        <p class='rms-gate-sub'>
          Koenig Stride uses your RMS identity — there's no separate login.<br>
          Sign in to RMS and click the <b>Koenig Stride</b> tile.
        </p>
        <a class='rms-gate-btn' href='{rms_url}' target='_blank'>Go to RMS Portal →</a>
      </div>
      <div class='rms-gate-foot'>
        Admin? Open <a href='?admin=true'>this URL</a> to sign in with admin credentials.
      </div>
    </div>
    """, unsafe_allow_html=True)


def force_password_change_screen():
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("## 🔐 Change Password Required")
        st.info("For security, please change your default password before using Koenig Stride.")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        if st.button("Update Password", use_container_width=True):
            if not new_password or not confirm_password:
                st.error("Please enter and confirm new password.")
            elif new_password != confirm_password:
                st.error("Passwords do not match.")
            else:
                ok, msg = validate_password_strength(new_password)
                if not ok:
                    st.error(msg)
                elif new_password in [DEFAULT_EMPLOYEE_PASSWORD, DEFAULT_ADMIN_PASSWORD]:
                    st.error("New password cannot be the default password.")
                else:
                    update_user_password(st.session_state.employee_id, new_password, first_login=False)
                    st.session_state.must_change_password = False
                    st.success("Password updated successfully.")
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

# -----------------------------------------------------
# RMS SSO auto-login (runs once per session if params present)
#
# Identity resolution priority:
#   1. Signed JWT token (?token=...)  — production path
#   2. Plain email param (?email=...) — dev/pilot only, gated by RMS_ALLOW_PLAIN_SSO
#   3. Legacy user+role params         — dev/pilot only, gated by RMS_ALLOW_PLAIN_SSO
#
# Only @koenig-solutions.com emails are accepted.
# First-time SSO users are auto-created in users.csv (linked to Employee Master
# by email when possible).
# -----------------------------------------------------


def _link_or_create_sso_employee(email, display_name):
    """Ensure the SSO user has a row in users.csv.

    Strategy:
      - Derive the internal user_id from the email localpart
        (e.g. 'praveen.chaudhary' from 'praveen.chaudhary@koenig-solutions.com').
      - If an Employee Master row exists with the same email, copy its
        display name & department, AND keep the localpart as the user_id
        (so future Strides records use a stable, human-readable ID).
      - Insert a users.csv row with an unguessable random hash (SSO users
        never need to type a password) and active=True.
    """
    email = (email or "").strip().lower()
    if not _is_allowed_koenig_email(email):
        return None, None

    user_id = _employee_id_from_email(email)
    pretty_name = (display_name or "").strip() or _name_from_email(email)

    # Try to enrich from Employee Master (DB)
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT employee_id, employee_name FROM employee_master WHERE LOWER(email) = ? LIMIT 1",
            (email,),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            # Keep the email-derived user_id (stable across uploads), but
            # prefer the official name from Employee Master.
            if row[1]:
                pretty_name = row[1]
    except Exception:
        pass  # Employee Master may not exist yet on a fresh install

    # Ensure users.csv row exists for this user_id
    try:
        df = load_users()
        if user_id not in df["user_id"].astype(str).tolist():
            # SSO users get an unguessable hash; they don't authenticate by password.
            new_row = pd.DataFrame([{
                "user_id": user_id,
                "password_hash": hash_password(uuid.uuid4().hex + "-sso-only"),
                "role": "Employee",
                "first_login": "False",   # no password change required for SSO
                "active": "True",
                "display_name": pretty_name or user_id,
            }])
            df = pd.concat([df, new_row], ignore_index=True)
            save_users(df)
        else:
            # Refresh display name if we learned a better one
            idx = df[df["user_id"].astype(str) == user_id].index
            if len(idx) and pretty_name and not df.loc[idx[0], "display_name"]:
                df.loc[idx[0], "display_name"] = pretty_name
                save_users(df)
    except Exception:
        pass

    return user_id, pretty_name


if not st.session_state.logged_in and not st.session_state.get("_rms_sso_tried"):
    st.session_state["_rms_sso_tried"] = True
    _sso_email = None       # preferred identity
    _sso_user = None        # legacy fallback identity
    _sso_name = None
    _sso_role = None
    _sso_source = None      # "token" | "plain" — used for audit log

    # 1. Preferred path: signed token
    if RMS_TOKEN_PARAM:
        _payload = _verify_rms_sso_token(RMS_TOKEN_PARAM)
        if _payload:
            _sso_email = str(_payload.get("email", "")).strip().lower() or None
            _sso_user = str(_payload.get("user", "")).strip() or None
            _sso_name = str(_payload.get("name", "")).strip() or None
            _sso_role = str(_payload.get("role", "")).strip() or None
            _sso_source = "token"

    # 2. Plain email param (?email=<koenig email>) — the standard RMS-integration
    #    path. RMS passes the user's email in the URL and Strides logs them in.
    #    Non-koenig domains are rejected below.
    if not (_sso_email or _sso_user):
        if RMS_EMAIL_PARAM:
            _sso_email = RMS_EMAIL_PARAM.strip().lower()
            _sso_name = RMS_NAME_PARAM or None
            _sso_role = RMS_ROLE_PARAM or None
            _sso_source = "plain"
        elif RMS_USER_PARAM:
            # Legacy fallback — RMS passing employee_id instead of email
            _sso_user = RMS_USER_PARAM
            _sso_name = RMS_NAME_PARAM or RMS_USER_PARAM
            _sso_role = RMS_ROLE_PARAM or "Employee"
            _sso_source = "plain"

    # ---- Email-based SSO (primary path) ----
    if _sso_email:
        if not _is_allowed_koenig_email(_sso_email):
            # Reject non-koenig domains silently — falls through to login screen.
            try:
                write_audit_log("SSO_REJECTED", target_id=_sso_email,
                                details=f"reason=non_koenig_domain; source={_sso_source}")
            except Exception:
                pass
        else:
            _resolved_user_id, _resolved_name = _link_or_create_sso_employee(_sso_email, _sso_name)
            if _resolved_user_id:
                # Role: explicit Admin from token wins; else check admin-email list; else Employee.
                _role = "Employee"
                if _sso_role and _sso_role.strip().lower() == "admin":
                    _role = "Admin"
                elif _is_admin_email(_sso_email):
                    _role = "Admin"

                st.session_state.logged_in = True
                st.session_state.role = _role
                st.session_state.employee_id = _resolved_user_id
                st.session_state.employee_name = _resolved_name or _resolved_user_id
                st.session_state.employee_email = _sso_email
                st.session_state.must_change_password = False
                st.session_state.start_completed = True  # SSO users skip the start-here gate
                try:
                    write_audit_log("SSO_LOGIN", target_id=_sso_email,
                                    details=f"role={_role}; source={_sso_source}")
                except Exception:
                    pass

    # ---- Legacy ID-based SSO (kept for back-compat with older RMS tile URLs) ----
    elif _sso_user:
        ensure_employee_exists(_sso_user)
        st.session_state.logged_in = True
        st.session_state.role = _sso_role if _sso_role in ("Admin", "Employee") else "Employee"
        st.session_state.employee_id = _sso_user
        st.session_state.employee_name = _sso_name or _sso_user
        st.session_state.must_change_password = False
        st.session_state.start_completed = True
    # Optional: deep-link to a panel (applies if any SSO path succeeded)
    if st.session_state.logged_in and DEEP_LINK_PANEL:
        _panel_map = {
            "home": "Home",
            "start-here": "Start Here",
            "ask-strides": "Ask Strides",
            "ask-sarika": "Ask Strides",  # legacy alias — keeps old RMS tile URLs working
            "user-management": "User Management",
            "knowledge-base": "Knowledge Base",
            "question-analytics": "Question Analytics",
            "admin-analytics": "Admin Analytics",
            "spoc": "SPOC",
        }
        _resolved = _panel_map.get(DEEP_LINK_PANEL.lower())
        if _resolved:
            st.session_state.selected_panel = _resolved

    # ---- Strip sensitive params from the URL after SSO succeeds ----
    # Removes ?email=, ?token=, ?user=, ?role=, ?name= from the address bar
    # so the email doesn't sit in browser history / get shoulder-surfed.
    # `embed`, `panel`, and `admin` are kept (they're not sensitive).
    if st.session_state.logged_in:
        try:
            kept = {}
            for k in ("embed", "panel"):
                v = _qp.get(k)
                if v:
                    kept[k] = v
            # Clear all query params, then set back only the safe ones.
            try:
                st.query_params.clear()
                for k, v in kept.items():
                    st.query_params[k] = v
            except Exception:
                # Older Streamlit versions — best-effort fallback
                try:
                    st.experimental_set_query_params(**kept)
                except Exception:
                    pass
        except Exception:
            pass

# -----------------------------------------------------
# Access gate
#   • If SSO succeeded → already logged in, fall through.
#   • If admin override (?admin=true) → show admin login form.
#   • Otherwise → show 'Please open via RMS' page (no employee login).
# -----------------------------------------------------
if not st.session_state.logged_in:
    if ADMIN_OVERRIDE:
        login_screen()
    else:
        _render_rms_only_gate()
    st.stop()

if st.session_state.must_change_password:
    force_password_change_screen()
    st.stop()

# =====================================================
# KNOWLEDGE
# =====================================================

@st.cache_data
def load_knowledge():
    if not EXCEL_PATH.exists():
        return pd.DataFrame(), f"Knowledge file not found: {EXCEL_PATH}"
    try:
        xl = pd.ExcelFile(EXCEL_PATH)
        frames = []
        for sheet in ["Salary & Tax FAQs", "Entity Nexus FAQs"]:
            if sheet in xl.sheet_names:
                df = pd.read_excel(EXCEL_PATH, sheet_name=sheet).fillna("")
                df["Source"] = sheet
                frames.append(df)
        if not frames:
            return pd.DataFrame(), "No valid FAQ sheets found."
        return pd.concat(frames, ignore_index=True).fillna(""), ""
    except Exception as e:
        return pd.DataFrame(), str(e)

@st.cache_data
def load_spoc_master():
    """Load the SPOC Master sheet — used exclusively by the SPOC Routing module."""
    if not EXCEL_PATH.exists():
        return pd.DataFrame()
    try:
        xl = pd.ExcelFile(EXCEL_PATH)
        if "SPOC Master" not in xl.sheet_names:
            return pd.DataFrame()
        df = pd.read_excel(EXCEL_PATH, sheet_name="SPOC Master").fillna("")
        # Standardise column names — trim whitespace
        df.columns = [str(c).strip() for c in df.columns]
        # Drop completely empty rows
        df = df[df.apply(lambda r: any(str(v).strip() for v in r.values), axis=1)].reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()

faq_df, load_error = load_knowledge()
spoc_df = load_spoc_master()

def safe_get(row, col, default=""):
    try:
        return str(row.get(col, default)).strip()
    except Exception:
        return default

def normalize(value):
    return str(value).strip().lower()

def is_protected(row):
    return normalize(safe_get(row, "Protected")) in ["yes", "y", "true", "1", "protected"]

def get_answer_text(row):
    for col in ["Display Message (Voice)", "Voice Response", "Answer (Internal)", "Answer", "Response"]:
        val = safe_get(row, col)
        if val:
            return val
    return "Answer found, but response text is blank in the knowledge file."

def get_spoc(row):
    return safe_get(row, "SPOC Name", "Relevant SPOC"), safe_get(row, "SPOC Email", "")

def get_category_column(df):
    for col in ["Category", "Section", "Topic", "Module"]:
        if col in df.columns:
            return col
    return None

def get_question_column(df):
    for col in ["Question", "Questions", "FAQ", "Query"]:
        if col in df.columns:
            return col
    return None

TAX_CATEGORIES = {"advance tax","form 16","home loan & insurance","hra","income tax 2026","nps","penalty & delay","salary tax basics","sodexo / meal benefit","tax claim process","tax regime"}
SALARY_CATEGORIES = {"reimbursements","salary structure"}
LABOUR_CATEGORIES = {"labour code","labor code","labour codes","labor codes"}

def get_module_for_row(row):
    source = normalize(safe_get(row, "Source"))
    category = normalize(safe_get(row, "Category"))
    question = normalize(safe_get(row, "Question"))
    keywords = normalize(safe_get(row, "Keywords"))
    answer = normalize(get_answer_text(row))
    combined = " ".join([source, category, question, keywords, answer])
    if category in LABOUR_CATEGORIES or "labour code" in combined or "labor code" in combined:
        return "Labour Code"
    if category in SALARY_CATEGORIES:
        return "Salary Queries"
    if category in TAX_CATEGORIES:
        return "Tax FAQs"
    # NOTE: SPOC Routing module is now powered exclusively by the SPOC Master
    # sheet via render_spoc_routing(). FAQ rows are no longer routed here
    # — they will fall through to Entity Nexus / Compliance / Tax instead.
    if is_protected(row):
        return "Protected Information Routing"
    if "entity" in source or "entity" in combined:
        return "Entity Nexus"
    if any(x in combined for x in ["compliance","tds","gst","filing","return","deduction","80c","80ccd"]):
        return "Compliance Support"
    if any(x in combined for x in ["salary","payroll","ctc","reimbursement"]):
        return "Salary Queries"
    return "Tax FAQs"

def render_spoc_routing():
    """Render the SPOC Routing module — sourced ONLY from the SPOC Master sheet."""
    if spoc_df.empty:
        st.warning("SPOC Master sheet not found in the knowledge file.")
        return

    # Resolve column names defensively
    topic_col = next((c for c in spoc_df.columns if "topic" in c.lower() or "entity" in c.lower()), spoc_df.columns[0])
    name_col = next((c for c in spoc_df.columns if "name" in c.lower()), None)
    email_col = next((c for c in spoc_df.columns if "email" in c.lower()), None)

    st.markdown(
        "<div style='color:#475569; font-size:14px; margin-bottom:14px;'>"
        "Below is the official list of <b>Single Points of Contact (SPOCs)</b> for each topic and entity. "
        "For any query, please reach out to the relevant SPOC directly."
        "</div>",
        unsafe_allow_html=True
    )

    # Group SPOCs by name for a clean grouped view
    if name_col:
        try:
            grouped = spoc_df.groupby(name_col, sort=False)
            for spoc_name, group in grouped:
                spoc_name_str = str(spoc_name).strip() or "Unassigned"
                email = ""
                if email_col:
                    emails = [str(e).strip() for e in group[email_col].tolist() if str(e).strip()]
                    email = emails[0] if emails else ""
                topics = [str(t).strip() for t in group[topic_col].tolist() if str(t).strip()]

                topic_html = "".join(
                    f"<li style='margin:4px 0; color:#1e293b;'>{t}</li>" for t in topics
                )
                email_html = (
                    f"<a href='mailto:{email}' style='color:#0b55d9; text-decoration:none; font-weight:700;'>{email}</a>"
                    if email else "<span style='color:#94a3b8;'>(no email on file)</span>"
                )
                st.markdown(f"""
                <div style='background:#ffffff; border:1px solid #dbe3ef; border-left:5px solid #155be8;
                            border-radius:14px; padding:16px 18px; margin-bottom:12px;
                            box-shadow:0 6px 18px rgba(15,23,42,.06);'>
                    <div style='display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;'>
                        <div style='font-size:17px; font-weight:800; color:#04123d;'>
                            👤 {spoc_name_str}
                        </div>
                        <div style='font-size:13px;'>✉️ {email_html}</div>
                    </div>
                    <div style='margin-top:10px; font-size:13px; color:#64748b; font-weight:700;
                                text-transform:uppercase; letter-spacing:.4px;'>
                        Topics / Entities handled ({len(topics)})
                    </div>
                    <ul style='margin:6px 0 0 18px; padding:0; font-size:14px;'>{topic_html}</ul>
                </div>
                """, unsafe_allow_html=True)
        except Exception:
            # Fallback: show plain table
            st.dataframe(spoc_df, use_container_width=True)
    else:
        st.dataframe(spoc_df, use_container_width=True)

    # Searchable quick lookup
    with st.expander("🔍 Quick lookup — search by topic, entity, name or email", expanded=False):
        q = st.text_input("Search", placeholder="e.g. UAE, Tax, Ritika…", key="spoc_search")
        if q and q.strip():
            q_norm = q.strip().lower()
            mask = spoc_df.apply(
                lambda r: any(q_norm in str(v).lower() for v in r.values), axis=1
            )
            results = spoc_df[mask]
            if results.empty:
                st.info("No matching SPOC found.")
            else:
                st.dataframe(results, use_container_width=True, hide_index=True)

if not faq_df.empty:
    faq_df = faq_df.copy()
    faq_df["Main Module"] = faq_df.apply(get_module_for_row, axis=1)

def get_categories_for_module(df, module):
    if df.empty:
        return []
    cat_col = get_category_column(df)
    if not cat_col:
        return []
    filtered = df[df["Main Module"] == module].copy()
    excluded = ["section mapping", "mapping", "section-mapping", ""]
    categories = filtered[cat_col].dropna().astype(str).str.strip().unique().tolist()
    categories = [c for c in categories if c.lower() not in excluded]
    categories.sort(key=lambda x: x.lower())
    return categories

def get_questions_by_module_category(df, module, category):
    cat_col = get_category_column(df)
    if not cat_col:
        return pd.DataFrame()
    filtered = df[(df["Main Module"] == module) & (df[cat_col].astype(str).str.strip().str.lower() == category.strip().lower())].copy()
    q_col = get_question_column(filtered)
    if q_col:
        filtered = filtered[filtered[q_col].astype(str).str.strip() != ""]
    return filtered

def render_answer(row):
    if is_protected(row):
        spoc, email = get_spoc(row)
        email_html = f"<br><b>Email:</b> {email}" if email else ""
        st.markdown(f"<div class='protected-box'><b>🔒 Protected Information</b><br>This information is protected and cannot be displayed here.<br><br>Please contact the designated SPOC:<br><b>SPOC:</b> {spoc}{email_html}</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='answer-box'><b>Koenig Stride Answer:</b><br>{get_answer_text(row)}</div>", unsafe_allow_html=True)

# =====================================================
# SEARCH
# =====================================================

@st.cache_resource
def load_model():
    if not AI_AVAILABLE:
        return None
    try:
        return SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        return None

model = load_model()

def get_openai_client():
    if not AI_AVAILABLE:
        return None
    try:
        api_key = st.secrets.get("OPENAI_API_KEY", "")
        return OpenAI(api_key=api_key) if api_key else None
    except Exception:
        return None

client = get_openai_client()

if not faq_df.empty:
    for col in ["Question", "Keywords", "Alternate Phrases", "Category", "Answer (Internal)", "Display Message (Voice)"]:
        if col not in faq_df.columns:
            faq_df[col] = ""
    faq_df["combined_text"] = (
        faq_df["Question"].astype(str) + " " +
        faq_df["Keywords"].astype(str) + " " +
        faq_df["Alternate Phrases"].astype(str) + " " +
        faq_df["Category"].astype(str) + " " +
        faq_df["Answer (Internal)"].astype(str) + " " +
        faq_df["Display Message (Voice)"].astype(str)
    )
else:
    faq_df["combined_text"] = ""

@st.cache_resource
def create_embeddings(texts):
    if model is None or not texts:
        return np.array([])
    return model.encode(texts, show_progress_bar=False)

embeddings = create_embeddings(faq_df["combined_text"].tolist()) if not faq_df.empty else np.array([])

def semantic_search(query, top_k=3):
    if faq_df.empty:
        return pd.DataFrame()
    if model is not None and embeddings.size > 0:
        q_emb = model.encode([query])
        sims = cosine_similarity(q_emb, embeddings)[0]
        top_indices = np.argsort(sims)[::-1][:top_k]
        results = faq_df.iloc[top_indices].copy()
        results["similarity"] = sims[top_indices]
        return results
    q = normalize(query)
    scores = []
    for _, row in faq_df.iterrows():
        text = normalize(row.get("combined_text", ""))
        score = sum(1 for word in q.split() if word in text) / max(len(q.split()), 1)
        scores.append(score)
    temp = faq_df.copy()
    temp["similarity"] = scores
    return temp.sort_values("similarity", ascending=False).head(top_k)

# ----- Out-of-scope / chitchat detector -----
# When a query doesn't look like a tax/HR/finance question, we let the AI
# respond casually (without strict KB constraints) so employees can chat
# naturally. Examples: 'hello', 'how are you', 'tell me a joke', 'weather'.
_CHITCHAT_INDICATORS = (
    "hello", "hi ", "hi!", "hey", "good morning", "good afternoon", "good evening",
    "how are you", "how's it going", "thank", "thanks", "thx", "bye", "goodbye",
    "joke", "weather", "who are you", "what is your name", "who made you",
    "sing", "poem", "story", "fun fact", "how old", "your favourite",
    "are you human", "are you a bot", "chatgpt", "openai",
)
_BUSINESS_DOMAIN_WORDS = (
    "tax", "salary", "payroll", "hra", "nps", "80c", "80d", "pf", "epf",
    "deduct", "regime", "form 16", "form 12", "tds", "pan", "ctc",
    "declaration", "investment", "reimburse", "meal pass", "sodexo",
    "leave", "holiday", "labour", "compliance", "entity", "koenig",
    "spoc", "finance", "hr", "income", "refund", "itr",
)


def _looks_like_chitchat(text):
    t = (text or "").lower().strip()
    if not t:
        return False
    if any(b in t for b in _BUSINESS_DOMAIN_WORDS):
        return False
    return any(c in t for c in _CHITCHAT_INDICATORS) or len(t.split()) <= 3


def generate_response(query, results):
    """Strict KB-grounded answer. The model is FORBIDDEN from inventing facts.

    Returns (answer_text, is_ai_generated).
      • is_ai_generated=True when GPT was used to compose the reply
        (so the UI can show the ⚠️ yellow banner).
      • is_ai_generated=False when the canned KB answer was used directly.
    """
    top = results.iloc[0]
    if client is None:
        return get_answer_text(top), False
    context = ""
    for _, row in results.iterrows():
        context += f"""
Question: {safe_get(row, 'Question')}
Answer: {get_answer_text(row)}
Protected: {safe_get(row, 'Protected')}
SPOC: {safe_get(row, 'SPOC Name')}
Email: {safe_get(row, 'SPOC Email')}
"""
    prompt = f"""You are **Koenig Stride**, an internal assistant for Koenig Solutions employees
on Indian tax, payroll, HR, labour code, entity nexus and SPOC routing.

STRICT RULES — follow without exception:

1. Answer ONLY using the Knowledge Base provided below. Never invent facts,
   never quote tax sections / dates / amounts that are not in the KB.
2. If the KB does not clearly answer the question, reply EXACTLY with:
   "This is not in our records. Please contact the Tax team at tax@koenig-solutions.com."
3. If a KB row marked Protected=YES is the best match, do NOT reveal the answer.
   Instead route the employee to the SPOC listed for that row.
4. Do not give legal or financial advice. State that the answer is an internal
   reference only.
5. Keep answers concise (4-6 sentences) unless the user asks for detail.
6. All amounts are in Indian Rupees (₹). Use Indian numbering format (1,50,000).
7. The current Tax Year is FY 2026-27 under the Income-tax Act, 2025.

Knowledge Base:
{context}
"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":prompt},{"role":"user","content":query}],
            temperature=0.1,
        )
        return resp.choices[0].message.content, True
    except Exception:
        return get_answer_text(top), False


def generate_chitchat_response(query):
    """Free-form AI reply for out-of-scope / casual questions."""
    if client is None:
        return (
            "I'm Strides, the Koenig assistant for tax, payroll, HR and SPOC queries. "
            "How can I help?",
            False,
        )
    prompt = (
        "You are Strides, a friendly assistant for Koenig Solutions employees.\n"
        "Keep replies short (1-3 sentences), warm, and appropriate for an office setting.\n"
        "If asked about your identity, say you are Strides — Koenig's internal assistant "
        "for tax, payroll, HR and SPOC queries.\n"
        "Do NOT give legal, tax, or financial advice in this casual mode — if asked, "
        "redirect the user to ask the same question with 'tax' or 'salary' in it."
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":prompt},{"role":"user","content":query}],
            temperature=0.7,
        )
        return resp.choices[0].message.content, True
    except Exception:
        return (
            "I'm Strides, the Koenig assistant for tax, payroll, HR and SPOC queries. "
            "How can I help?",
            False,
        )

# -----------------------------------------------------
# QUERY LOGGING (for Question Analytics admin panel)
# Threshold above which a query is considered "matched / in record"
QUERY_LOG_MATCH_THRESHOLD = 0.35  # below this → weak match / not in record
QUERY_LOG_MIN_THRESHOLD = 0.15    # below this → no answer at all
# -----------------------------------------------------


def _ensure_query_log_table():
    """Create the query_log table on first use (idempotent)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS query_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asked_at TEXT,
                employee_id TEXT,
                employee_name TEXT,
                query TEXT,
                matched INTEGER,           -- 1 if matched a FAQ, 0 otherwise
                in_record INTEGER,         -- 1 if above MATCH threshold, 0 if weak/no match
                matched_faq_id TEXT,
                matched_category TEXT,
                matched_question TEXT,
                similarity REAL,
                response_type TEXT,        -- 'answer' | 'protected' | 'not_found' | 'weak_match'
                source TEXT
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_query_log_in_record ON query_log(in_record)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_query_log_asked_at ON query_log(asked_at)")
        conn.commit()
        conn.close()
    except Exception:
        pass


def log_query(query, response_type, top_row=None, similarity=0.0):
    """Record an Ask Strides query into query_log.

    response_type: 'answer' | 'protected' | 'not_found' | 'weak_match'
    top_row: best matching FAQ row (may be None)
    similarity: cosine-similarity / keyword score
    """
    try:
        _ensure_query_log_table()
        sim = float(similarity or 0)
        in_record = 1 if sim >= QUERY_LOG_MATCH_THRESHOLD and response_type in ("answer", "protected") else 0
        matched = 1 if response_type in ("answer", "protected") else 0
        faq_id = str(safe_get(top_row, "ID")) if top_row is not None else ""
        cat = safe_get(top_row, "Category") if top_row is not None else ""
        q_match = safe_get(top_row, "Question") if top_row is not None else ""
        src = safe_get(top_row, "Source") if top_row is not None else ""
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO query_log (
                asked_at, employee_id, employee_name, query,
                matched, in_record, matched_faq_id, matched_category,
                matched_question, similarity, response_type, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            str(st.session_state.get("employee_id", "") or ""),
            str(st.session_state.get("employee_name", "") or ""),
            str(query)[:1000],
            matched, in_record,
            faq_id, cat, q_match,
            sim, response_type, src,
        ))
        conn.commit()
        conn.close()
    except Exception:
        # never break the chat flow because of logging
        pass


# -----------------------------------------------------
# LIVE TAX CALCULATOR (intercepts numeric salary questions before FAQ search)
# -----------------------------------------------------

# FY 2026-27 slabs — must match the values used elsewhere in the app.
TAX_CALC_NEW_SLABS = [
    (400000, 0.00), (800000, 0.05), (1200000, 0.10),
    (1600000, 0.15), (2000000, 0.20), (2400000, 0.25),
    (float("inf"), 0.30),
]
TAX_CALC_OLD_SLABS = [
    (250000, 0.00), (500000, 0.05),
    (1000000, 0.20), (float("inf"), 0.30),
]
TAX_CALC_NEW_STD_DED   = 75000
TAX_CALC_OLD_STD_DED   = 50000
TAX_CALC_CESS          = 0.04
TAX_CALC_NEW_REBATE_UP = 1200000   # 87A under new regime: nil up to ₹12L taxable
TAX_CALC_OLD_REBATE_UP = 500000    # 87A under old regime: nil up to ₹5L taxable


def _parse_amount_with_unit(num_str, unit_str):
    """Convert a raw number + optional Indian unit (lakh/lac/crore/L/cr) into rupees."""
    try:
        val = float(num_str.replace(",", ""))
    except Exception:
        return None
    u = (unit_str or "").lower().strip()
    if u in ("lakh", "lakhs", "lac", "lacs", "l"):
        val *= 100000
    elif u in ("crore", "crores", "cr"):
        val *= 10000000
    elif u in ("k", "thousand"):
        val *= 1000
    return val


def _extract_amount_after(text, after_keywords):
    """Find the first number that appears AFTER any of the given keywords.
    Returns rupee value or None."""
    pat = (
        r"(?:" + "|".join(re.escape(k) for k in after_keywords) + r")"
        r"[^\d]{0,40}"
        r"(\d[\d,]*\.?\d*)\s*(lakh|lakhs|lac|lacs|crore|crores|cr|l|k|thousand)?"
    )
    m = re.search(pat, text, re.IGNORECASE)
    if not m:
        return None
    return _parse_amount_with_unit(m.group(1), m.group(2))


def _extract_salary(text):
    """Detect the primary salary figure mentioned in `text`.

    Heuristics, in priority order:
      1. Number immediately after 'salary' / 'income' / 'CTC' / 'gross' / 'package' / 'earn'.
      2. The LARGEST standalone amount in the sentence (ignoring small numbers <₹1L,
         which are almost always deduction figures, not salary).

    Returns the rupee value, or None if no plausible salary found.
    """
    text = text or ""
    # Priority 1: explicit salary keyword
    for kw in ["salary", "income", "ctc", "gross", "package", "earn",
               "earning", "earnings", "compensation", "pay"]:
        v = _extract_amount_after(text, [kw])
        if v and v >= 100000:    # at least ₹1L to be a plausible annual salary
            return v

    # Priority 2: largest standalone amount
    candidates = []
    for m in re.finditer(
        r"(?<![\d.])(\d[\d,]*\.?\d*)\s*(lakh|lakhs|lac|lacs|crore|crores|cr|l|k|thousand)?",
        text, re.IGNORECASE,
    ):
        v = _parse_amount_with_unit(m.group(1), m.group(2))
        if v and v >= 100000:
            candidates.append(v)
    return max(candidates) if candidates else None


# Section→ (display name, max cap in rupees, kind)
# kind: 'old' → only in Old regime; 'both' → allowed in both regimes
_DEDUCTION_PATTERNS = [
    # 80C and substitutes
    ("80c",      "Section 80C",          150000, "old"),
    ("pf",       "PF (under 80C)",       150000, "old"),
    ("ppf",      "PPF (under 80C)",      150000, "old"),
    ("elss",     "ELSS (under 80C)",     150000, "old"),
    ("lic",      "LIC premium (80C)",    150000, "old"),
    # 80D health insurance
    ("80d",      "Section 80D (health insurance)", 100000, "old"),
    ("mediclaim","Mediclaim (80D)",      100000, "old"),
    # NPS (additional)
    ("80ccd(1b)","NPS 80CCD(1B)",         50000, "old"),
    ("80ccd1b",  "NPS 80CCD(1B)",         50000, "old"),
    # NPS (employer) — ALLOWED in NEW regime too
    ("80ccd(2)", "Employer NPS 80CCD(2)", 99999999, "both"),
    ("80ccd2",   "Employer NPS 80CCD(2)", 99999999, "both"),
    ("employer nps", "Employer NPS 80CCD(2)", 99999999, "both"),
    # Home loan interest — Section 24(b)
    ("home loan",       "Home Loan Interest (24b)", 200000, "old"),
    ("home-loan",       "Home Loan Interest (24b)", 200000, "old"),
    ("housing loan",    "Home Loan Interest (24b)", 200000, "old"),
    ("24(b)",           "Home Loan Interest (24b)", 200000, "old"),
    # HRA
    ("hra",             "HRA exemption",            99999999, "old"),
    ("house rent",      "HRA exemption",            99999999, "old"),
    # Education loan
    ("80e",             "Section 80E (education loan)", 99999999, "old"),
    ("education loan",  "Section 80E (education loan)", 99999999, "old"),
    # Donation
    ("80g",             "Section 80G (donation)",   99999999, "old"),
    ("donation",        "Section 80G (donation)",   99999999, "old"),
    # LTA
    ("lta",             "LTA exemption",            99999999, "old"),
    ("leave travel",    "LTA exemption",            99999999, "old"),
    # Meal Passes / Sodexo — ALLOWED in NEW regime too
    ("meal pass",       "Meal Passes / Sodexo",     26400, "both"),
    ("meal passes",     "Meal Passes / Sodexo",     26400, "both"),
    ("sodexo",          "Meal Passes / Sodexo",     26400, "both"),
]


def _extract_deductions(text):
    """Return a list of {section, name, amount, kind} dicts found in the text.

    Matching rules:
      • Keyword must occur as a WHOLE WORD (no substring matches — e.g. '80c' must
        not match inside '80ccd(2)').
      • Find a nearby number (after first, then before; within ~40 chars).
        The number must be ≥ 1000 to avoid grabbing stray digits from "80CCD(2)".
        If no explicit amount mentioned, assume the FULL cap (assumed=True).
      • Cap at the section's statutory limit.
      • Dedupe by display name; first occurrence wins.
    """
    text = (text or "").lower()
    found = {}
    # Process keywords longest-first so '80ccd(2)' is consumed before '80c'.
    for kw, name, cap, kind in sorted(_DEDUCTION_PATTERNS, key=lambda x: -len(x[0])):
        kw_re = re.escape(kw)
        # Whole-word boundary: not preceded/followed by alphanumerics that
        # would extend the keyword (e.g. '80c' inside '80ccd').
        # We treat the keyword start/end as boundaries against [a-z0-9].
        boundary = r"(?<![a-z0-9])" + kw_re + r"(?![a-z0-9])"
        if not re.search(boundary, text):
            continue
        # Number AFTER the keyword (within 40 chars)
        pat_after = boundary + r"[^\d]{0,40}(\d[\d,]*\.?\d*)\s*(lakh|lakhs|lac|lacs|crore|crores|cr|l|k|thousand)?"
        m = re.search(pat_after, text)
        amount, assumed = None, False
        if m:
            v = _parse_amount_with_unit(m.group(1), m.group(2))
            # Reject tiny stray numbers (likely a section number, not an amount)
            if v is not None and v >= 1000:
                amount = v
        if amount is None:
            # Number BEFORE the keyword
            pat_before = r"(\d[\d,]*\.?\d*)\s*(lakh|lakhs|lac|lacs|crore|crores|cr|l|k|thousand)?[^\d]{0,40}" + boundary
            m2 = re.search(pat_before, text)
            if m2:
                v = _parse_amount_with_unit(m2.group(1), m2.group(2))
                if v is not None and v >= 1000:
                    amount = v
        if amount is None:
            amount = cap
            assumed = True
        amount = min(amount, cap)
        if name not in found:
            found[name] = {"name": name, "amount": amount, "kind": kind, "assumed": assumed}
    return list(found.values())


def _tax_from_slabs(taxable, slabs):
    if taxable <= 0:
        return 0.0
    prev, tax = 0, 0.0
    for cap, rate in slabs:
        slice_ = min(taxable, cap) - prev
        if slice_ > 0:
            tax += slice_ * rate
        if taxable <= cap:
            break
        prev = cap
    return tax


def _compute_regime_breakup(gross, regime, deductions):
    """Return a dict with the full step-by-step computation for one regime."""
    if regime == "New":
        std_ded = TAX_CALC_NEW_STD_DED
        # Only deductions with kind='both' apply under New regime.
        applicable = [d for d in deductions if d["kind"] == "both"]
        slabs = TAX_CALC_NEW_SLABS
        rebate_cap = TAX_CALC_NEW_REBATE_UP
    else:
        std_ded = TAX_CALC_OLD_STD_DED
        applicable = list(deductions)
        slabs = TAX_CALC_OLD_SLABS
        rebate_cap = TAX_CALC_OLD_REBATE_UP

    ded_total = sum(d["amount"] for d in applicable)
    taxable = max(0, gross - std_ded - ded_total)
    tax = _tax_from_slabs(taxable, slabs)
    rebate_applied = False
    if taxable <= rebate_cap:
        tax = 0.0
        rebate_applied = True
    cess = tax * TAX_CALC_CESS
    total = round(tax + cess)
    return {
        "regime": regime,
        "std_ded": std_ded,
        "deductions": applicable,
        "deductions_total": ded_total,
        "taxable": taxable,
        "tax": round(tax),
        "cess": round(cess),
        "total": total,
        "rebate_applied": rebate_applied,
    }


def _format_inr(amount):
    return f"₹{amount:,.0f}"


def _render_calc_answer(gross, new_r, old_r, deductions):
    """Build a markdown answer comparing both regimes side-by-side."""
    lines = [
        f"### Tax computation for annual gross salary {_format_inr(gross)} (FY 2026-27)",
        "",
    ]
    if deductions:
        lines.append("**Deductions detected in your question:**")
        for d in deductions:
            note = " *(assumed full limit — mention the amount for accuracy)*" if d["assumed"] else ""
            badge = "both regimes" if d["kind"] == "both" else "old regime only"
            lines.append(f"- {d['name']}: {_format_inr(d['amount'])}  _({badge}){note}_")
        lines.append("")
    else:
        lines.append("_No specific deductions mentioned. Old-regime numbers below assume NO investments. To get a tailored Old-regime result, mention your 80C / 80D / HRA / home-loan / NPS amounts._")
        lines.append("")

    def _section(label, r):
        out = [f"#### {label}"]
        out.append(f"- Standard deduction: {_format_inr(r['std_ded'])}")
        if r["deductions"]:
            out.append(f"- Other deductions applied: {_format_inr(r['deductions_total'])}")
        else:
            out.append("- Other deductions applied: ₹0 *(none allowed under this regime)*" if r["regime"] == "New" else "- Other deductions applied: ₹0")
        out.append(f"- **Taxable income: {_format_inr(r['taxable'])}**")
        if r["rebate_applied"]:
            out.append("- Slab tax: nil after Section 87A rebate")
        else:
            out.append(f"- Slab tax: {_format_inr(r['tax'])}")
            out.append(f"- Health & education cess (4%): {_format_inr(r['cess'])}")
        out.append(f"- **Total tax payable: {_format_inr(r['total'])}**")
        return "\n".join(out)

    lines.append(_section("🆕 New Tax Regime", new_r))
    lines.append("")
    lines.append(_section("📜 Old Tax Regime", old_r))
    lines.append("")

    diff = old_r["total"] - new_r["total"]
    if diff > 0:
        lines.append(f"✅ **New Regime saves you {_format_inr(diff)}** over the Old regime in this scenario.")
    elif diff < 0:
        lines.append(f"✅ **Old Regime saves you {_format_inr(-diff)}** over the New regime in this scenario.")
    else:
        lines.append("⚖️ Both regimes give the same tax in this scenario.")

    lines.append("")
    lines.append("---")
    lines.append("_This is an estimate based only on what you typed. For your exact liability, consult the Tax team at tax@koenig-solutions.com._")

    return "\n".join(lines)


# Words that, when present alongside a salary-like number, indicate a tax
# computation request. Kept broad so conversational follow-ups still match.
_TAX_TRIGGER_WORDS = (
    "tax", "taxable", "liability", "how much", "calculate", "calc",
    "regime", "deduct", "pay", "payable",
    # Conversational / follow-up hints
    "income", "salary", "ctc", "package", "earning", "earn",
    "if ", "what if", "and if", "compute",
)


def _looks_like_tax_question(text):
    """Cheap intent check — the user is asking about tax on a salary number."""
    t = (text or "").lower()
    return any(w in t for w in _TAX_TRIGGER_WORDS)


def _last_turn_was_tax_calc():
    """Return True iff the most recent assistant message was a tax computation.

    Used to treat follow-up numeric questions (e.g. "and if income is 30 lakh?")
    as calculator queries even when the trigger words are absent.
    """
    history = st.session_state.get("chat_history", [])
    for item in reversed(history):
        if item.get("type") == "answer" and item.get("source") == "Live Tax Calculator":
            return True
        if item.get("type") in ("answer", "protected", "not_found", "ai_answer"):
            return False    # only count the most recent assistant turn
    return False


def _last_calc_deductions():
    """Return the deductions list from the most recent tax-calc turn (or []).
    Allows follow-up questions to inherit previously-mentioned 80C / HRA / etc."""
    return list(st.session_state.get("_last_calc_deductions", []) or [])


def try_tax_calculator(query):
    """If `query` is a numeric tax question, return a computed answer + an
    inheritance note. Else return None.
    """
    has_intent = _looks_like_tax_question(query)
    follow_up  = _last_turn_was_tax_calc()
    if not (has_intent or follow_up):
        return None
    gross = _extract_salary(query)
    if not gross or gross < 100000:
        return None

    deductions = _extract_deductions(query)
    inherited_note = ""
    # If this is a follow-up and the user didn't restate any deductions,
    # carry over the deductions from the previous tax-calc turn.
    if follow_up and not deductions:
        inherited = _last_calc_deductions()
        if inherited:
            deductions = inherited
            names = ", ".join(d["name"] for d in inherited)
            inherited_note = (
                f"\n\n_\u2139\ufe0f Re-using deductions from your previous question: "
                f"{names}. Mention different amounts in your next question to override._"
            )

    new_r = _compute_regime_breakup(gross, "New", deductions)
    old_r = _compute_regime_breakup(gross, "Old", deductions)
    answer = _render_calc_answer(gross, new_r, old_r, deductions) + inherited_note

    # Remember the deductions for the next follow-up turn
    st.session_state["_last_calc_deductions"] = deductions
    return answer


def submit_query(query):
    # 1. Try the live tax calculator first — if it produces a numeric answer,
    #    return it directly without going through FAQ search.
    calc_answer = try_tax_calculator(query)
    if calc_answer is not None:
        st.session_state.chat_history.append({
            "query": query,
            "type": "answer",
            "answer": calc_answer,
            "similarity": 1.0,
            "source": "Live Tax Calculator",
        })
        # Log as a successful, in-record answer
        try:
            _ensure_query_log_table()
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO query_log (
                    asked_at, employee_id, employee_name, query,
                    matched, in_record, matched_faq_id, matched_category,
                    matched_question, similarity, response_type, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    str(st.session_state.get("employee_id", "") or ""),
                    str(st.session_state.get("employee_name", "") or ""),
                    str(query)[:1000],
                    1, 1, "calc", "Tax Calculator", "Tax computation",
                    1.0, "answer", "Live Tax Calculator",
                ),
            )
            conn.commit(); conn.close()
        except Exception:
            pass
        return

    # 2. Chitchat / out-of-scope — let the AI answer casually (with banner).
    if _looks_like_chitchat(query):
        ans, _ai = generate_chitchat_response(query)
        st.session_state.chat_history.append({
            "query": query, "type": "answer",
            "answer": ans, "similarity": 0.0,
            "source": "AI (chitchat)", "ai_generated": True,
            "chitchat": True,
        })
        log_query(query, "answer", None, 0.0)
        return

    # 3. Otherwise — strict KB-grounded answer via semantic search.
    results = semantic_search(query)
    not_found_msg = (
        "This is not in our records. Please contact the Tax team at "
        "tax@koenig-solutions.com."
    )
    if results.empty:
        st.session_state.chat_history.append({
            "query": query, "type": "not_found",
            "answer": "Knowledge base is not loaded. " + not_found_msg,
            "similarity": 0, "source": "",
        })
        log_query(query, "not_found", None, 0)
        return
    top = results.iloc[0]
    sim = float(top.get("similarity", 0))

    # If the best match is too weak, refuse to guess.
    if sim < QUERY_LOG_MATCH_THRESHOLD:
        st.session_state.chat_history.append({
            "query": query, "type": "not_found",
            "answer": not_found_msg,
            "similarity": sim, "source": safe_get(top, "Source"),
        })
        log_query(query, "not_found", top, sim)
        return

    # Protected route
    if is_protected(top):
        spoc, email = get_spoc(top)
        st.session_state.chat_history.append({
            "query": query, "type": "protected",
            "answer": "This information is protected and cannot be displayed here.",
            "spoc": spoc, "email": email,
            "similarity": sim, "source": safe_get(top, "Source"),
        })
        log_query(query, "protected", top, sim)
        return

    # Confident match — strict KB-grounded answer (may be AI-paraphrased).
    ans, ai_used = generate_response(query, results)
    st.session_state.chat_history.append({
        "query": query, "type": "answer",
        "answer": ans, "similarity": sim,
        "source": safe_get(top, "Source"),
        "ai_generated": ai_used,
    })
    log_query(query, "answer", top, sim)


# =====================================================
# PAYROLL + TAX DATABASE FOUNDATION
# =====================================================

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def add_column_if_missing(cur, table_name, column_name, column_definition):
    cur.execute(f"PRAGMA table_info({table_name})")
    existing_columns = [row[1] for row in cur.fetchall()]

    if column_name not in existing_columns:
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def _drop_legacy_payroll_tables_once():
    """One-time cleanup: drop the obsolete payroll/declaration tables that were
    removed in May 2026.

    Tables: employee_master, employee_salary_monthly, employee_pli_monthly,
            employee_tds_monthly, employee_tax_computation, employee_investments,
            salary_structure_master.

    Idempotent and safe — each table is dropped via DROP TABLE IF EXISTS.
    """
    if st.session_state.get("_legacy_tables_dropped"):
        return
    st.session_state["_legacy_tables_dropped"] = True
    legacy_tables = [
        "employee_master",
        "employee_salary_monthly",
        "employee_pli_monthly",
        "employee_tds_monthly",
        "employee_tax_computation",
        "employee_investments",
        "salary_structure_master",
    ]
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        for t in legacy_tables:
            try:
                cur.execute(f"DROP TABLE IF EXISTS {t}")
            except Exception:
                pass
        conn.commit()
        conn.close()
    except Exception:
        pass


# Run the one-time drop on every fresh session — cheap, idempotent.
_drop_legacy_payroll_tables_once()


def _ensure_audit_log_table():
    """Create the audit_log table if it does not yet exist. Idempotent."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                actor_id TEXT,
                actor_role TEXT,
                action TEXT,
                target_id TEXT,
                details TEXT
            )"""
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log(timestamp)")
        conn.commit()
        conn.close()
    except Exception:
        pass


def write_audit_log(action, target_id="", details=""):
    """Record a sensitive action. Best-effort — never raises."""
    try:
        _ensure_audit_log_table()
        actor_id = str(st.session_state.get("employee_id", "") or "")
        actor_role = str(st.session_state.get("role", "") or "")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO audit_log (timestamp, actor_id, actor_role, action, target_id, details)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                actor_id,
                actor_role,
                str(action)[:120],
                str(target_id)[:120],
                str(details)[:500],
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass




def normalize_header(value):
    return (
        str(value)
        .strip()
        .lower()
        .replace("\n", " ")
        .replace("\r", " ")
        .replace(".", "")
        .replace("_", " ")
        .replace("-", " ")
    )


# Aliases shorter than this won't be matched as substrings to prevent
# accidental matches like "OT" -> "TotalDays".
_MIN_FUZZY_LEN = 4


def find_column(df, possible_names, exact_only=False):
    """Resolve a logical column to its actual Excel header.

    Strategy:
      1. Exact match on normalized headers (case + punctuation insensitive).
      2. Fuzzy substring match — BUT only for aliases of length >= 4 to avoid
         false positives like "OT" matching "TotalDays" or "PF" matching
         "BasicPercent". Short aliases must match exactly.

    Pass exact_only=True to disable fuzzy matching entirely (use when a column
    name like "Total Income From Salary" could be confused with a shorter
    header like "Salary").
    """
    normalized_cols = {normalize_header(c): c for c in df.columns}
    possible_norm = [normalize_header(x) for x in possible_names]

    # Pass 1: exact match
    for p in possible_norm:
        if p in normalized_cols:
            return normalized_cols[p]

    if exact_only:
        return None

    # Pass 2: fuzzy substring match, but only for sufficiently long aliases
    for p in possible_norm:
        if len(p) < _MIN_FUZZY_LEN:
            continue
        for norm_col, original_col in normalized_cols.items():
            if p in norm_col or norm_col in p:
                return original_col

    return None


def money_value(row, col):
    if not col:
        return 0.0
    try:
        value = row.get(col, 0)
        if pd.isna(value):
            return 0.0
        return float(str(value).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


def text_value(row, col):
    if not col:
        return ""
    try:
        value = row.get(col, "")
        if pd.isna(value):
            return ""
        return str(value).strip()
    except Exception:
        return ""


def normalize_employee_id(value):
    """Normalize Employee ID to a clean string.

    Rules:
    - NaN / None / blanks → ""
    - Strip whitespace
    - Strip trailing ".0" from floats read by pandas (e.g. 1086.0 → "1086")
    - Strip leading zeros from purely numeric IDs (e.g. "00123" → "123")
      (only if result is still non-empty; preserves "0" as "0")
    - Preserves alphanumeric IDs as-is (e.g. "EMP-001" stays "EMP-001")
    """
    try:
        if value is None:
            return ""
        if isinstance(value, float) and pd.isna(value):
            return ""
        # Handle numeric types (int/float) cleanly
        if isinstance(value, float):
            if value.is_integer():
                return str(int(value))
            return str(value).strip()
        if isinstance(value, int):
            return str(value)
        s = str(value).strip()
        if not s or s.lower() in ("nan", "none", "null"):
            return ""
        # Strip trailing ".0" pattern (e.g. "1086.0")
        if s.endswith(".0"):
            head = s[:-2]
            if head.lstrip("-").isdigit():
                s = head
        # Strip leading zeros only for purely numeric strings, but keep "0"
        if s.isdigit():
            stripped = s.lstrip("0")
            s = stripped if stripped else "0"
        return s
    except Exception:
        return ""


def employee_id_value(row, col):
    """Read and normalize an Employee ID from a dataframe row."""
    if not col:
        return ""
    try:
        return normalize_employee_id(row.get(col, ""))
    except Exception:
        return ""


















# ---- Standard month helpers (Indian Financial Year: April → March) ----
FY_MONTHS = [
    "April", "May", "June", "July", "August", "September",
    "October", "November", "December", "January", "February", "March"
]






# ---- Excel template builder for upload panels ----
UPLOAD_TEMPLATES = {
    "Employee Master": [
        "Employee ID", "Employee Name", "Tax Regime", "PAN No", "Gender",
        "Date of Joining", "Date of Exit", "DOB", "Designation"
    ],
    "Salary Computation": [
        "Employee ID", "Employee Name", "Gross Salary", "Basic", "HRA",
        "Sodexo / Meal Passes", "Telephone / Internet", "Electricity Reimbursement",
        "Professional / Software", "Skill Development", "Power & Utility Allowance",
        "Taxable Allowance", "OT / PLI / Profit Sharing", "Ex-Gratia",
        "Gratuity", "Severance", "Leave Encashment", "Referral Bonus",
        "Other Adjustment", "Total Income from Salary"
    ],
    "PLI / Incentive": [
        "Employee ID", "Employee Name", "PLI", "Incentive",
        "Performance Bonus", "Profit Sharing", "Other Variable Pay",
        "Total Variable Pay", "Remarks"
    ],
    "TDS Deduction": [
        "Employee ID", "Employee Name", "TDS Deducted",
        "Total Tax", "Cess 4%", "Total Tax After Cess",
        "Total Deduction", "Net Deductible"
    ],
}








# ----- Preview helpers: hide internal columns, prettify headers -----

# Columns hidden from the user-facing preview (internal book-keeping)
_HIDDEN_PREVIEW_COLS = {"id", "created_at", "updated_at"}

# Map of raw DB column → pretty display label
_PRETTY_PREVIEW_LABELS = {
    "employee_id": "Employee ID",
    "employee_name": "Employee Name",
    "financial_year": "Tax Year",
    "salary_month": "Month",
    "tax_regime": "Tax Regime",
    "pan_no": "PAN No.",
    "date_of_joining": "Date of Joining",
    "doj": "Date of Joining",
    "date_of_exit": "Date of Exit",
    "doe": "Date of Exit",
    "dob": "DOB",
    "gender": "Gender",
    "designation": "Designation",
    "department": "Department",
    "branch": "Branch",
    "annual_salary": "Annual Salary",
    "monthly_salary": "Monthly Salary",
    "basic_percent": "Basic %",
    "upload_month": "Upload Month",
    "tax_year": "Tax Year",
    "status": "Status",
    "gross_salary": "Gross Salary",
    "basic": "Basic",
    "hra": "HRA",
    "sodexo_meal_passes": "Meal Passes / Sodexo",
    "telephone_internet": "Telephone / Internet",
    "electricity_reimbursement": "Electricity Reimbursement",
    "professional_software": "Professional / Software",
    "skill_development": "Skill Development",
    "power_utility_allowance": "Power & Utility Allowance",
    "taxable_allowance": "Taxable Allowance",
    "ot_pli_profit_sharing": "OT / PLI / Profit Sharing",
    "exgratia": "Ex-Gratia",
    "gratuity": "Gratuity",
    "severance": "Severance",
    "leave_encashment": "Leave Encashment",
    "referral_bonus": "Referral Bonus",
    "other_adjustment": "Other Adjustment",
    "total_income_from_salary": "Total Income from Salary",
    "pli_amount": "PLI Amount",
    "incentive_amount": "Incentive",
    "performance_bonus": "Performance Bonus",
    "profit_sharing": "Profit Sharing",
    "other_variable_pay": "Other Variable Pay",
    "total_variable_pay": "Total Variable Pay",
    "remarks": "Remarks",
    "tds_deducted": "TDS Deducted",
    "tax1": "Tax1",
    "tax2": "Tax2",
    "tax3": "Tax3",
    "tax4": "Tax4",
    "tax5": "Tax5",
    "uploaded_at": "Uploaded At",
    "computed_at": "Computed At",
    "email": "Email",
}








# =====================================================
# TAX COMPUTATION ENGINE
# Implements the 39-field tax computation per tax_cal.csv specification.
# Pulls from: Employee Master • Salary Monthly • PLI Monthly • TDS Monthly
# • Approved Employee Declarations.
# =====================================================

# Slabs as per the user's spec (Income Tax Act 2025, applicable from FY 2026-27)
NEW_REGIME_SLABS = [
    (400000, 0.00),    # Up to 4,00,000   — Nil
    (800000, 0.05),    # 4,00,001 – 8,00,000   — 5%
    (1200000, 0.10),   # 8,00,001 – 12,00,000  — 10%
    (1600000, 0.15),   # 12,00,001 – 16,00,000 — 15%
    (2000000, 0.20),   # 16,00,001 – 20,00,000 — 20%
    (2400000, 0.25),   # 20,00,001 – 24,00,000 — 25%
    (float("inf"), 0.30),  # Above 24,00,000      — 30%
]

OLD_REGIME_SLABS = [
    (250000, 0.00),    # Up to 2,50,000 — Nil
    (500000, 0.05),    # 2,50,001 – 5,00,000  — 5%
    (1000000, 0.20),   # 5,00,001 – 10,00,000 — 20%
    (float("inf"), 0.30),  # Above 10,00,000      — 30%
]

STD_DEDUCTION_NEW = 75000
STD_DEDUCTION_OLD = 50000
CESS_RATE = 0.04













































# =====================================================
# LOGOUT
# =====================================================

def logout():
    for key in ["logged_in","role","employee_id","employee_name","must_change_password","menu_open","selected_module","chat_history","show_change_password"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()







# =====================================================
# VOICE FEATURES REMOVED (per user request, May 2026)
# Voice recording / TTS / speak buttons were taken out so Strides is
# text-only. The helper below is kept as a stub so any lingering reference
# (e.g., from cached session state) does not crash.
# =====================================================

def _voice_disabled_stub(*args, **kwargs):  # pragma: no cover - safety stub
    return None


def _unused_transcribe_audio_with_openai(audio_bytes):
    if client is None:
        return "", "OpenAI API key not available. Please add OPENAI_API_KEY in Streamlit Secrets."

    try:
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "sarika_voice_input.wav"

        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="en",
            prompt=(
                "Indian English speaker. Common terms: HRA, NPS, Section 80C, "
                "Form 16, Form 12B, Form 12BB, Sodexo, Koenig, Stride, Strides, "
                "SPOC, TDS, PAN, CTC, Rupees, lakh, crore."
            ),
        )

        return transcript.text, ""

    except Exception as e:
        return "", str(e)


def _unused_speak_button_html(text, button_label="🔊 Speak Reply"):
    safe_text = html.escape(str(text)).replace("\\n", " ")

    return f"""
    <button onclick="
        const msg = new SpeechSynthesisUtterance(`{safe_text}`);
        msg.lang = 'en-IN';
        msg.rate = 0.95;
        msg.pitch = 1.02;
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(msg);
    " style="
        background:#155be8;
        color:white;
        border:none;
        border-radius:10px;
        padding:9px 14px;
        font-weight:700;
        cursor:pointer;
        margin-top:6px;
    ">
        {button_label}
    </button>
    """


def _unused_render_voice_sarika_panel():
    st.markdown("### 🎙️ Voice Assistant")
    st.caption("Record your question, then click **Transcribe & Ask Strides**.")

    if client is None:
        st.warning("Voice transcription needs OPENAI_API_KEY in Streamlit Secrets.")
        st.info("Text chat will still work below.")
        return

    if not hasattr(st, "audio_input"):
        st.error("Your Streamlit version does not support native audio recording.")
        st.info("Please use Streamlit version 1.40.0 or later in requirements.txt.")
        return

    audio_file = st.audio_input(
        "Record your question here",
        key="sarika_native_audio_input"
    )

    if audio_file is not None:
        audio_bytes = audio_file.getvalue()
        st.audio(audio_bytes, format="audio/wav")

        if st.button("📝 Transcribe & Ask Strides", use_container_width=True, key="voice_transcribe_ask_btn"):
            with st.spinner("Strides is listening and thinking..."):
                transcript, err = transcribe_audio_with_openai(audio_bytes)

                if err:
                    st.error(f"Voice transcription failed: {err}")
                elif not transcript.strip():
                    st.warning("No speech detected. Please try again.")
                else:
                    st.success(f"You said: {transcript}")
                    submit_query(transcript.strip())
                    st.rerun()

    # Voice TTS removed — stub left intentionally empty.
    return


# =====================================================
# ADMIN ANALYTICS DASHBOARD
# =====================================================

def render_question_analytics():
    """Admin panel: shows what employees ask Strides, what's in record vs not."""
    st.markdown("## 📊 Question Analytics")
    st.caption(
                "Every question asked in **Ask Strides** is logged here. Use this view to see what's well-covered "
        "by the FAQ knowledge base and what topics need new FAQ rows."
    )

    _ensure_query_log_table()
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(
            "SELECT * FROM query_log ORDER BY asked_at DESC",
            conn,
        )
        conn.close()
    except Exception as e:
        st.error(f"Could not load query log: {e}")
        return

    if df.empty:
        st.info("No questions have been asked yet. Once employees use Ask Strides, their queries will appear here.")
        return

    # ---- Date range filter ----
    fc1, fc2, fc3 = st.columns([1, 1, 2])
    with fc1:
        date_window = st.selectbox(
            "Time window",
            ["Last 7 days", "Last 30 days", "Last 90 days", "All time"],
            index=1,
            key="qlog_window",
        )
    days_map = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90, "All time": None}
    days = days_map[date_window]
    if days:
        cutoff = (datetime.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        df_f = df[df["asked_at"] >= cutoff].copy()
    else:
        df_f = df.copy()

    with fc2:
        view_mode = st.selectbox(
            "Show",
            ["All queries", "In record only", "Not in record only"],
            key="qlog_view",
        )
    if view_mode == "In record only":
        df_v = df_f[df_f["in_record"] == 1]
    elif view_mode == "Not in record only":
        df_v = df_f[df_f["in_record"] == 0]
    else:
        df_v = df_f

    # ---- KPI cards ----
    total = len(df_f)
    in_rec = int(df_f["in_record"].sum())
    not_in_rec = total - in_rec
    pct = (in_rec / total * 100) if total else 0
    unique_q = df_f["query"].str.lower().str.strip().nunique()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total questions", f"{total:,}")
    k2.metric("In record (FAQ match)", f"{in_rec:,}", f"{pct:.1f}%")
    k3.metric("Not in record", f"{not_in_rec:,}", f"{100-pct:.1f}%" if total else "0%")
    k4.metric("Unique questions", f"{unique_q:,}")

    st.markdown("---")

    # ---- Daily volume chart ----
    if total and days:
        df_daily = df_f.copy()
        df_daily["date"] = pd.to_datetime(df_daily["asked_at"], errors="coerce").dt.date
        chart_df = (
            df_daily.groupby("date")
            .agg(in_record=("in_record", "sum"), total=("id", "count"))
            .reset_index()
        )
        chart_df["not_in_record"] = chart_df["total"] - chart_df["in_record"]
        chart_df = chart_df.set_index("date")[["in_record", "not_in_record"]]
        st.markdown("### 📈 Daily volume")
        st.bar_chart(chart_df, height=220)

    # ---- Top matched FAQs ----
    cA, cB = st.columns(2)
    with cA:
        st.markdown("### 🏆 Top FAQs answered")
        top_faqs = (
            df_f[df_f["in_record"] == 1]
            .groupby(["matched_faq_id", "matched_category", "matched_question"], dropna=False)
            .size().reset_index(name="hits")
            .sort_values("hits", ascending=False)
            .head(15)
            .rename(columns={
                "matched_faq_id": "FAQ ID",
                "matched_category": "Category",
                "matched_question": "Question",
                "hits": "Hits",
            })
        )
        if top_faqs.empty:
            st.info("No in-record matches yet in this window.")
        else:
            st.dataframe(top_faqs, hide_index=True, use_container_width=True)

    with cB:
        st.markdown("### 📊 Category coverage")
        cat_df = (
            df_f[df_f["in_record"] == 1]
            .groupby("matched_category")
            .size().reset_index(name="hits")
            .sort_values("hits", ascending=False)
            .rename(columns={"matched_category": "Category", "hits": "Hits"})
        )
        if cat_df.empty:
            st.info("No category data yet.")
        else:
            st.dataframe(cat_df, hide_index=True, use_container_width=True)

    st.markdown("---")

    # ---- Not in record (the actionable list) ----
    st.markdown("### ❗ Questions NOT in record (future FAQ candidates)")
    st.caption(
        "These are questions where Strides could not find a confident FAQ match. "
        "Review them, decide which to convert into new FAQ entries, and add to **Salary & Tax FAQs**."
    )

    gap_df = df_f[df_f["in_record"] == 0].copy()
    if gap_df.empty:
        st.success("🎉 Every question in this window was answered from the FAQ base — no gaps to fix.")
    else:
        # group near-duplicates by lower-cased query text
        gap_df["q_norm"] = gap_df["query"].astype(str).str.lower().str.strip()
        grouped = (
            gap_df.groupby("q_norm")
            .agg(
                Times_Asked=("id", "count"),
                Sample_Question=("query", "first"),
                Last_Asked=("asked_at", "max"),
                Avg_Similarity=("similarity", "mean"),
                Last_Response_Type=("response_type", "last"),
            )
            .reset_index(drop=True)
            .sort_values(["Times_Asked", "Last_Asked"], ascending=[False, False])
        )
        grouped["Avg_Similarity"] = grouped["Avg_Similarity"].round(3)
        st.dataframe(grouped, hide_index=True, use_container_width=True)

        # CSV download for FAQ team
        csv_bytes = grouped.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download as CSV (for FAQ team)",
            data=csv_bytes,
            file_name=f"strides_unanswered_questions_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

    st.markdown("---")

    # ---- Raw log (collapsed) ----
    with st.expander("📜 Raw query log (latest 200 rows)"):
        display_cols = [
            "asked_at", "employee_id", "employee_name", "query",
            "in_record", "response_type", "similarity",
            "matched_faq_id", "matched_category", "matched_question",
        ]
        existing = [c for c in display_cols if c in df_v.columns]
        st.dataframe(df_v[existing].head(200), hide_index=True, use_container_width=True)

        # Maintenance
        st.markdown("---")
        st.caption("Maintenance")
        c1, c2 = st.columns(2)
        with c1:
            full_csv = df_v.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download full filtered log (CSV)",
                data=full_csv,
                file_name=f"strides_query_log_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        with c2:
            if st.button("🗑️ Clear query log (irreversible)", key="qlog_clear"):
                try:
                    conn = sqlite3.connect(DB_PATH)
                    cur = conn.cursor()
                    cur.execute("DELETE FROM query_log")
                    conn.commit()
                    conn.close()
                    st.success("Query log cleared.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not clear log: {e}")


def render_home_admin_charts():
    """Admin-only mini-dashboard shown on the Home panel.

    Four KPIs:
      1. Total questions asked
      2. Not available in record (gap)
      3. Diverted to SPOC (protected answers)
      4. Tax FAQs vs Entity Nexus split

    Plus a small bar chart visualising the breakdown.
    """
    st.markdown("---")
    st.markdown("### 📊 Strides usage at a glance")
    st.caption("Admin view — live numbers from the Ask Strides query log.")

    try:
        _ensure_query_log_table()
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(
            "SELECT query, in_record, response_type, source FROM query_log",
            conn,
        )
        conn.close()
    except Exception as e:
        st.info(f"Query log not yet available ({e}).")
        return

    if df.empty:
        st.info("No questions logged yet. Metrics will appear once employees start using Ask Strides.")
        return

    total          = len(df)
    not_in_record  = int((df["in_record"] == 0).sum())
    diverted_spoc  = int((df["response_type"] == "protected").sum())

    src_lower      = df["source"].astype(str).str.lower()
    tax_count      = int((df["in_record"] == 1)
                         .where(src_lower.str.contains("tax"), False).sum())
    nexus_count    = int((df["in_record"] == 1)
                         .where(src_lower.str.contains("entity"), False).sum())

    # ---- KPI cards ----
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💬 Total questions asked", f"{total:,}")
    c2.metric("❓ Not in record",         f"{not_in_record:,}",
              f"{(not_in_record/total*100):.1f}%" if total else "0%")
    c3.metric("📞 Diverted to SPOC",     f"{diverted_spoc:,}")
    c4.metric("🧾 Tax / 🏢 Entity Nexus",
              f"{tax_count:,} / {nexus_count:,}")

    # ---- Combined breakdown chart ----
    chart_df = pd.DataFrame({
        "Category": [
            "Tax FAQs",
            "Entity Nexus",
            "Diverted to SPOC",
            "Not in record",
        ],
        "Questions": [
            tax_count,
            nexus_count,
            diverted_spoc,
            not_in_record,
        ],
    })
    if chart_df["Questions"].sum() > 0:
        st.bar_chart(chart_df.set_index("Category"), height=240)
    st.caption(
        "Open **Question Analytics** in the sidebar for the full query log, "
        "daily volume trend, and the list of unanswered questions to add as new FAQs."
    )


def render_admin_analytics_dashboard():
    """High-level admin analytics: users, knowledge base, storage, audit log."""
    st.markdown("## 📈 Admin Analytics")
    st.caption("Overview of platform usage and data health.")

    # ---------------- Users ----------------
    try:
        users_df = load_users()
        total_users = len(users_df)
        admins = int((users_df["role"].astype(str).str.lower() == "admin").sum())
        employees = int((users_df["role"].astype(str).str.lower() == "employee").sum())
        active_users = int(users_df["active"].astype(str).str.lower().isin(["true", "1", "yes", "y"]).sum())
    except Exception:
        total_users = admins = employees = active_users = 0

    st.markdown("### 👥 Users")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Users", total_users)
    c2.metric("Active", active_users)
    c3.metric("Employees", employees)
    c4.metric("Admins", admins)

    # ---------------- Knowledge base ----------------
    st.markdown("### 📚 Knowledge Base")
    try:
        kb_total = len(faq_df) if not faq_df.empty else 0
        kb_protected = int(faq_df["Protected"].astype(str).str.lower().isin(["yes", "y", "true"]).sum()) if not faq_df.empty and "Protected" in faq_df.columns else 0
        spoc_total = len(spoc_df) if not spoc_df.empty else 0
    except Exception:
        kb_total = kb_protected = spoc_total = 0

    k1, k2, k3 = st.columns(3)
    k1.metric("FAQ Records", kb_total)
    k2.metric("Protected Records", kb_protected)
    k3.metric("SPOC Master Rows", spoc_total)

    if not faq_df.empty and "Main Module" in faq_df.columns:
        with st.expander("📊 FAQs by Module", expanded=False):
            module_counts = faq_df["Main Module"].value_counts().reset_index()
            module_counts.columns = ["Module", "Count"]
            st.dataframe(module_counts, use_container_width=True, hide_index=True)
            try:
                st.bar_chart(module_counts.set_index("Module"))
            except Exception:
                pass

    # ---------------- Storage health (Streamlit Cloud warning) ----------------
    st.markdown("### ⚠️ Storage Health")
    try:
        db_size = DB_PATH.stat().st_size / 1024 if DB_PATH.exists() else 0
    except Exception:
        db_size = 0
    s1, _ = st.columns(2)
    s1.metric("SQLite DB size", f"{db_size:,.1f} KB")
    st.warning(
        "⚠️ **Streamlit Cloud filesystem is ephemeral.** SQLite data will be "
        "wiped on container restart. Plan a Postgres migration before going live."
    )

    # ---------------- Audit log ----------------
    st.markdown("### 🔍 Recent Audit Log (last 100)")
    try:
        conn = get_db_connection()
        audit_df = pd.read_sql_query(
            "SELECT timestamp, actor_id, actor_role, action, target_id, details "
            "FROM audit_log ORDER BY id DESC LIMIT 100",
            conn,
        )
        conn.close()
        if audit_df.empty:
            st.info("No audit events recorded yet.")
        else:
            st.dataframe(audit_df, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Download full audit log (.csv)",
                audit_df.to_csv(index=False).encode("utf-8"),
                file_name="koenig_stride_audit_log.csv",
                mime="text/csv",
                use_container_width=True,
            )
    except Exception as e:
        st.caption(f"Audit log not available: {e}")


# =====================================================
# PANEL NAVIGATION
# =====================================================

def set_panel(panel_name):
    st.session_state.selected_panel = panel_name
    if panel_name == "Start Here":
        st.session_state.start_completed = True

def panel_button(label, panel_name):
    active = st.session_state.get("selected_panel", "Home") == panel_name
    prefix = "🔵 " if active else ""
    if st.button(prefix + label, use_container_width=True, key=f"nav_{panel_name}"):
        set_panel(panel_name)
        st.rerun()


# =====================================================
# APP HEADER
# =====================================================

top1, top2, top3 = st.columns([1.2, 3, 1.5], gap="large")
with top1:
    if LOGO_B64:
        st.markdown(img_html(LOGO_B64, "logo-img"), unsafe_allow_html=True)
    else:
        st.markdown("## KOENIG")
with top2:
    st.markdown("""
    <div class='brand-row'>
        <div class='bot-icon'>☻</div>
        <h1 class='brand-title'>Koenig Stride</h1>
    </div>
    <div class='brand-subtitle'>Tax & Entity Nexus Assistant — Step Forward</div>
    """, unsafe_allow_html=True)
with top3:
    st.markdown(f"""
    <div class='user-pill'>
        👤 {st.session_state.employee_name}<br>
        <span class='small-text'>Role: {st.session_state.role} · ID: {st.session_state.employee_id}</span>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Logout", use_container_width=True):
        logout()

if load_error:
    st.error(load_error)

# =====================================================
# MAIN
# =====================================================

left, right = st.columns([1.05, 3.6], gap="large")

with left:
    st.markdown("<div class='card' style='text-align:center;'>", unsafe_allow_html=True)
    if SARIKA_B64:
        st.markdown(img_html(SARIKA_B64, "avatar-img"), unsafe_allow_html=True)
    st.markdown("<h3>👩‍💼 Strides</h3>", unsafe_allow_html=True)
    st.markdown("<div class='online'>● Strides is online</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### 📌 Panels")

    panel_button("🏠 Home", "Home")
    panel_button("🚀 Start Here", "Start Here")
    panel_button("👤 Account", "Account")

    if st.session_state.get("start_completed", False):
        st.markdown("---")
        st.markdown("### 🤖 Assistant")
        panel_button("💬 Ask Strides", "Ask Strides")

        if st.session_state.role == "Admin":
            st.markdown("---")
            st.markdown("### 🛠️ Admin")
            panel_button("👥 User Management", "User Management")
            panel_button("📚 Knowledge Base", "Knowledge Base")
            panel_button("📊 Question Analytics", "Question Analytics")
            panel_button("📈 Admin Analytics", "Admin Analytics")

with right:
    selected_panel = st.session_state.get("selected_panel", "Home")

    locked_panels = [
        "Ask Strides", "User Management",
        "Knowledge Base", "Question Analytics", "Admin Analytics"
    ]

    if selected_panel in locked_panels and not st.session_state.get("start_completed", False):
        # Silent redirect was confusing for users — explain what happened.
        st.info("👋 Please click **🚀 Start Here** first to unlock this panel.")
        selected_panel = "Home"
        st.session_state.selected_panel = "Home"

    # =====================================================
    # HOME PANEL
    # =====================================================
    if selected_panel == "Home":
        st.markdown("""
        <div class='hero' style='margin-top:24px;'>
            <h2>Welcome to Koenig Stride</h2>
            <p>Select a panel from the left sidebar,<br>or use Ask Strides to ask directly.</p>
        </div>
        """, unsafe_allow_html=True)
        st.info(
            "👉 Click **🚀 Start Here** in the left sidebar to unlock Ask Strides "
            "and the Tax FAQ explorer."
        )

        # ---- Admin-only mini-dashboard on Home ----
        if st.session_state.role == "Admin":
            render_home_admin_charts()


    # =====================================================
    # START HERE PANEL
    # =====================================================
    elif selected_panel == "Start Here":
        st.session_state.start_completed = True
        st.markdown("## 🚀 Start Here")
        st.success("Assistant panels are now available in the left sidebar, including Ask Strides.")
        if st.button("💬 Open Ask Strides", use_container_width=True):
            st.session_state.selected_panel = "Ask Strides"
            st.rerun()
        st.markdown("Select an area below, then choose a category and question.")

        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("### Select Area")
        modules = [
            ("✅ Tax FAQs", "Tax FAQs"),
            ("✅ Salary Queries", "Salary Queries"),
            ("⚖️ Labour Code", "Labour Code"),
            ("✅ Entity Nexus", "Entity Nexus"),
            ("📞 SPOC", "SPOC"),
            ("🔒 Protected Information Routing", "Protected Information Routing"),
            ("✅ Compliance Support", "Compliance Support"),
        ]
        rows = [st.columns(2), st.columns(2), st.columns(2), st.columns(1)]
        flat_cols = rows[0] + rows[1] + rows[2] + rows[3]
        for i, (label, module_name) in enumerate(modules):
            with flat_cols[i]:
                if st.button(label, key=f"module_{i}", use_container_width=True):
                    st.session_state.selected_module = module_name
        st.markdown("</div>", unsafe_allow_html=True)

        if st.session_state.selected_module:
            selected = st.session_state.selected_module

            # SPOC — show the SPOC directory directly (no category browsing).
            if selected in ("SPOC", "SPOC Routing"):  # accept legacy value too
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.markdown(f"<span class='selected-pill'>Selected: {selected}</span>", unsafe_allow_html=True)
                st.markdown("### 📞 SPOC Directory")
                render_spoc_routing()
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.markdown(f"<span class='selected-pill'>Selected: {selected}</span>", unsafe_allow_html=True)
                st.markdown("### Select Category")
                categories = get_categories_for_module(faq_df, selected)
                if categories:
                    for category in categories:
                        cat_df = get_questions_by_module_category(faq_df, selected, category)
                        if cat_df.empty:
                            continue
                        with st.expander(f"📂 {category} ({len(cat_df)} questions)", expanded=False):
                            q_col = get_question_column(cat_df)
                            for _, row in cat_df.iterrows():
                                question = safe_get(row, q_col or "Question")
                                if not question:
                                    continue
                                with st.expander(f"❓ {question}", expanded=False):
                                    render_answer(row)
                else:
                    st.info("No categories found under this section. Please check the Category column in Excel.")
                st.markdown("</div>", unsafe_allow_html=True)

    # =====================================================
    # ACCOUNT PANEL
    # =====================================================
    elif selected_panel == "Account":
        st.markdown("## 👤 Account")
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.write(f"**Name:** {st.session_state.employee_name}")
        st.write(f"**Role:** {st.session_state.role}")
        st.write(f"**Employee ID:** {st.session_state.employee_id}")
        st.markdown("---")
        st.markdown("### Change Password")

        old_password = st.text_input("Current Password", type="password", key="account_old_pwd")
        new_password = st.text_input("New Password", type="password", key="account_new_pwd")
        confirm_password = st.text_input("Confirm Password", type="password", key="account_confirm_pwd")

        if st.button("Update My Password", use_container_width=True):
            ok, msg, row = authenticate_user(st.session_state.employee_id, old_password)
            if not ok:
                st.error("Current password is incorrect.")
            elif new_password != confirm_password:
                st.error("New password and confirm password do not match.")
            else:
                valid, vmsg = validate_password_strength(new_password)
                if not valid:
                    st.error(vmsg)
                else:
                    update_user_password(st.session_state.employee_id, new_password, first_login=False)
                    st.success("Password changed successfully.")
        st.markdown("</div>", unsafe_allow_html=True)

    # =====================================================
    # ASK STRIDES PANEL (formerly Ask Sarika)
    # =====================================================
    elif selected_panel in ("Ask Strides", "Ask Sarika"):  # legacy panel name supported
        st.markdown("## 💬 Ask Strides")
        st.markdown(
            "<div style='color:#64748b; font-size:13px; margin-top:-8px; margin-bottom:12px;'>"
            "Chat with Strides — your AI assistant for tax, salary, labour code, entity nexus and SPOC queries."
            "</div>",
            unsafe_allow_html=True
        )

        # ----- Chat history (newest at the bottom, like real chat apps) -----
        chat_container = st.container()
        with chat_container:
            if not st.session_state.chat_history:
                with st.chat_message("assistant", avatar="👩‍💼"):
                    st.markdown(
                        f"Hi **{st.session_state.employee_name}** 👋  \n"
                        "I'm **Strides**, your Koenig Stride assistant. "
                        "Ask me anything about **Tax, Salary, Labour Code, Entity Nexus** or **SPOC routing**."
                    )
            else:
                for item in st.session_state.chat_history[-30:]:
                    with st.chat_message("user", avatar="👤"):
                        st.markdown(item["query"])

                    with st.chat_message("assistant", avatar="👩‍💼"):
                        if item["type"] == "protected":
                            email_html = f"<br><b>Email:</b> {item.get('email','')}" if item.get("email") else ""
                            st.markdown(f"""
                            <div class='protected-box' style='margin:0;'>
                            <b>🔒 Protected Information</b><br>
                            {item['answer']}<br><br>
                            Please contact:<br>
                            <b>SPOC:</b> {item.get('spoc','Relevant SPOC')}
                            {email_html}
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            # Yellow banner for AI-generated answers (everything
                            # except the deterministic Live Tax Calculator).
                            st.markdown(item["answer"])
                            # Soft footnote on non-deterministic answers — no
                            # alarmist banner, just a gentle pointer if the user
                            # wants to double-check.
                            if item.get("ai_generated") and item.get("source") != "Live Tax Calculator" and not item.get("chitchat"):
                                st.markdown(
                                    "<div style='margin-top:8px;font-size:12px;color:#64748b;font-style:italic;'>"
                                    "If there is any doubt, you may verify with the Tax team at "
                                    "<a href='mailto:tax@koenig-solutions.com'>tax@koenig-solutions.com</a>."
                                    "</div>",
                                    unsafe_allow_html=True,
                                )

                        if st.session_state.role == "Admin":
                            st.caption(
                                f"Source: {item.get('source','')} · "
                                f"Similarity: {item.get('similarity',0):.2f}"
                            )

        # ----- Chat input at the bottom (widget-style, like ChatGPT/WhatsApp) -----
        user_query = st.chat_input("Type your question and press Enter… (e.g. What is NPS?)")
        if user_query and user_query.strip():
            with st.spinner("Strides is thinking…"):
                submit_query(user_query.strip())
            st.rerun()

        if st.session_state.chat_history:
            col_clear, _ = st.columns([1, 4])
            with col_clear:
                if st.button("🗑️ Clear chat", use_container_width=True, key="ask_strides_clear"):
                    st.session_state.chat_history = []
                    st.rerun()

    # =====================================================
    # ADMIN PANELS
    # =====================================================
    elif selected_panel == "User Management" and st.session_state.role == "Admin":
        st.markdown("## 👥 User Management")
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("### Reset Employee Password")
        reset_emp_id = st.text_input("Employee ID to reset", placeholder="Example: 1001")
        if st.button("Reset Employee Password to Welcome@123"):
            if reset_emp_id.strip().isdigit():
                reset_employee_password(reset_emp_id.strip())
                st.success(f"Password reset for Employee {reset_emp_id}. They must change it on next login.")
            else:
                st.error("Please enter a numeric Employee ID.")
        st.markdown("---")
        st.markdown("### Users")
        users_df = load_users()
        display_df = users_df[["user_id", "role", "first_login", "active", "display_name"]].copy()
        st.dataframe(display_df, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    elif selected_panel == "Knowledge Base" and st.session_state.role == "Admin":
        st.markdown("## 📚 Knowledge Base")
        if not faq_df.empty:
            st.success(f"Knowledge base loaded successfully. Total records: {len(faq_df)}")
            cols = [c for c in ["Main Module", "Source", "Category", "Question", "Protected", "SPOC Name", "SPOC Email"] if c in faq_df.columns]
            st.dataframe(faq_df[cols], use_container_width=True)
        else:
            st.warning("No knowledge records loaded.")

    elif selected_panel == "Question Analytics" and st.session_state.role == "Admin":
        render_question_analytics()

    elif selected_panel == "Admin Analytics" and st.session_state.role == "Admin":
        render_admin_analytics_dashboard()

    else:
        st.warning("You are not authorized to view this panel.")

# =====================================================
# ADMIN
# =====================================================

# Admin panels are now available from the left sidebar.
st.markdown("<div class='footer-line'><div>© 2025 Koenig Solutions Ltd. All rights reserved.</div><div>Privacy Policy &nbsp; | &nbsp; Terms of Use</div></div>", unsafe_allow_html=True)
