import streamlit as st
import pandas as pd
from pathlib import Path
import base64
import hashlib
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

BASE_DIR = Path(__file__).parent
EXCEL_PATH = BASE_DIR / "knowledge" / "Koenig_VoiceBot_FAQ_Master.xlsx"
LOGO_PATH = BASE_DIR / "assets" / "koenig_logo.png"
SARIKA_PATH = BASE_DIR / "assets" / "sarika.png"
USERS_PATH = BASE_DIR / "users.csv"

DEFAULT_EMPLOYEE_PASSWORD = "Welcome@123"
DEFAULT_ADMIN_PASSWORD = "admin123"

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
    border-radius:14px !important;
    font-weight:800 !important;
    min-height:50px;
    border:1px solid var(--border) !important;
    background:white !important;
    color:#111827 !important;
    box-shadow:0 5px 16px rgba(15,23,42,.05) !important;
    transition:transform .08s ease, box-shadow .15s ease, background .15s ease;
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

def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

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

    if match.empty:
        if user_id.isdigit():
            ensure_employee_exists(user_id)
            df = load_users()
            match = df[df["user_id"].astype(str) == user_id]
        else:
            return False, "User not found.", None

    row = match.iloc[0]

    if not bool_from_str(row.get("active", "True")):
        return False, "This user is inactive. Please contact admin.", None

    if row["password_hash"] != hash_password(password):
        return False, "Invalid password.", None

    return True, "", row

def update_user_password(user_id, new_password, first_login=False):
    df = load_users()
    idx = df[df["user_id"].astype(str) == str(user_id)].index
    if len(idx) == 0:
        return False

    df.loc[idx, "password_hash"] = hash_password(new_password)
    df.loc[idx, "first_login"] = "True" if first_login else "False"
    save_users(df)
    return True

def reset_employee_password(emp_id):
    ensure_employee_exists(emp_id)
    return update_user_password(emp_id, DEFAULT_EMPLOYEE_PASSWORD, first_login=True)

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

        # 4. Sarika photo
        if SARIKA_B64:
            st.markdown(f"""
            <div class='sarika-wrap'>
                <img src='data:image/png;base64,{SARIKA_B64}'>
                <div class='sarika-caption'>👩‍💼 Sarika</div>
                <div class='sarika-online'>● Sarika is online</div>
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
                        st.rerun()
                    else:
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
                    st.rerun()
                elif ok:
                    st.error("This is not an admin account.")
                else:
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

faq_df, load_error = load_knowledge()

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
    if "spoc" in combined or "contact" in combined or "who handles" in combined:
        return "SPOC Routing"
    if is_protected(row):
        return "Protected Information Routing"
    if "entity" in source or "entity" in combined:
        return "Entity Nexus"
    if any(x in combined for x in ["compliance","tds","gst","filing","return","deduction","80c","80ccd"]):
        return "Compliance Support"
    if any(x in combined for x in ["salary","payroll","ctc","reimbursement"]):
        return "Salary Queries"
    return "Tax FAQs"

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
# LOGOUT
# =====================================================

def logout():
    for key in ["logged_in","role","employee_id","employee_name","must_change_password","menu_open","selected_module","chat_history","show_change_password"]:
        if key in st.session_state:
            del st.session_state[key]
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

    st.markdown("""
    <div class='side-item side-item-active'>🏠 Home</div>
    <div class='side-item'>👤 Account</div>
    """, unsafe_allow_html=True)

    if st.button("🔧 Change Password", use_container_width=True):
        st.session_state.show_change_password = not st.session_state.show_change_password

    if st.session_state.show_change_password:
        with st.expander("Change My Password", expanded=True):
            old_password = st.text_input("Current Password", type="password", key="old_pwd")
            new_password = st.text_input("New Password", type="password", key="new_pwd")
            confirm_password = st.text_input("Confirm Password", type="password", key="confirm_pwd")
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
                        st.session_state.show_change_password = False

    st.markdown("<div class='side-item'>ℹ️ Help & Support</div>", unsafe_allow_html=True)

with right:
    st.markdown("""
    <div class='hero'>
        <h2>Welcome to Koenig Stride</h2>
        <p>Select Start Here to browse guided help,<br>or use the chat box to ask directly.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div class='primary-start'>", unsafe_allow_html=True)
    if st.button("🚀 Start Here                                              →", use_container_width=True):
        st.session_state.menu_open = True
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.menu_open:
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

    st.markdown("## 💬 Ask Koenig Stride Directly")
    with st.form("ask_form", clear_on_submit=True):
        query = st.text_input("Type your question here", placeholder="Example: What is NPS?")
        submitted = st.form_submit_button("➤ Ask Koenig Stride")
    if submitted and query.strip():
        with st.spinner("Koenig Stride is thinking..."):
            submit_query(query.strip())

    if st.session_state.chat_history:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("### Conversation")
        for item in reversed(st.session_state.chat_history[-10:]):
            st.markdown(f"<div class='user-bubble'><b>You:</b><br>{item['query']}</div>", unsafe_allow_html=True)
            if item["type"] == "protected":
                email_html = f"<br><b>Email:</b> {item.get('email','')}" if item.get("email") else ""
                st.markdown(f"""
                <div class='protected-box'>
                <b>🔒 Koenig Stride:</b><br>
                {item['answer']}<br><br>
                Please contact:<br>
                <b>SPOC:</b> {item.get('spoc','Relevant SPOC')}
                {email_html}<br><br>
                <span class='small-text'>Source: {item.get('source','')} | Similarity: {item.get('similarity',0):.2f}</span>
                </div>
                """, unsafe_allow_html=True)
            else:
                meta = f"<br><br><span class='small-text'>Source: {item.get('source','')} | Similarity: {item.get('similarity',0):.2f}</span>" if st.session_state.role == "Admin" else ""
                st.markdown(f"<div class='bot-bubble'><b>Koenig Stride:</b><br>{item['answer']}{meta}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

# =====================================================
# ADMIN
# =====================================================

if st.session_state.role == "Admin":
    with st.expander("Admin Panel: User Management"):
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

    with st.expander("Admin Preview: Knowledge Base"):
        if not faq_df.empty:
            st.success(f"Knowledge base loaded successfully. Total records: {len(faq_df)}")
            cols = [c for c in ["Main Module", "Source", "Category", "Question", "Protected", "SPOC Name", "SPOC Email"] if c in faq_df.columns]
            st.dataframe(faq_df[cols], use_container_width=True)
        else:
            st.warning("No knowledge records loaded.")

st.markdown("<div class='footer-line'><div>© 2025 Koenig Solutions Ltd. All rights reserved.</div><div>Privacy Policy &nbsp; | &nbsp; Terms of Use</div></div>", unsafe_allow_html=True)
