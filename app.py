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
import streamlit.components.v1 as components

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

BASE_DIR = Path(__file__).parent
EXCEL_PATH = BASE_DIR / "knowledge" / "Koenig_VoiceBot_FAQ_Master.xlsx"
LOGO_PATH = BASE_DIR / "assets" / "koenig_logo.png"
SARIKA_PATH = BASE_DIR / "assets" / "sarika.png"
USERS_PATH = BASE_DIR / "users.csv"
DB_PATH = BASE_DIR / "koenig_stride.db"
PROOF_FOLDER = BASE_DIR / "proof_uploads"
PROOF_FOLDER.mkdir(exist_ok=True)

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
.stDeployButton {
    display:none !important;
    visibility:hidden !important;
}

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

        login_type = st.radio("Login As", ["Employee", "Admin"], horizontal=True, label_visibility="visible")

        if login_type == "Employee":
            user_id = st.text_input("Employee ID", placeholder="Example: 1001")
            password = st.text_input("Password", type="password", placeholder="Default: Welcome@123")
            if st.button("Employee Login", use_container_width=True, type="primary"):
                if not user_id.strip().isdigit():
                    st.error("Please enter a valid numeric Employee ID.")
                elif not password:
                    st.error("Please enter password.")
                else:
                    ok, msg, row = authenticate_user(user_id, password)
                    if ok:
                        st.session_state.logged_in = True
                        st.session_state.role = "Employee"
                        st.session_state.employee_id = user_id.strip()
                        st.session_state.employee_name = row.get("display_name", f"Employee {user_id}")
                        st.session_state.must_change_password = bool_from_str(row.get("first_login", "False"))
                        try:
                            write_audit_log("LOGIN_SUCCESS", target_id=user_id.strip(), details="role=Employee")
                        except Exception:
                            pass
                        st.rerun()
                    else:
                        try:
                            write_audit_log("LOGIN_FAILED", target_id=user_id.strip(), details=f"role=Employee; reason={msg}")
                        except Exception:
                            pass
                        st.error(msg)
        else:
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
                        write_audit_log("LOGIN_SUCCESS", target_id="admin", details="role=Admin")
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

if not st.session_state.logged_in:
    login_screen()
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

def generate_response(query, results):
    top = results.iloc[0]
    if client is None:
        return get_answer_text(top)
    context = ""
    for _, row in results.iterrows():
        context += f"""
Question: {safe_get(row, 'Question')}
Answer: {get_answer_text(row)}
Protected: {safe_get(row, 'Protected')}
SPOC: {safe_get(row, 'SPOC Name')}
Email: {safe_get(row, 'SPOC Email')}
"""
    prompt = f"""
You are Koenig Stride, an internal Tax & Entity Nexus Assistant.
Use only the knowledge base below. Do not invent facts. If Protected is YES, do not reveal protected information and route employee to SPOC.

Knowledge Base:
{context}
"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":prompt},{"role":"user","content":query}],
            temperature=0.2
        )
        return resp.choices[0].message.content
    except Exception:
        return get_answer_text(top)

def submit_query(query):
    results = semantic_search(query)
    if results.empty:
        st.session_state.chat_history.append({"query":query,"type":"not_found","answer":"Knowledge base is not loaded.","similarity":0,"source":""})
        return
    top = results.iloc[0]
    sim = float(top.get("similarity", 0))
    if sim < 0.15:
        st.session_state.chat_history.append({"query":query,"type":"not_found","answer":"I could not find a relevant answer. Please try differently or contact the relevant SPOC.","similarity":sim,"source":safe_get(top,"Source")})
        return
    if is_protected(top):
        spoc, email = get_spoc(top)
        st.session_state.chat_history.append({"query":query,"type":"protected","answer":"This information is protected and cannot be displayed here.","spoc":spoc,"email":email,"similarity":sim,"source":safe_get(top,"Source")})
        return
    ans = generate_response(query, results)
    st.session_state.chat_history.append({"query":query,"type":"answer","answer":ans,"similarity":sim,"source":safe_get(top,"Source")})


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


@st.cache_resource(show_spinner=False)
def init_payroll_database():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS salary_structure_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            component_name TEXT NOT NULL UNIQUE,
            component_type TEXT DEFAULT 'Allowance',
            formula_type TEXT DEFAULT 'Fixed',
            percentage REAL DEFAULT 0,
            max_limit REAL DEFAULT 0,
            basis TEXT DEFAULT 'Yearly',
            taxable_status TEXT DEFAULT 'Taxable',
            proof_required INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            remarks TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        )
    """)

    # Upgrade old DB if table already existed from previous version
    add_column_if_missing(cur, "salary_structure_master", "proof_required", "INTEGER DEFAULT 0")
    add_column_if_missing(cur, "salary_structure_master", "enabled", "INTEGER DEFAULT 1")
    add_column_if_missing(cur, "salary_structure_master", "sort_order", "INTEGER DEFAULT 0")
    add_column_if_missing(cur, "salary_structure_master", "remarks", "TEXT DEFAULT ''")
    add_column_if_missing(cur, "salary_structure_master", "updated_at", "TEXT DEFAULT ''")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS employee_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT UNIQUE,
            employee_name TEXT,
            tax_regime TEXT,
            pan_no TEXT,
            gender TEXT,
            date_of_joining TEXT,
            date_of_exit TEXT,
            dob TEXT,
            designation TEXT,
            uploaded_at TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS employee_salary_monthly (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT,
            employee_name TEXT,
            financial_year TEXT,
            salary_month TEXT,
            gross_salary REAL DEFAULT 0,
            basic REAL DEFAULT 0,
            hra REAL DEFAULT 0,
            sodexo_meal_passes REAL DEFAULT 0,
            telephone_internet REAL DEFAULT 0,
            electricity_reimbursement REAL DEFAULT 0,
            professional_software REAL DEFAULT 0,
            skill_development REAL DEFAULT 0,
            power_utility_allowance REAL DEFAULT 0,
            taxable_allowance REAL DEFAULT 0,
            ot_pli_profit_sharing REAL DEFAULT 0,
            exgratia REAL DEFAULT 0,
            gratuity REAL DEFAULT 0,
            severance REAL DEFAULT 0,
            leave_encashment REAL DEFAULT 0,
            referral_bonus REAL DEFAULT 0,
            other_adjustment REAL DEFAULT 0,
            total_income_from_salary REAL DEFAULT 0,
            uploaded_at TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS employee_tds_monthly (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT,
            employee_name TEXT,
            financial_year TEXT,
            salary_month TEXT,
            tds_deducted REAL DEFAULT 0,
            tax1_total_tax REAL DEFAULT 0,
            tax2_cess_4_percent REAL DEFAULT 0,
            tax3_total_tax_after_cess REAL DEFAULT 0,
            tax4_total_deduction REAL DEFAULT 0,
            tax5_net_deductible REAL DEFAULT 0,
            uploaded_at TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS employee_investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT,
            employee_name TEXT,
            financial_year TEXT,
            declaration_type TEXT DEFAULT '',
            section TEXT DEFAULT '',
            investment_type TEXT DEFAULT '',
            claimed_amount REAL DEFAULT 0,
            approved_amount REAL DEFAULT 0,
            status TEXT DEFAULT 'Pending',
            proof_file TEXT DEFAULT '',
            employee_remarks TEXT DEFAULT '',
            admin_remarks TEXT DEFAULT '',
            submitted_at TEXT DEFAULT '',
            approved_at TEXT DEFAULT '',
            approved_by TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS employee_tax_computation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT,
            employee_name TEXT,
            financial_year TEXT,
            gross_annual_salary REAL DEFAULT 0,
            basic_salary REAL DEFAULT 0,
            hra REAL DEFAULT 0,
            sodexo_meal_passes REAL DEFAULT 0,
            telephone_internet REAL DEFAULT 0,
            electricity_reimbursement REAL DEFAULT 0,
            professional_software REAL DEFAULT 0,
            skill_development REAL DEFAULT 0,
            power_utility_allowance REAL DEFAULT 0,
            taxable_allowance REAL DEFAULT 0,
            bonus_incentive REAL DEFAULT 0,
            previous_employer_income_12b_12bb REAL DEFAULT 0,
            total_income_from_salary REAL DEFAULT 0,
            approved_allowances_reimbursements REAL DEFAULT 0,
            standard_deduction REAL DEFAULT 0,
            approved_investments REAL DEFAULT 0,
            home_loan_deduction REAL DEFAULT 0,
            other_eligible_deductions REAL DEFAULT 0,
            taxable_salary REAL DEFAULT 0,
            tax1_total_tax REAL DEFAULT 0,
            tax2_cess_4_percent REAL DEFAULT 0,
            tax3_total_tax_after_cess REAL DEFAULT 0,
            tax4_total_deduction REAL DEFAULT 0,
            tax5_net_deductible REAL DEFAULT 0,
            computed_at TEXT DEFAULT ''
        )
    """)

    # Audit log for sensitive actions (compliance / traceability)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT '',
            actor_id TEXT DEFAULT '',
            actor_role TEXT DEFAULT '',
            action TEXT DEFAULT '',
            target_id TEXT DEFAULT '',
            details TEXT DEFAULT ''
        )
    """)

    conn.commit()
    conn.close()
    seed_salary_structure_master()


def write_audit_log(action, target_id="", details=""):
    """Record a sensitive action. Best-effort — never raises."""
    try:
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


def seed_salary_structure_master():
    conn = get_db_connection()
    cur = conn.cursor()

    default_rows = [
        ("Basic", "Salary Component", "Manual / Upload", 0, 0, "Monthly", "Taxable", 0, 1, 1, "Base salary component"),
        ("HRA", "Allowance", "50% of Basic", 50, 0, "Monthly", "Partial", 0, 1, 2, "HRA = 50% of Basic"),
        ("Sodexo / Meal Passes", "Reimbursement", "Fixed", 0, 105600, "Yearly", "Conditional", 1, 1, 3, "Part of CTC; exempt up to approved declaration/proof amount"),
        ("Telephone / Internet", "Reimbursement", "Percentage", 3, 0, "Yearly", "Conditional", 1, 1, 4, "Exempt up to approved proof amount"),
        ("Electricity Reimbursement", "Reimbursement", "Percentage", 3, 0, "Yearly", "Conditional", 1, 1, 5, "Exempt up to approved proof amount"),
        ("Professional / Software", "Reimbursement", "Percentage", 2, 0, "Yearly", "Conditional", 1, 1, 6, "Exempt up to approved proof amount"),
        ("Skill Development", "Reimbursement", "Percentage", 2, 0, "Yearly", "Conditional", 1, 1, 7, "Exempt up to approved proof amount"),
        ("Power & Utility Allowance", "Allowance", "Percentage", 2, 0, "Yearly", "Conditional", 1, 1, 8, "Exempt up to approved proof amount"),
        ("Taxable Allowance", "Allowance", "Balance", 0, 0, "Monthly", "Taxable", 0, 1, 9, "Balance after configured components"),
        ("Meal Passes / Sodexo Declaration", "Deduction", "Fixed", 0, 105600, "Yearly", "Conditional", 1, 1, 10, "Employee declaration/deduction head for meal passes; editable"),
    ]

    for row in default_rows:
        cur.execute("""
            INSERT OR IGNORE INTO salary_structure_master (
                component_name, component_type, formula_type, percentage,
                max_limit, basis, taxable_status, proof_required,
                enabled, sort_order, remarks, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (*row, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    conn.close()


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


def find_column(df, possible_names):
    normalized_cols = {normalize_header(c): c for c in df.columns}
    possible_norm = [normalize_header(x) for x in possible_names]

    for p in possible_norm:
        if p in normalized_cols:
            return normalized_cols[p]

    for p in possible_norm:
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


def load_salary_structure_master():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM salary_structure_master ORDER BY sort_order, id", conn)
    conn.close()
    return df


def save_salary_structure_master(df):
    save_df = df.copy().fillna("")

    required_cols = [
        "component_name", "component_type", "formula_type", "percentage",
        "max_limit", "basis", "taxable_status", "proof_required",
        "enabled", "sort_order", "remarks"
    ]

    for col in required_cols:
        if col not in save_df.columns:
            save_df[col] = ""

    save_df["percentage"] = pd.to_numeric(save_df["percentage"], errors="coerce").fillna(0)
    save_df["max_limit"] = pd.to_numeric(save_df["max_limit"], errors="coerce").fillna(0)
    save_df["proof_required"] = save_df["proof_required"].apply(lambda x: 1 if str(x).lower() in ["1", "true", "yes", "required"] else 0)
    save_df["enabled"] = save_df["enabled"].apply(lambda x: 1 if str(x).lower() in ["1", "true", "yes", "enabled"] else 0)
    save_df["sort_order"] = pd.to_numeric(save_df["sort_order"], errors="coerce").fillna(0).astype(int)
    save_df["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM salary_structure_master")

    for _, row in save_df.iterrows():
        component_name = str(row["component_name"]).strip()
        if not component_name:
            continue

        cur.execute("""
            INSERT INTO salary_structure_master (
                component_name, component_type, formula_type, percentage,
                max_limit, basis, taxable_status, proof_required,
                enabled, sort_order, remarks, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            component_name,
            str(row["component_type"]).strip(),
            str(row["formula_type"]).strip(),
            float(row["percentage"]),
            float(row["max_limit"]),
            str(row["basis"]).strip(),
            str(row["taxable_status"]).strip(),
            int(row["proof_required"]),
            int(row["enabled"]),
            int(row["sort_order"]),
            str(row["remarks"]).strip(),
            str(row["updated_at"]).strip(),
        ))

    conn.commit()
    conn.close()


def calculate_salary_split(annual_salary, basic_percent=40):
    """
    Auto salary split using salary_structure_master.

    Important logic:
    - Sodexo / Meal Passes is part of CTC.
    - Deduction-type components like Meal Passes / Sodexo Declaration are not added to CTC breakup.
    - Taxable Allowance is the balancing figure so total salary components equal Annual Salary / CTC.
    """
    structure_df = load_salary_structure_master()
    annual_salary = float(annual_salary or 0)
    basic = round(annual_salary * basic_percent / 100, 2)

    result = {
        "Annual Salary / CTC": annual_salary,
        "Basic": basic,
        "HRA": 0,
        "Sodexo / Meal Passes": 0,
        "Telephone / Internet": 0,
        "Electricity Reimbursement": 0,
        "Professional / Software": 0,
        "Skill Development": 0,
        "Power & Utility Allowance": 0,
        "Taxable Allowance": 0,
        "Total Salary Components": 0,
        "Meal Passes / Sodexo Declaration": 0,
    }

    ctc_components = set([
        "Basic",
        "HRA",
        "Sodexo / Meal Passes",
        "Telephone / Internet",
        "Electricity Reimbursement",
        "Professional / Software",
        "Skill Development",
        "Power & Utility Allowance",
        "Taxable Allowance",
    ])

    for _, row in structure_df.iterrows():
        if int(row.get("enabled", 1)) != 1:
            continue

        component = str(row.get("component_name", "")).strip()
        component_type = str(row.get("component_type", "")).strip().lower()
        formula_type = str(row.get("formula_type", "")).strip().lower()
        percentage = float(row.get("percentage", 0) or 0)
        max_limit = float(row.get("max_limit", 0) or 0)

        # Deduction/investment declaration heads are tracked separately;
        # they should not increase CTC breakup.
        if component_type == "deduction":
            if component == "Meal Passes / Sodexo Declaration":
                result[component] = round(max_limit, 2)
            continue

        if component == "Basic":
            result[component] = basic

        elif component == "HRA":
            result[component] = round(basic * percentage / 100, 2)

        elif component == "Taxable Allowance":
            continue

        elif formula_type == "fixed":
            result[component] = round(max_limit, 2)

        elif formula_type == "percentage":
            calculated = annual_salary * percentage / 100
            if max_limit > 0:
                calculated = min(calculated, max_limit)
            result[component] = round(calculated, 2)

        elif formula_type == "50% of basic":
            result[component] = round(basic * percentage / 100, 2)

    component_total_before_taxable = sum(
        amount for comp, amount in result.items()
        if comp in ctc_components and comp != "Taxable Allowance"
    )

    result["Taxable Allowance"] = round(max(annual_salary - component_total_before_taxable, 0), 2)

    result["Total Salary Components"] = round(
        sum(amount for comp, amount in result.items() if comp in ctc_components),
        2
    )

    return result


def render_salary_structure_master_panel():
    st.markdown("### 💼 Salary Structure Master")
    st.caption("Edit Sodexo, HRA, reimbursements, allowances, proof rules and taxable status.")

    st.info(
        "Sodexo / Meal Passes is treated as part of CTC. "
        "Meal Passes / Sodexo Declaration is also available as a separate editable deduction/declaration head. "
        "Exemption will be considered only up to approved proof/declaration amount."
    )

    structure_df = load_salary_structure_master()

    display_cols = [
        "component_name", "component_type", "formula_type", "percentage",
        "max_limit", "basis", "taxable_status", "proof_required",
        "enabled", "sort_order", "remarks"
    ]

    edited_df = st.data_editor(
        structure_df[display_cols],
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        key="salary_structure_editor",
        column_config={
            "component_name": st.column_config.TextColumn("Component", required=True),
            "component_type": st.column_config.SelectboxColumn(
                "Type",
                options=["Salary Component", "Allowance", "Reimbursement", "Deduction", "Other"]
            ),
            "formula_type": st.column_config.SelectboxColumn(
                "Formula",
                options=["Manual / Upload", "Fixed", "Percentage", "50% of Basic", "Balance", "Formula"]
            ),
            "percentage": st.column_config.NumberColumn("Percentage", min_value=0.0, step=0.5),
            "max_limit": st.column_config.NumberColumn("Max Limit", min_value=0.0, step=1000.0),
            "basis": st.column_config.SelectboxColumn(
                "Basis",
                options=["Monthly", "Yearly", "Per Claim", "As Approved"]
            ),
            "taxable_status": st.column_config.SelectboxColumn(
                "Taxable Status",
                options=["Taxable", "Exempt", "Partial", "Conditional"]
            ),
            "proof_required": st.column_config.CheckboxColumn("Proof Required"),
            "enabled": st.column_config.CheckboxColumn("Enabled"),
            "sort_order": st.column_config.NumberColumn("Sort Order", min_value=0, step=1),
            "remarks": st.column_config.TextColumn("Remarks"),
        }
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("💾 Save Salary Structure", use_container_width=True):
            save_salary_structure_master(edited_df)
            st.success("Salary Structure Master saved successfully.")

    with c2:
        csv = edited_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download Structure CSV",
            csv,
            file_name="salary_structure_master.csv",
            mime="text/csv",
            use_container_width=True
        )

    with c3:
        if st.button("🔄 Reload Default Components", use_container_width=True):
            seed_salary_structure_master()
            st.success("Default components checked/reloaded.")

    st.markdown("---")
    st.markdown("### 🧮 Auto Salary Split Preview")

    c1, c2 = st.columns(2)
    with c1:
        annual_salary = st.number_input(
            "Annual Salary / CTC",
            min_value=0.0,
            step=10000.0,
            value=1200000.0
        )
    with c2:
        basic_percent = st.number_input(
            "Basic % of Annual Salary",
            min_value=0.0,
            max_value=100.0,
            step=1.0,
            value=40.0
        )

    if st.button("Calculate Salary Split", use_container_width=True):
        split_result = calculate_salary_split(annual_salary, basic_percent)
        split_df = pd.DataFrame(
            [{"Component": k, "Annual Amount": v, "Monthly Amount": round(v / 12, 2)} for k, v in split_result.items()]
        )
        st.dataframe(split_df, use_container_width=True, hide_index=True)


def import_employee_master(df):
    emp_id_col = find_column(df, ["Employee ID", "EmployeeID", "Emp ID", "EmpCode"])
    emp_name_col = find_column(df, ["Employee Name", "Name", "Emp Name"])
    tax_regime_col = find_column(df, ["Tax Regime", "Regime"])
    pan_col = find_column(df, ["PAN", "PAN No", "Pan No."])
    gender_col = find_column(df, ["Gender"])
    doj_col = find_column(df, ["Date of Joining", "DOJ"])
    doe_col = find_column(df, ["Date of Exit", "DOE"])
    dob_col = find_column(df, ["DOB", "Date of Birth"])
    designation_col = find_column(df, ["Designation"])

    if not emp_id_col:
        return 0, "Employee ID column not found."

    conn = get_db_connection()
    cur = conn.cursor()
    count = 0

    for _, row in df.iterrows():
        employee_id = text_value(row, emp_id_col)
        if not employee_id:
            continue

        cur.execute("""
            INSERT OR REPLACE INTO employee_master (
                employee_id, employee_name, tax_regime, pan_no, gender,
                date_of_joining, date_of_exit, dob, designation, uploaded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            employee_id,
            text_value(row, emp_name_col),
            text_value(row, tax_regime_col),
            text_value(row, pan_col),
            text_value(row, gender_col),
            text_value(row, doj_col),
            text_value(row, doe_col),
            text_value(row, dob_col),
            text_value(row, designation_col),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        count += 1

    conn.commit()
    conn.close()
    return count, ""


def import_salary_monthly(df, tax_year, salary_month, mode):
    emp_id_col = find_column(df, ["Employee ID", "EmployeeID", "Emp ID", "EmpCode"])
    emp_name_col = find_column(df, ["Employee Name", "Name", "Emp Name"])
    gross_col = find_column(df, ["Gross Salary", "Gross", "Salary", "Annual Salary / CTC", "CTC"])
    basic_col = find_column(df, ["Basic", "Basic Salary"])
    hra_col = find_column(df, ["HRA"])
    sodexo_col = find_column(df, ["Sodexo", "Meal Passes", "Meal Passess"])
    tel_col = find_column(df, ["Telephone / Internet", "Telephone", "Internet"])
    elec_col = find_column(df, ["Electricity Reimbursement", "Electricity"])
    prof_col = find_column(df, ["Professional / Software", "Software", "Professional"])
    skill_col = find_column(df, ["Skill Development"])
    utility_col = find_column(df, ["Power & Utility Allowance", "Power Utility", "Utility Allowance"])
    taxable_allowance_col = find_column(df, ["Taxable Allowance"])
    ot_col = find_column(df, ["OT/PLI/Profit sharing", "OT", "PLI", "Profit sharing"])
    exgratia_col = find_column(df, ["EXGRATIA", "Exgratia"])
    gratuity_col = find_column(df, ["Gratuity"])
    severance_col = find_column(df, ["Severance"])
    leave_col = find_column(df, ["LeaveEncashment", "Leave Encashment"])
    referral_col = find_column(df, ["Referralbonus", "Referral Bonus"])
    other_col = find_column(df, ["OtherAdjustment", "Other Adjustment"])
    total_income_col = find_column(df, ["Total Income From Salary", "Total Income from Salary"])

    if not emp_id_col:
        return 0, "Employee ID column not found."

    conn = get_db_connection()
    cur = conn.cursor()

    if mode == "Overwrite Month":
        cur.execute(
            "DELETE FROM employee_salary_monthly WHERE financial_year = ? AND salary_month = ?",
            (tax_year, salary_month)
        )

    count = 0

    for _, row in df.iterrows():
        employee_id = text_value(row, emp_id_col)
        if not employee_id:
            continue

        cur.execute("""
            INSERT INTO employee_salary_monthly (
                employee_id, employee_name, financial_year, salary_month,
                gross_salary, basic, hra, sodexo_meal_passes,
                telephone_internet, electricity_reimbursement,
                professional_software, skill_development, power_utility_allowance,
                taxable_allowance, ot_pli_profit_sharing, exgratia, gratuity,
                severance, leave_encashment, referral_bonus, other_adjustment,
                total_income_from_salary, uploaded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            employee_id,
            text_value(row, emp_name_col),
            tax_year,
            salary_month,
            money_value(row, gross_col),
            money_value(row, basic_col),
            money_value(row, hra_col),
            money_value(row, sodexo_col),
            money_value(row, tel_col),
            money_value(row, elec_col),
            money_value(row, prof_col),
            money_value(row, skill_col),
            money_value(row, utility_col),
            money_value(row, taxable_allowance_col),
            money_value(row, ot_col),
            money_value(row, exgratia_col),
            money_value(row, gratuity_col),
            money_value(row, severance_col),
            money_value(row, leave_col),
            money_value(row, referral_col),
            money_value(row, other_col),
            money_value(row, total_income_col),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        count += 1

    conn.commit()
    conn.close()
    return count, ""


def import_tds_monthly(df, tax_year, salary_month, mode):
    emp_id_col = find_column(df, ["Employee ID", "EmployeeID", "Emp ID", "EmpCode"])
    emp_name_col = find_column(df, ["Employee Name", "Name", "Emp Name"])
    tds_col = find_column(df, ["TDS", "TDS Deducted", "Tax Deducted"])
    tax1_col = find_column(df, ["Tax1"])
    tax2_col = find_column(df, ["Tax2"])
    tax3_col = find_column(df, ["Tax3"])
    tax4_col = find_column(df, ["Tax4"])
    tax5_col = find_column(df, ["Tax5"])

    if not emp_id_col:
        return 0, "Employee ID column not found."

    conn = get_db_connection()
    cur = conn.cursor()

    if mode == "Overwrite Month":
        cur.execute(
            "DELETE FROM employee_tds_monthly WHERE financial_year = ? AND salary_month = ?",
            (tax_year, salary_month)
        )

    count = 0

    for _, row in df.iterrows():
        employee_id = text_value(row, emp_id_col)
        if not employee_id:
            continue

        cur.execute("""
            INSERT INTO employee_tds_monthly (
                employee_id, employee_name, financial_year, salary_month,
                tds_deducted, tax1_total_tax, tax2_cess_4_percent,
                tax3_total_tax_after_cess, tax4_total_deduction,
                tax5_net_deductible, uploaded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            employee_id,
            text_value(row, emp_name_col),
            tax_year,
            salary_month,
            money_value(row, tds_col),
            money_value(row, tax1_col),
            money_value(row, tax2_col),
            money_value(row, tax3_col),
            money_value(row, tax4_col),
            money_value(row, tax5_col),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        count += 1

    conn.commit()
    conn.close()
    return count, ""


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
    "TDS Deduction": [
        "Employee ID", "Employee Name", "TDS Deducted",
        "Total Tax", "Cess 4%", "Total Tax After Cess",
        "Total Deduction", "Net Deductible"
    ],
}


def build_excel_template(columns, sheet_name="Template"):
    """Return an in-memory .xlsx file containing one empty sheet with headers."""
    buf = io.BytesIO()
    df = pd.DataFrame(columns=columns)
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31] or "Template")
    buf.seek(0)
    return buf.getvalue()


def render_payroll_upload_engine():
    st.markdown("### 📤 Payroll Upload Engine")
    st.caption("Upload Employee Master, Salary Computation Excel, and TDS Excel.")

    upload_type = st.selectbox(
        "Upload Type",
        ["Employee Master", "Salary Computation", "TDS Deduction"],
        key="payroll_upload_type"
    )

    # Template download for the chosen upload type
    template_cols = UPLOAD_TEMPLATES.get(upload_type, [])
    if template_cols:
        template_bytes = build_excel_template(template_cols, sheet_name=upload_type)
        st.download_button(
            label=f"📥 Download {upload_type} template (.xlsx)",
            data=template_bytes,
            file_name=f"koenig_stride_{upload_type.lower().replace(' ', '_')}_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"tpl_dl_{upload_type}"
        )
        st.caption(
            "Expected columns: " + ", ".join(template_cols)
        )

    c1, c2, c3 = st.columns(3)
    with c1:
        tax_year = st.text_input("Tax Year", value="2026-27")
    with c2:
        salary_month = st.selectbox(
            "Month",
            ["April", "May", "June", "July", "August", "September", "October", "November", "December", "January", "February", "March"],
            index=0
        )
    with c3:
        mode = st.selectbox("Import Mode", ["Append", "Overwrite Month"])

    uploaded_file = st.file_uploader(
        "Upload Excel file",
        type=["xlsx", "xls"],
        key="payroll_excel_upload"
    )

    if uploaded_file is not None:
        try:
            xl = pd.ExcelFile(uploaded_file)
            sheet_name = st.selectbox("Select Sheet", xl.sheet_names)
            upload_df = pd.read_excel(uploaded_file, sheet_name=sheet_name).fillna("")

            st.markdown("#### Preview")
            st.dataframe(upload_df.head(50), use_container_width=True)
            st.caption("Showing first 50 rows.")

            st.markdown("#### Detected Columns")
            st.write(", ".join([str(c) for c in upload_df.columns]))

            if st.button("✅ Import to Database", use_container_width=True):
                if upload_type == "Employee Master":
                    count, err = import_employee_master(upload_df)
                elif upload_type == "Salary Computation":
                    count, err = import_salary_monthly(upload_df, tax_year, salary_month, mode)
                else:
                    count, err = import_tds_monthly(upload_df, tax_year, salary_month, mode)

                if err:
                    st.error(err)
                else:
                    st.success(f"{count} row(s) imported successfully for {upload_type}.")

        except Exception as e:
            st.error(f"Unable to process uploaded file: {e}")


def render_payroll_data_preview():
    st.markdown("### 📊 Payroll Data Preview")

    conn = get_db_connection()

    tab1, tab2, tab3, tab4 = st.tabs(["Employee Master", "Salary Monthly", "TDS Monthly", "Tax Computation"])

    with tab1:
        df = pd.read_sql_query("SELECT * FROM employee_master ORDER BY employee_id", conn)
        st.dataframe(df, use_container_width=True)

    with tab2:
        df = pd.read_sql_query("SELECT * FROM employee_salary_monthly ORDER BY uploaded_at DESC, employee_id", conn)
        st.dataframe(df, use_container_width=True)

    with tab3:
        df = pd.read_sql_query("SELECT * FROM employee_tds_monthly ORDER BY uploaded_at DESC, employee_id", conn)
        st.dataframe(df, use_container_width=True)

    with tab4:
        df = pd.read_sql_query("SELECT * FROM employee_tax_computation ORDER BY computed_at DESC, employee_id", conn)
        st.dataframe(df, use_container_width=True)

    conn.close()


def render_tax_output_fields():
    st.markdown("### 🧾 Income Breakup + Tax Output Fields")

    fields = pd.DataFrame([
        {"Field": "Employee ID", "Meaning": "Unique employee mapping"},
        {"Field": "Employee Name", "Meaning": "Employee identification"},
        {"Field": "Tax Regime", "Meaning": "Old/New tax regime"},
        {"Field": "PAN No.", "Meaning": "Tax compliance"},
        {"Field": "Gender", "Meaning": "Reporting/reference"},
        {"Field": "Date of Joining", "Meaning": "Payroll period calculation"},
        {"Field": "Date of Exit", "Meaning": "Final settlement logic"},
        {"Field": "DOB", "Meaning": "Age-based tax logic"},
        {"Field": "Designation", "Meaning": "Employee role/reference"},
        {"Field": "Basic Salary", "Meaning": "Base salary component"},
        {"Field": "HRA", "Meaning": "House Rent Allowance"},
        {"Field": "Sodexo / Meal Passes", "Meaning": "Meal benefit component"},
        {"Field": "Telephone / Internet", "Meaning": "Conditional exemption up to approved proof"},
        {"Field": "Electricity Reimbursement", "Meaning": "Conditional exemption up to approved proof"},
        {"Field": "Professional / Software", "Meaning": "Conditional exemption up to approved proof"},
        {"Field": "Skill Development", "Meaning": "Conditional exemption up to approved proof"},
        {"Field": "Power & Utility Allowance", "Meaning": "Conditional exemption up to approved proof"},
        {"Field": "Taxable Allowance", "Meaning": "Remaining taxable component"},
        {"Field": "OT / PLI / Profit Sharing", "Meaning": "Variable taxable income"},
        {"Field": "EXGRATIA", "Meaning": "Additional taxable income"},
        {"Field": "Gratuity", "Meaning": "Conditional tax treatment"},
        {"Field": "Severance", "Meaning": "Exit settlement taxation"},
        {"Field": "Leave Encashment", "Meaning": "Conditional exemption/taxability"},
        {"Field": "Referral Bonus", "Meaning": "Taxable variable income"},
        {"Field": "Other Adjustment", "Meaning": "Manual adjustment field"},
        {"Field": "Previous Employer Income 12B/12BB", "Meaning": "Previous employer salary and TDS details"},
        {"Field": "Total Income from Salary", "Meaning": "Annual salary income before deductions"},
        {"Field": "Approved Allowances / Reimbursements", "Meaning": "Only approved proof-based exemptions"},
        {"Field": "Standard Deduction", "Meaning": "As per applicable regime/rules"},
        {"Field": "Meal Passes / Sodexo Declaration", "Meaning": "Editable deduction/declaration head; exemption subject to approved amount"},
        {"Field": "Approved Investments", "Meaning": "Only approved employee declarations/proofs"},
        {"Field": "Home Loan Deduction", "Meaning": "Approved home loan interest"},
        {"Field": "Other Eligible Deductions", "Meaning": "Other approved deductions"},
        {"Field": "Taxable Salary", "Meaning": "Salary after applicable deductions/exemptions"},
        {"Field": "Tax1", "Meaning": "Total Tax"},
        {"Field": "Tax2", "Meaning": "Tax after adding 4% cess"},
        {"Field": "Tax3", "Meaning": "Total Tax after Cess"},
        {"Field": "Tax4", "Meaning": "Total Deduction"},
        {"Field": "Tax5", "Meaning": "Net Deductible"},
    ])
    st.dataframe(fields, use_container_width=True, hide_index=True)


def render_payroll_tax_engine_panel():
    st.markdown("## 💼 Payroll & Tax Engine Setup")
    st.info("Admin module: salary structure, payroll upload engine, TDS upload and payroll data preview.")

    tab1, tab2, tab3, tab4 = st.tabs([
        "Salary Structure Master",
        "Payroll Upload Engine",
        "Payroll Data Preview",
        "Income & Tax Fields"
    ])

    with tab1:
        render_salary_structure_master_panel()

    with tab2:
        render_payroll_upload_engine()

    with tab3:
        render_payroll_data_preview()

    with tab4:
        render_tax_output_fields()


# Initialize payroll DB early
init_payroll_database()



# =====================================================
# EMPLOYEE DECLARATION + APPROVAL FLOW
# =====================================================

def ensure_declaration_columns():
    """Upgrade employee_investments safely if older DB exists."""
    init_payroll_database()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(employee_investments)")
    existing = [row[1] for row in cur.fetchall()]
    add_cols = {
        "tax_regime": "TEXT DEFAULT ''",
        "previous_employer_income": "REAL DEFAULT 0",
        "previous_employer_tds": "REAL DEFAULT 0",
        "eligible_limit": "REAL DEFAULT 0",
        "excess_amount": "REAL DEFAULT 0",
    }
    for col, definition in add_cols.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE employee_investments ADD COLUMN {col} {definition}")
    conn.commit()
    conn.close()


def get_declaration_sections():
    return [
        "80C", "80D", "NPS 80CCD(1B)", "Employer NPS 80CCD(2)",
        "HRA", "Home Loan Interest", "LTA", "Donation",
        "Meal Passes / Sodexo Declaration",
        "Telephone / Internet", "Electricity Reimbursement", "Professional / Software",
        "Skill Development", "Power & Utility Allowance",
        "Form 12B / 12BB", "Previous Employer Income", "Other Deduction",
    ]


def get_section_default_limit(section):
    limits = {
        "80C": 150000, "80D": 25000, "NPS 80CCD(1B)": 50000,
        "Employer NPS 80CCD(2)": 0, "HRA": 0, "Home Loan Interest": 200000,
        "LTA": 0, "Donation": 0, "Meal Passes / Sodexo Declaration": 105600,
        "Telephone / Internet": 0, "Electricity Reimbursement": 0,
        "Professional / Software": 0, "Skill Development": 0,
        "Power & Utility Allowance": 0, "Form 12B / 12BB": 0,
        "Previous Employer Income": 0, "Other Deduction": 0,
    }
    try:
        structure_df = load_salary_structure_master()
        match = structure_df[structure_df["component_name"].astype(str).str.strip().str.lower() == section.strip().lower()]
        if not match.empty:
            value = float(match.iloc[0].get("max_limit", 0) or 0)
            if value > 0:
                return value
    except Exception:
        pass
    return limits.get(section, 0)


# ---- Proof upload security: allowlist + size limit ----
ALLOWED_PROOF_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".xls"}
MAX_PROOF_SIZE_MB = 5
MAX_PROOF_SIZE_BYTES = MAX_PROOF_SIZE_MB * 1024 * 1024


def save_uploaded_proof(uploaded_file, employee_id, section):
    """Persist an uploaded proof file with extension allowlist + size check.

    Returns the absolute path on success, or an empty string if the upload
    was rejected. The caller should surface the reason via st.error.
    """
    if uploaded_file is None:
        return ""

    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in ALLOWED_PROOF_EXTENSIONS:
        st.error(
            f"❌ File type {ext or '(unknown)'} is not allowed. "
            f"Permitted: {', '.join(sorted(ALLOWED_PROOF_EXTENSIONS))}."
        )
        return ""

    try:
        size = uploaded_file.size
    except Exception:
        size = len(uploaded_file.getbuffer())
    if size and size > MAX_PROOF_SIZE_BYTES:
        st.error(
            f"❌ File too large ({size/1024/1024:.1f} MB). "
            f"Max allowed is {MAX_PROOF_SIZE_MB} MB."
        )
        return ""

    safe_section = re.sub(r"[^A-Za-z0-9]+", "_", section).strip("_") or "section"
    safe_emp = re.sub(r"[^A-Za-z0-9]+", "_", str(employee_id)).strip("_") or "emp"
    file_name = (
        f"{safe_emp}_{safe_section}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
        f"{uuid.uuid4().hex[:8]}{ext}"
    )
    file_path = PROOF_FOLDER / file_name
    try:
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
    except Exception as e:
        st.error(f"❌ Could not save proof: {e}")
        return ""
    return str(file_path)


def submit_employee_declaration(employee_id, employee_name, tax_year, tax_regime, declaration_type, section, investment_type, claimed_amount, eligible_limit, proof_file_path, employee_remarks, previous_employer_income=0, previous_employer_tds=0):
    ensure_declaration_columns()
    claimed_amount = float(claimed_amount or 0)
    eligible_limit = float(eligible_limit or 0)
    excess_amount = max(claimed_amount - eligible_limit, 0) if eligible_limit > 0 else 0
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO employee_investments (
            employee_id, employee_name, financial_year, tax_regime,
            declaration_type, section, investment_type,
            claimed_amount, approved_amount, eligible_limit, excess_amount,
            status, proof_file, employee_remarks,
            previous_employer_income, previous_employer_tds,
            submitted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        employee_id, employee_name, tax_year, tax_regime,
        declaration_type, section, investment_type,
        claimed_amount, 0, eligible_limit, excess_amount,
        "Pending", proof_file_path, employee_remarks,
        float(previous_employer_income or 0), float(previous_employer_tds or 0),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    conn.close()


def load_employee_declarations(employee_id=None):
    ensure_declaration_columns()
    conn = get_db_connection()
    if employee_id:
        df = pd.read_sql_query("SELECT * FROM employee_investments WHERE employee_id = ? ORDER BY submitted_at DESC", conn, params=(str(employee_id),))
    else:
        df = pd.read_sql_query("SELECT * FROM employee_investments ORDER BY submitted_at DESC", conn)
    conn.close()
    return df.fillna("")


def update_declaration_status(row_id, status, approved_amount, admin_remarks, approved_by):
    ensure_declaration_columns()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE employee_investments
        SET status = ?, approved_amount = ?, admin_remarks = ?, approved_by = ?, approved_at = ?
        WHERE id = ?
    """, (status, float(approved_amount or 0), admin_remarks, approved_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), int(row_id)))
    conn.commit()
    conn.close()
    try:
        write_audit_log(
            f"DECLARATION_{status.upper()}",
            target_id=str(row_id),
            details=f"approved_amount={approved_amount}; by={approved_by}",
        )
    except Exception:
        pass


def delete_declaration(row_id):
    ensure_declaration_columns()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM employee_investments WHERE id = ?", (int(row_id),))
    conn.commit()
    conn.close()
    try:
        write_audit_log("DECLARATION_DELETED", target_id=str(row_id))
    except Exception:
        pass


def render_employee_declaration_portal():
    st.markdown("### 🧾 Employee Declaration Portal")
    st.caption("Submit investment proofs, reimbursements, Meal Passes/Sodexo, and Form 12B/12BB.")
    employee_id = str(st.session_state.employee_id)
    employee_name = str(st.session_state.employee_name or f"Employee {employee_id}")
    c1, c2 = st.columns(2)
    with c1:
        tax_year = st.text_input("Tax Year", value="2026-27", key="emp_decl_tax_year")
    with c2:
        tax_regime = st.selectbox("Tax Regime", ["New", "Old"], key="emp_decl_tax_regime")
    st.markdown("---")
    declaration_type = st.selectbox("Declaration Type", ["Investment", "Reimbursement", "Allowance", "Form 12B / 12BB", "Previous Employer", "Other"], key="emp_decl_type")
    section = st.selectbox("Section / Component", get_declaration_sections(), key="emp_decl_section")
    eligible_limit = get_section_default_limit(section)
    c1, c2 = st.columns(2)
    with c1:
        investment_type = st.text_input("Investment / Claim Type", value=section, key="emp_decl_inv_type")
    with c2:
        edited_limit = st.number_input("Eligible Limit", value=float(eligible_limit or 0), min_value=0.0, step=1000.0, key="emp_decl_limit")
    c3, c4 = st.columns(2)
    with c3:
        claimed_amount = st.number_input("Claimed Amount", min_value=0.0, step=1000.0, key="emp_decl_claimed_amount")
    with c4:
        if edited_limit > 0 and claimed_amount > edited_limit:
            st.warning(f"Claim exceeds eligible limit by ₹{claimed_amount - edited_limit:,.2f}")
        else:
            st.success("Within configured limit")
    previous_employer_income = 0.0
    previous_employer_tds = 0.0
    if section in ["Form 12B", "Form 12BB", "Previous Employer Income"]: 
        st.markdown("#### Previous Employer / Form 12B-12BB Details")
        p1, p2 = st.columns(2)
        with p1:
            previous_employer_income = st.number_input("Previous Employer Income", min_value=0.0, step=1000.0, key="previous_employer_income")
        with p2:
            previous_employer_tds = st.number_input("Previous Employer TDS", min_value=0.0, step=1000.0, key="previous_employer_tds")
    uploaded_file = st.file_uploader("Upload Proof / Document", type=["pdf", "jpg", "jpeg", "png", "xlsx", "xls"], key="emp_decl_proof")
    employee_remarks = st.text_area("Employee Remarks", placeholder="Mention bill period, previous employer name, etc.", key="emp_decl_remarks")
    if st.button("📤 Submit Declaration", use_container_width=True):
        proof_path = save_uploaded_proof(uploaded_file, employee_id, section)
        submit_employee_declaration(employee_id, employee_name, tax_year, tax_regime, declaration_type, section, investment_type, claimed_amount, edited_limit, proof_path, employee_remarks, previous_employer_income, previous_employer_tds)
        st.success("Declaration submitted successfully for approval.")
        st.rerun()
    st.markdown("---")
    st.markdown("### My Declaration Status")
    my_df = load_employee_declarations(employee_id)
    if my_df.empty:
        st.info("No declarations submitted yet.")
    else:
        show_cols = ["financial_year", "tax_regime", "declaration_type", "section", "investment_type", "claimed_amount", "eligible_limit", "excess_amount", "approved_amount", "status", "employee_remarks", "admin_remarks", "submitted_at", "approved_at"]
        show_cols = [c for c in show_cols if c in my_df.columns]
        st.dataframe(my_df[show_cols], use_container_width=True, hide_index=True)
        approved = pd.to_numeric(my_df.get("approved_amount", 0), errors="coerce").fillna(0).sum()
        pending = pd.to_numeric(my_df[my_df["status"] == "Pending"].get("claimed_amount", 0), errors="coerce").fillna(0).sum()
        rejected = pd.to_numeric(my_df[my_df["status"] == "Rejected"].get("claimed_amount", 0), errors="coerce").fillna(0).sum()
        m1, m2, m3 = st.columns(3)
        m1.metric("Approved Amount", f"₹{approved:,.0f}")
        m2.metric("Pending Amount", f"₹{pending:,.0f}")
        m3.metric("Rejected Amount", f"₹{rejected:,.0f}")



def render_inline_proof_viewer(proof_path):
    proof_path = str(proof_path or "").strip()

    if not proof_path:
        st.info("No proof uploaded for this declaration.")
        return

    path_obj = Path(proof_path)

    if not path_obj.exists():
        st.warning("Proof file not found on server.")
        return

    suffix = path_obj.suffix.lower()

    try:
        if suffix in [".jpg", ".jpeg", ".png"]:
            st.image(str(path_obj), caption=path_obj.name, use_container_width=True)

        elif suffix == ".pdf":
            with open(path_obj, "rb") as pdf_file:
                PDFbyte = pdf_file.read()
            st.download_button(
                label="📄 Open / Download PDF Proof",
                data=PDFbyte,
                file_name=path_obj.name,
                mime="application/pdf",
                use_container_width=True
            )
            st.info("Chrome blocks embedded PDF preview on Streamlit Cloud. Use the button above to open the proof.")

        elif suffix in [".xlsx", ".xls"]:
            preview_df = pd.read_excel(path_obj).fillna("")
            st.dataframe(preview_df.head(50), use_container_width=True)
            st.caption("Showing first 50 rows of uploaded Excel proof.")

        else:
            st.info("Preview not available for this file type.")

        with open(path_obj, "rb") as f:
            st.download_button(
                "⬇️ Download Proof",
                f.read(),
                file_name=path_obj.name,
                use_container_width=True
            )

    except Exception as e:
        st.warning(f"Unable to preview proof: {e}")


def render_admin_declaration_approval_panel():
    st.markdown("### ✅ Investment / Declaration Approval Panel")
    st.caption("Change status in the table, enter approved amount/remarks, then click Submit Updates.")

    df = load_employee_declarations()

    if df.empty:
        st.info("No employee declarations submitted yet.")
        return

    c1, c2, c3 = st.columns(3)

    with c1:
        status_filter = st.selectbox(
            "Filter Status",
            ["All", "Pending", "Approved", "Rejected", "Delete"],
            key="admin_decl_status_filter"
        )

    with c2:
        section_filter = st.selectbox(
            "Filter Section",
            ["All"] + sorted(df["section"].astype(str).dropna().unique().tolist()),
            key="admin_decl_section_filter"
        )

    with c3:
        employee_filter = st.text_input(
            "Employee ID / Name",
            key="admin_decl_employee_filter"
        )

    filtered = df.copy()

    if status_filter != "All":
        filtered = filtered[filtered["status"] == status_filter]

    if section_filter != "All":
        filtered = filtered[filtered["section"] == section_filter]

    if employee_filter.strip():
        q = employee_filter.strip().lower()
        filtered = filtered[
            filtered["employee_id"].astype(str).str.lower().str.contains(q, na=False) |
            filtered["employee_name"].astype(str).str.lower().str.contains(q, na=False)
        ]

    if filtered.empty:
        st.info("No matching declarations.")
        return

    st.markdown("### Pending Employee Declarations")

    if filtered.empty:
        st.info("No declarations submitted yet.")
        return

    st.markdown("#### Step 1: Update Status in Table")

    editable_cols = [
        "id", "employee_id", "employee_name", "financial_year", "tax_regime",
        "declaration_type", "section", "investment_type",
        "claimed_amount", "eligible_limit", "excess_amount",
        "approved_amount", "status", "employee_remarks",
        "admin_remarks", "submitted_at", "approved_at"
    ]
    editable_cols = [c for c in editable_cols if c in filtered.columns]

    edit_df = filtered[editable_cols].copy()

    original_status_map = dict(zip(edit_df["id"], edit_df["status"]))
    original_approved_map = dict(zip(edit_df["id"], edit_df["approved_amount"]))
    original_remarks_map = dict(zip(edit_df["id"], edit_df["admin_remarks"]))

    edited_df = st.data_editor(
        edit_df,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        key="admin_declaration_status_editor",
        disabled=[
            col for col in editable_cols
            if col not in ["status", "approved_amount", "admin_remarks"]
        ],
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "employee_id": st.column_config.TextColumn("Employee ID", disabled=True),
            "employee_name": st.column_config.TextColumn("Employee Name", disabled=True),
            "financial_year": st.column_config.TextColumn("Tax Year", disabled=True),
            "tax_regime": st.column_config.TextColumn("Tax Regime", disabled=True),
            "declaration_type": st.column_config.TextColumn("Declaration Type", disabled=True),
            "section": st.column_config.TextColumn("Section", disabled=True),
            "investment_type": st.column_config.TextColumn("Investment Type", disabled=True),
            "claimed_amount": st.column_config.NumberColumn("Claimed Amount", disabled=True),
            "eligible_limit": st.column_config.NumberColumn("Eligible Limit", disabled=True),
            "excess_amount": st.column_config.NumberColumn("Excess Amount", disabled=True),
            "approved_amount": st.column_config.NumberColumn("Approved Amount", min_value=0.0, step=1000.0),
            "status": st.column_config.SelectboxColumn(
                "Status",
                options=["Pending", "Approved", "Rejected", "Delete"],
                required=True
            ),
            "employee_remarks": st.column_config.TextColumn("Employee Remarks", disabled=True),
            "admin_remarks": st.column_config.TextColumn("Admin Remarks"),
            "submitted_at": st.column_config.TextColumn("Submitted At", disabled=True),
            "approved_at": st.column_config.TextColumn("Approved At", disabled=True),
        }
    )

    st.info(
        "Change Status from the dropdown. Use Approved / Rejected / Delete. "
        "Then click Submit Updates below."
    )

    if st.button(
        "✅ Submit Updates",
        use_container_width=True,
        key="submit_declaration_approval_updates_btn_1"
    ):

        updated_count = 0
        deleted_count = 0

        for _, row in edited_df.iterrows():

            row_id = int(row["id"])

            status = str(
                row.get("status", "Pending")
            )

            approved_amount = float(
                row.get("approved_amount", 0) or 0
            )

            admin_remarks = str(
                row.get("admin_remarks", "") or ""
            )

            if status == "Delete":

                delete_declaration(row_id)
                deleted_count += 1

            else:

                update_declaration_status(
                    row_id,
                    status,
                    approved_amount,
                    admin_remarks,
                    st.session_state.employee_name or "Admin"
                )

                updated_count += 1

        st.success(
            f"Declaration approvals updated. "
            f"Updated: {updated_count}, Deleted: {deleted_count}"
        )

        st.rerun()
        st.info("Use the Status dropdown inside the table. Then click Submit Updates.")
    
    def get_declaration_sections():

        return [
            "80C",
            "80D",
            "NPS 80CCD(1B)",
            "Employer NPS 80CCD(2)",
            "HRA",
            "Home Loan Interest",
            "LTA",
            "Donation",
            "Meal Passes / Sodexo Declaration",
            "Telephone / Internet",
            "Electricity Reimbursement",
            "Professional / Software",
            "Skill Development",
            "Power & Utility Allowance",
            "Form 12B",
            "Form 12BB",
            "Previous Employer Income",
            "Other Deduction"
        ]

    if st.button(
        "✅ Submit Updates",
        use_container_width=True,
        key="submit_declaration_approval_updates_btn_2"
    ):
        updated_count = 0
        deleted_count = 0

        for _, row in edited_df.iterrows():
            row_id = int(row["id"])
            new_status = str(row.get("status", "Pending")).strip()
            new_approved_amount = float(row.get("approved_amount", 0) or 0)
            new_admin_remarks = str(row.get("admin_remarks", "") or "")

            old_status = str(original_status_map.get(row_id, ""))
            old_approved = float(original_approved_map.get(row_id, 0) or 0)
            old_remarks = str(original_remarks_map.get(row_id, "") or "")

            changed = (
                new_status != old_status or
                new_approved_amount != old_approved or
                new_admin_remarks != old_remarks
            )

            if not changed:
                continue

            if new_status == "Delete":
                delete_declaration(row_id)
                deleted_count += 1
            elif new_status == "Rejected":
                update_declaration_status(
                    row_id,
                    "Rejected",
                    0,
                    new_admin_remarks,
                    st.session_state.employee_name or "Admin"
                )
                updated_count += 1
            elif new_status == "Approved":
                update_declaration_status(
                    row_id,
                    "Approved",
                    new_approved_amount,
                    new_admin_remarks,
                    st.session_state.employee_name or "Admin"
                )
                updated_count += 1
            else:
                update_declaration_status(
                    row_id,
                    "Pending",
                    new_approved_amount,
                    new_admin_remarks,
                    st.session_state.employee_name or "Admin"
                )
                updated_count += 1

        st.success(f"Updates submitted. Updated: {updated_count}, Deleted: {deleted_count}")
        st.rerun()

    st.markdown("---")
    st.markdown("#### Step 2: View Uploaded Proof Inline")

    proof_df = filtered[["id", "employee_id", "employee_name", "section", "proof_file"]].copy()
    proof_df = proof_df[proof_df["proof_file"].astype(str).str.strip() != ""]

    if proof_df.empty:
        st.info("No proof files available for the current filter.")
    else:
        proof_id = st.selectbox(
            "Select Declaration ID to View Proof",
            proof_df["id"].astype(int).tolist(),
            key="proof_preview_id"
        )

        selected_proof_row = proof_df[proof_df["id"] == proof_id].iloc[0]
        st.caption(
            f"Proof for Employee {selected_proof_row.get('employee_id', '')} - "
            f"{selected_proof_row.get('employee_name', '')} | "
            f"Section: {selected_proof_row.get('section', '')}"
        )

        render_inline_proof_viewer(selected_proof_row.get("proof_file", ""))

    st.markdown("---")
    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download Approval Data CSV",
        csv,
        file_name="employee_declaration_approval_data.csv",
        mime="text/csv",
        use_container_width=True
    )

def render_employee_tax_summary_snapshot():
    st.markdown("### 📊 My Tax Declaration Snapshot")
    employee_id = str(st.session_state.employee_id)
    df = load_employee_declarations(employee_id)
    if df.empty:
        st.info("No declaration data yet. Submit investment/reimbursement proofs to see your tax snapshot.")
        return
    approved_df = df[df["status"] == "Approved"]
    pending_df = df[df["status"] == "Pending"]
    rejected_df = df[df["status"] == "Rejected"]
    approved_amount = pd.to_numeric(approved_df.get("approved_amount", 0), errors="coerce").fillna(0).sum()
    pending_amount = pd.to_numeric(pending_df.get("claimed_amount", 0), errors="coerce").fillna(0).sum()
    rejected_amount = pd.to_numeric(rejected_df.get("claimed_amount", 0), errors="coerce").fillna(0).sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Approved Declarations", f"₹{approved_amount:,.0f}")
    c2.metric("Pending Review", f"₹{pending_amount:,.0f}")
    c3.metric("Rejected Claims", f"₹{rejected_amount:,.0f}")
    if not approved_df.empty:
        section_summary = approved_df.groupby("section", as_index=False)["approved_amount"].sum().sort_values("approved_amount", ascending=False)
        st.markdown("#### Approved Amount by Section")
        st.dataframe(section_summary, use_container_width=True, hide_index=True)

# =====================================================
# LOGOUT
# =====================================================

def logout():
    for key in ["logged_in","role","employee_id","employee_name","must_change_password","menu_open","selected_module","chat_history","show_change_password"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()



# =====================================================
# EMPLOYEE MASTER DATABASE + UPLOAD
# =====================================================

def init_employee_master_table():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS employee_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT UNIQUE,
            employee_name TEXT,
            tax_regime TEXT,
            pan_no TEXT,
            gender TEXT,
            date_of_joining TEXT,
            date_of_exit TEXT,
            dob TEXT,
            designation TEXT,
            uploaded_at TEXT
        )
    """)

    required_columns = {
        "email": "TEXT",
        "doj": "TEXT",
        "doe": "TEXT",
        "department": "TEXT",
        "branch": "TEXT",
        "annual_salary": "REAL DEFAULT 0",
        "monthly_salary": "REAL DEFAULT 0",
        "basic_percent": "REAL DEFAULT 50",
        "status": "TEXT DEFAULT 'Active'",
        "upload_month": "TEXT",
        "tax_year": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT"
    }

    cur.execute("PRAGMA table_info(employee_master)")
    existing_cols = [row[1] for row in cur.fetchall()]

    for col, col_type in required_columns.items():
        if col not in existing_cols:
            cur.execute(f"ALTER TABLE employee_master ADD COLUMN {col} {col_type}")

    conn.commit()
    conn.close()

def normalize_employee_master_columns(df):
    aliases = {
        "EmployeeID": ["EmployeeID", "Employee ID", "Emp ID", "EmpCode", "Employee Code"],
        "EmployeeName": ["EmployeeName", "Employee Name", "Emp Name", "Name"],
        "Email": ["Email", "Email ID", "Official Email", "Official Email ID"],
        "PAN": ["PAN", "PAN No", "Pan No.", "PAN Number"],
        "Gender": ["Gender"],
        "DOB": ["DOB", "Date of Birth"],
        "DOJ": ["DOJ", "Date of Joining", "Joining Date"],
        "DOE": ["DOE", "Date of Exit", "Exit Date"],
        "Designation": ["Designation"],
        "Department": ["Department"],
        "Branch": ["Branch", "Location", "Base Location"],
        "TaxRegime": ["TaxRegime", "Tax Regime", "Regime"],
        "AnnualSalary": ["AnnualSalary", "Annual Salary", "Annual CTC", "CTC"],
        "MonthlySalary": ["MonthlySalary", "Monthly Salary", "Salary"],
        "BasicPercent": ["BasicPercent", "Basic Percent", "Basic %"],
        "Status": ["Status", "Employee Status"]
    }
    current = {str(c).strip().lower().replace(" ", "").replace(".", "").replace("_", ""): c for c in df.columns}
    rename_map = {}
    for target, options in aliases.items():
        for opt in options:
            key = str(opt).strip().lower().replace(" ", "").replace(".", "").replace("_", "")
            if key in current:
                rename_map[current[key]] = target
                break
    return df.rename(columns=rename_map)


def upload_employee_master(df, upload_month, tax_year):
    init_employee_master_table()
    df = normalize_employee_master_columns(df.copy()).fillna("")
    required = ["EmployeeID", "EmployeeName", "Email", "PAN", "Gender", "DOB", "DOJ", "Designation", "Department", "Branch", "TaxRegime", "AnnualSalary", "MonthlySalary", "BasicPercent", "Status"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {"success": False, "message": "Missing columns: " + ", ".join(missing), "inserted": 0, "updated": 0, "errors": []}

    inserted, updated, errors = 0, 0, []
    conn = get_db_connection()
    cur = conn.cursor()
    for idx, row in df.iterrows():
        try:
            employee_id = str(row.get("EmployeeID", "")).strip()
            if not employee_id:
                errors.append(f"Row {idx + 2}: Missing Employee ID")
                continue
            def num(x, default=0):
                try:
                    return float(str(x).replace(",", "") or default)
                except Exception:
                    return default
            vals = {
                "employee_name": str(row.get("EmployeeName", "")).strip(),
                "email": str(row.get("Email", "")).strip(),
                "pan_no": str(row.get("PAN", "")).strip(),
                "gender": str(row.get("Gender", "")).strip(),
                "dob": str(row.get("DOB", "")).strip(),
                "doj": str(row.get("DOJ", "")).strip(),
                "doe": str(row.get("DOE", "")).strip(),
                "designation": str(row.get("Designation", "")).strip(),
                "department": str(row.get("Department", "")).strip(),
                "branch": str(row.get("Branch", "")).strip(),
                "tax_regime": str(row.get("TaxRegime", "New")).strip() or "New",
                "annual_salary": num(row.get("AnnualSalary", 0)),
                "monthly_salary": num(row.get("MonthlySalary", 0)),
                "basic_percent": num(row.get("BasicPercent", 50), 50),
                "status": str(row.get("Status", "Active")).strip() or "Active",
                "upload_month": upload_month,
                "tax_year": tax_year,
                "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            cur.execute("SELECT employee_id FROM employee_master WHERE employee_id = ?", (employee_id,))
            exists = cur.fetchone()
            if exists:
                cur.execute("""
                    UPDATE employee_master SET employee_name=?, email=?, pan_no=?, gender=?, dob=?, doj=?, doe=?, designation=?, department=?, branch=?, tax_regime=?, annual_salary=?, monthly_salary=?, basic_percent=?, status=?, upload_month=?, tax_year=?, updated_at=? WHERE employee_id=?
                """, (vals["employee_name"], vals["email"], vals["pan_no"], vals["gender"], vals["dob"], vals["doj"], vals["doe"], vals["designation"], vals["department"], vals["branch"], vals["tax_regime"], vals["annual_salary"], vals["monthly_salary"], vals["basic_percent"], vals["status"], vals["upload_month"], vals["tax_year"], vals["now"], employee_id))
                updated += 1
            else:
                cur.execute("""
                    INSERT INTO employee_master (employee_id, employee_name, email, pan_no, gender, dob, doj, doe, designation, department, branch, tax_regime, annual_salary, monthly_salary, basic_percent, status, upload_month, tax_year, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (employee_id, vals["employee_name"], vals["email"], vals["pan_no"], vals["gender"], vals["dob"], vals["doj"], vals["doe"], vals["designation"], vals["department"], vals["branch"], vals["tax_regime"], vals["annual_salary"], vals["monthly_salary"], vals["basic_percent"], vals["status"], vals["upload_month"], vals["tax_year"], vals["now"], vals["now"]))
                inserted += 1
        except Exception as e:
            errors.append(f"Row {idx + 2}: {str(e)}")
    conn.commit()
    conn.close()
    return {"success": True, "inserted": inserted, "updated": updated, "errors": errors}


def load_employee_master():
    init_employee_master_table()
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM employee_master ORDER BY employee_id", conn)
    conn.close()
    return df.fillna("")

def update_employee_master_record(employee_id, data):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE employee_master
        SET employee_name = ?,
            email = ?,
            pan_no = ?,
            gender = ?,
            dob = ?,
            doj = ?,
            doe = ?,
            designation = ?,
            department = ?,
            branch = ?,
            tax_regime = ?,
            annual_salary = ?,
            monthly_salary = ?,
            basic_percent = ?,
            status = ?,
            updated_at = ?
        WHERE employee_id = ?
    """, (
        data["employee_name"],
        data["email"],
        data["pan_no"],
        data["gender"],
        data["dob"],
        data["doj"],
        data["doe"],
        data["designation"],
        data["department"],
        data["branch"],
        data["tax_regime"],
        float(data["annual_salary"]),
        float(data["monthly_salary"]),
        float(data["basic_percent"]),
        data["status"],
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        employee_id
    ))

    conn.commit()
    conn.close()

def delete_employee_master_record(employee_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM employee_master WHERE employee_id = ?",
        (employee_id,)
    )

    conn.commit()
    conn.close()

def render_employee_master_upload_panel():
    st.markdown("## 👥 Employee Master Upload")
    st.caption("Upload or update employees for Koenig Stride payroll and tax computation.")
    c1, c2 = st.columns(2)
    with c1:
        upload_month = st.text_input("Upload Month", value=datetime.now().strftime("%B %Y"), key="emp_master_upload_month")
    with c2:
        tax_year = st.text_input("Tax Year", value="2026-27", key="emp_master_tax_year")

    with st.expander("Required Excel Format", expanded=False):
        sample_df = pd.DataFrame([{
            "EmployeeID": "1001", "EmployeeName": "Sample Employee", "Email": "employee@koenig-solutions.com",
            "PAN": "ABCDE1234F", "Gender": "Male", "DOB": "1990-01-01", "DOJ": "2024-04-01",
            "DOE": "", "Designation": "Executive", "Department": "Accounts", "Branch": "Delhi",
            "TaxRegime": "New", "AnnualSalary": 1200000, "MonthlySalary": 100000, "BasicPercent": 40, "Status": "Active"
        }])
        st.dataframe(sample_df, use_container_width=True, hide_index=True)
        dl_c1, dl_c2 = st.columns(2)
        with dl_c1:
            st.download_button(
                "⬇️ Download Sample CSV",
                sample_df.to_csv(index=False).encode("utf-8"),
                file_name="employee_master_sample.csv",
                mime="text/csv",
                use_container_width=True
            )
        with dl_c2:
            tpl_bytes = build_excel_template(list(sample_df.columns), sheet_name="Employee Master")
            st.download_button(
                "⬇️ Download Empty Template (.xlsx)",
                tpl_bytes,
                file_name="employee_master_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    uploaded_file = st.file_uploader("Upload Employee Master Excel", type=["xlsx", "xls"], key="employee_master_excel_upload")
    if uploaded_file is not None:
        try:
            xl = pd.ExcelFile(uploaded_file)
            sheet_name = st.selectbox("Select Sheet", xl.sheet_names, key="employee_master_sheet")
            df = normalize_employee_master_columns(pd.read_excel(uploaded_file, sheet_name=sheet_name).fillna(""))
            st.success(f"File loaded successfully — {len(df)} record(s)")
            st.dataframe(df.head(50), use_container_width=True, hide_index=True)
            required = ["EmployeeID", "EmployeeName", "Email", "PAN", "Gender", "DOB", "DOJ", "Designation", "Department", "Branch", "TaxRegime", "AnnualSalary", "MonthlySalary", "BasicPercent", "Status"]
            missing = [c for c in required if c not in df.columns]
            if missing:
                st.error("Missing columns: " + ", ".join(missing))
            else:
                st.success("All required columns found.")
                if st.button("📤 Upload Employee Master", use_container_width=True):
                    result = upload_employee_master(df, upload_month, tax_year)
                    if result["success"]:
                        st.success(
                            f"Upload Complete | Inserted: {result['inserted']} | Updated: {result['updated']}"
                        )

                        st.cache_data.clear()

                        saved_df = load_employee_master()

                        st.markdown("### Saved Employee Master Records")
                        st.dataframe(saved_df, use_container_width=True, hide_index=True)

                        if result["errors"]:
                            st.warning("Some rows had errors")
                            st.dataframe(pd.DataFrame({"Errors": result["errors"]}))
                    else:
                        st.error(result["message"])
        except Exception as e:
            st.error(f"Upload failed: {e}")

    st.markdown("---")
    st.markdown("### Current Employee Master")
    emp_df = load_employee_master()
    if emp_df.empty:
        st.info("No employee master records found yet.")
    else:
        st.dataframe(emp_df, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Download Current Employee Master", emp_df.to_csv(index=False).encode("utf-8"), file_name="current_employee_master.csv", mime="text/csv", use_container_width=True)

try:
    init_employee_master_table()
except Exception as e:
    st.warning(f"Employee master table initialization warning: {e}")



# =====================================================
# VOICE SARIKA - NATIVE STREAMLIT AUDIO INPUT
# =====================================================

def transcribe_audio_with_openai(audio_bytes):
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
                "Form 16, Form 12B, Form 12BB, Sodexo, Koenig, Stride, Sarika, "
                "SPOC, TDS, PAN, CTC, Rupees, lakh, crore."
            ),
        )

        return transcript.text, ""

    except Exception as e:
        return "", str(e)


def speak_button_html(text, button_label="🔊 Speak Reply"):
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


def render_voice_sarika_panel():
    st.markdown("### 🎙️ Voice Sarika")
    st.caption("Record your question, then click **Transcribe & Ask Sarika**.")

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

        if st.button("📝 Transcribe & Ask Sarika", use_container_width=True, key="voice_transcribe_ask_btn"):
            with st.spinner("Sarika is listening and thinking..."):
                transcript, err = transcribe_audio_with_openai(audio_bytes)

                if err:
                    st.error(f"Voice transcription failed: {err}")
                elif not transcript.strip():
                    st.warning("No speech detected. Please try again.")
                else:
                    st.success(f"You said: {transcript}")
                    submit_query(transcript.strip())
                    st.rerun()

    if st.session_state.chat_history:
        latest = st.session_state.chat_history[-1]
        if latest.get("type") == "answer":
            components.html(
                speak_button_html(latest.get("answer", ""), "🔊 Speak Latest Reply"),
                height=60
            )


# =====================================================
# ADMIN ANALYTICS DASHBOARD
# =====================================================

def render_admin_analytics_dashboard():
    """High-level admin analytics: users, declarations, knowledge, payroll."""
    st.markdown("## 📈 Admin Analytics")
    st.caption("Overview of platform usage, declarations, and data health.")

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

    # ---------------- Declarations ----------------
    st.markdown("### 🧾 Declarations")
    try:
        decl_df = load_employee_declarations()
    except Exception:
        decl_df = pd.DataFrame()

    if decl_df.empty:
        st.info("No declarations submitted yet.")
    else:
        total_decl = len(decl_df)
        pending = int((decl_df["status"].astype(str) == "Pending").sum())
        approved = int((decl_df["status"].astype(str) == "Approved").sum())
        rejected = int((decl_df["status"].astype(str) == "Rejected").sum())

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Total Declarations", total_decl)
        d2.metric("Pending", pending)
        d3.metric("Approved", approved)
        d4.metric("Rejected", rejected)

        try:
            claimed_total = float(decl_df.get("claimed_amount", pd.Series(dtype=float)).sum() or 0)
            approved_total = float(decl_df[decl_df["status"].astype(str) == "Approved"]
                                   .get("approved_amount", pd.Series(dtype=float)).sum() or 0)
            a1, a2 = st.columns(2)
            a1.metric("Total Claimed", f"₹{claimed_total:,.0f}")
            a2.metric("Total Approved", f"₹{approved_total:,.0f}")
        except Exception:
            pass

        # Declarations by section
        if "section" in decl_df.columns:
            with st.expander("📊 Declarations by Section", expanded=False):
                by_section = (
                    decl_df.groupby("section")
                    .agg(
                        count=("id", "count"),
                        claimed=("claimed_amount", "sum"),
                    )
                    .reset_index()
                    .sort_values("count", ascending=False)
                )
                st.dataframe(by_section, use_container_width=True, hide_index=True)
                try:
                    st.bar_chart(by_section.set_index("section")["count"])
                except Exception:
                    pass

        # Top employees by declaration count
        if "employee_id" in decl_df.columns:
            with st.expander("👤 Top Employees by Declarations", expanded=False):
                top_emp = (
                    decl_df.groupby(["employee_id", "employee_name"])
                    .size()
                    .reset_index(name="declarations")
                    .sort_values("declarations", ascending=False)
                    .head(10)
                )
                st.dataframe(top_emp, use_container_width=True, hide_index=True)

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

    # ---------------- Payroll ----------------
    st.markdown("### 💼 Payroll Database")
    try:
        conn = get_db_connection()
        emp_master_n = conn.execute("SELECT COUNT(*) FROM employee_master").fetchone()[0]
        salary_n = conn.execute("SELECT COUNT(*) FROM employee_salary_monthly").fetchone()[0]
        tds_n = conn.execute("SELECT COUNT(*) FROM employee_tds_monthly").fetchone()[0]
        inv_n = conn.execute("SELECT COUNT(*) FROM employee_investments").fetchone()[0]
        conn.close()
    except Exception:
        emp_master_n = salary_n = tds_n = inv_n = 0

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Employee Master", emp_master_n)
    p2.metric("Salary Records", salary_n)
    p3.metric("TDS Records", tds_n)
    p4.metric("Investment Rows", inv_n)

    # ---------------- Storage health (Streamlit Cloud warning) ----------------
    st.markdown("### ⚠️ Storage Health")
    try:
        db_size = DB_PATH.stat().st_size / 1024 if DB_PATH.exists() else 0
        proof_count = sum(1 for _ in PROOF_FOLDER.glob("*")) if PROOF_FOLDER.exists() else 0
    except Exception:
        db_size = 0
        proof_count = 0
    s1, s2 = st.columns(2)
    s1.metric("SQLite DB size", f"{db_size:,.1f} KB")
    s2.metric("Proof files stored", proof_count)
    st.warning(
        "⚠️ **Streamlit Cloud filesystem is ephemeral.** SQLite data and proof "
        "uploads will be wiped on container restart. Plan a Postgres + S3 migration "
        "before going live with real employees."
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
    st.markdown("<h3>👩‍💼 Sarika</h3>", unsafe_allow_html=True)
    st.markdown("<div class='online'>● Sarika is online</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### 📌 Panels")

    panel_button("🏠 Home", "Home")
    panel_button("🚀 Start Here", "Start Here")
    panel_button("👤 Account", "Account")

    if st.session_state.get("start_completed", False):
        st.markdown("---")
        st.markdown("### 🤖 Assistant")
        panel_button("💬 Ask Sarika", "Ask Sarika")

        st.markdown("---")
        st.markdown("### 🧾 Employee Tax")
        panel_button("🧾 Employee Declaration", "Employee Declaration")
        panel_button("📊 My Tax Snapshot", "My Tax Snapshot")

        if st.session_state.role == "Admin":
            st.markdown("---")
            st.markdown("### 🛠️ Admin")
            panel_button("👥 Employee Master Upload", "Employee Master Upload")
            panel_button("💼 Payroll & Tax Engine", "Payroll Tax Engine")
            panel_button("✅ Declaration Approval", "Declaration Approval")
            panel_button("👥 User Management", "User Management")
            panel_button("📚 Knowledge Base", "Knowledge Base")
            panel_button("📈 Admin Analytics", "Admin Analytics")

with right:
    selected_panel = st.session_state.get("selected_panel", "Home")

    locked_panels = [
        "Ask Sarika", "Employee Declaration", "My Tax Snapshot",
        "Payroll Tax Engine", "Declaration Approval", "User Management",
        "Knowledge Base", "Admin Analytics"
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
            <p>Select a panel from the left sidebar,<br>or use Ask Sarika to ask directly.</p>
        </div>
        """, unsafe_allow_html=True)
        st.info(
            "👉 Click **🚀 Start Here** in the left sidebar to unlock Ask Sarika, "
            "Employee Declarations, and (for Admins) the Payroll & Approval panels."
        )


    # =====================================================
    # START HERE PANEL
    # =====================================================
    elif selected_panel == "Start Here":
        st.session_state.start_completed = True
        st.markdown("## 🚀 Start Here")
        st.success("Assistant panels are now available in the left sidebar, including Ask Sarika.")
        if st.button("💬 Open Ask Sarika", use_container_width=True):
            st.session_state.selected_panel = "Ask Sarika"
            st.rerun()
        st.markdown("Select an area below, then choose a category and question.")

        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("### Select Area")
        modules = [
            ("✅ Tax FAQs", "Tax FAQs"),
            ("✅ Salary Queries", "Salary Queries"),
            ("⚖️ Labour Code", "Labour Code"),
            ("✅ Entity Nexus", "Entity Nexus"),
            ("✅ SPOC Routing", "SPOC Routing"),
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
    # EMPLOYEE DECLARATION PANEL
    # =====================================================
    elif selected_panel == "Employee Declaration":
        render_employee_declaration_portal()

    # =====================================================
    # TAX SNAPSHOT PANEL
    # =====================================================
    elif selected_panel == "My Tax Snapshot":
        render_employee_tax_summary_snapshot()

    # =====================================================
    # ASK SARIKA PANEL
    # =====================================================
    elif selected_panel == "Ask Sarika":
        st.markdown("## 💬 Ask Sarika")
        st.markdown(
            "<div style='color:#64748b; font-size:13px; margin-top:-8px; margin-bottom:12px;'>"
            "Chat with Sarika — your AI assistant for tax, salary, labour code, entity nexus and SPOC queries."
            "</div>",
            unsafe_allow_html=True
        )

        with st.expander("🎙️ Voice Sarika (speak instead of typing)", expanded=False):
            if "render_voice_sarika_panel" in globals():
                render_voice_sarika_panel()
            else:
                st.info("Voice Sarika is not available in this build. Please use the text box below.")

        # ----- Chat history (newest at the bottom, like real chat apps) -----
        chat_container = st.container()
        with chat_container:
            if not st.session_state.chat_history:
                with st.chat_message("assistant", avatar="👩‍💼"):
                    st.markdown(
                        f"Hi **{st.session_state.employee_name}** 👋  \n"
                        "I'm **Sarika**, your Koenig Stride assistant. "
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
                            st.markdown(item["answer"])

                        if st.session_state.role == "Admin":
                            st.caption(
                                f"Source: {item.get('source','')} · "
                                f"Similarity: {item.get('similarity',0):.2f}"
                            )

        # ----- Chat input at the bottom (widget-style, like ChatGPT/WhatsApp) -----
        user_query = st.chat_input("Type your question and press Enter… (e.g. What is NPS?)")
        if user_query and user_query.strip():
            with st.spinner("Sarika is thinking…"):
                submit_query(user_query.strip())
            st.rerun()

        if st.session_state.chat_history:
            col_clear, _ = st.columns([1, 4])
            with col_clear:
                if st.button("🗑️ Clear chat", use_container_width=True, key="ask_sarika_clear"):
                    st.session_state.chat_history = []
                    st.rerun()

    # =====================================================
    # ADMIN PANELS
    # =====================================================
    elif selected_panel == "Employee Master Upload" and st.session_state.role == "Admin":
        render_employee_master_upload_panel()

    elif selected_panel == "Payroll Tax Engine" and st.session_state.role == "Admin":
        render_payroll_tax_engine_panel()

    elif selected_panel == "Declaration Approval" and st.session_state.role == "Admin":
        render_admin_declaration_approval_panel()

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

    elif selected_panel == "Admin Analytics" and st.session_state.role == "Admin":
        render_admin_analytics_dashboard()

    else:
        st.warning("You are not authorized to view this panel.")

# =====================================================
# ADMIN
# =====================================================

# Admin panels are now available from the left sidebar.
st.markdown("<div class='footer-line'><div>© 2025 Koenig Solutions Ltd. All rights reserved.</div><div>Privacy Policy &nbsp; | &nbsp; Terms of Use</div></div>", unsafe_allow_html=True)
