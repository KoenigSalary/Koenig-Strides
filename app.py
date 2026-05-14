
import streamlit as st
import pandas as pd
from pathlib import Path
import base64
import numpy as np

# Optional AI imports
try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    from openai import OpenAI
    AI_AVAILABLE = True
except Exception:
    AI_AVAILABLE = False

# =====================================================
# KOENIG STRIDE - COMPLETE BLUE UI
# Logo + Sarika + Start Here + Module > Category > Question + Chat
# =====================================================

st.set_page_config(
    page_title="Koenig Stride",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =====================================================
# PATHS
# =====================================================

BASE_DIR = Path(__file__).parent
EXCEL_PATH = BASE_DIR / "knowledge" / "Koenig_VoiceBot_FAQ_Master.xlsx"
LOGO_PATH = BASE_DIR / "assets" / "koenig_logo.png"
SARIKA_PATH = BASE_DIR / "assets" / "sarika.png"

# =====================================================
# IMAGE BASE64
# =====================================================

def image_to_base64(path):
    if path.exists():
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""

LOGO_B64 = image_to_base64(LOGO_PATH)
SARIKA_B64 = image_to_base64(SARIKA_PATH)

# =====================================================
# CSS
# =====================================================

st.markdown("""
<style>
:root {
    --blue-dark: #071a4f;
    --blue: #155be8;
    --bg: #f4f7fb;
    --card: #ffffff;
    --border: #dbe3ef;
    --text: #111827;
    --muted: #64748b;
}

[data-testid="stAppViewContainer"] {
    background: var(--bg);
}

.block-container {
    padding-top: 1rem;
    max-width: 1380px;
}

#MainMenu, footer, header {
    visibility: hidden;
}

[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
.stDeployButton {
    display: none !important;
    visibility: hidden !important;
}

.topbar {
    background: #ffffff;
    border-radius: 0 0 24px 24px;
    padding: 20px 24px;
    box-shadow: 0 8px 26px rgba(15,23,42,0.06);
    margin-bottom: 22px;
}

.logo-img {
    width: 220px;
    max-width: 100%;
    object-fit: contain;
}

.brand-title {
    display: flex;
    align-items: center;
    gap: 14px;
}

.bot-icon {
    background: var(--blue);
    color: white;
    width: 48px;
    height: 48px;
    border-radius: 50%;
    display:flex;
    justify-content:center;
    align-items:center;
    font-size:24px;
    font-weight:800;
}

.brand-title h1 {
    margin:0;
    font-size:40px;
    color:var(--text);
    font-weight:800;
}

.brand-subtitle {
    margin-left:64px;
    color:#334155;
    font-size:16px;
    margin-top:4px;
}

.user-pill {
    background:white;
    border:1px solid var(--border);
    padding:12px 18px;
    border-radius:14px;
    box-shadow:0 4px 16px rgba(15,23,42,0.06);
    font-weight:700;
    text-align:center;
}

.hero {
    background: linear-gradient(135deg, var(--blue-dark), var(--blue));
    color:white;
    padding:36px 42px;
    border-radius:24px;
    box-shadow:0 16px 40px rgba(15,23,42,0.16);
    margin-bottom:18px;
    display:flex;
    justify-content:space-between;
    align-items:center;
}

.hero h2 {
    font-size:36px;
    margin:0 0 12px 0;
    font-weight:800;
}

.hero p {
    font-size:17px;
    margin:0;
    line-height:1.5;
}

.hero-graphic {
    font-size:70px;
    opacity:.95;
}

.layout-card {
    background:white;
    border:1px solid var(--border);
    border-radius:22px;
    box-shadow:0 14px 35px rgba(15,23,42,0.08);
    padding:24px;
    margin-bottom:18px;
}

.assistant-name {
    font-size:28px;
    font-weight:800;
    margin-bottom:18px;
}

.avatar-wrap {
    display:flex;
    justify-content:center;
    position:relative;
}

.avatar-img {
    width:230px;
    height:230px;
    border-radius:50%;
    object-fit:cover;
    border:5px solid #0b4f8a;
    box-shadow:0 8px 24px rgba(15,23,42,0.18);
}

.status-dot {
    position:absolute;
    bottom:12px;
    right:34px;
    width:23px;
    height:23px;
    background:#22c55e;
    border:4px solid white;
    border-radius:50%;
}

.online-box {
    background:#dcfce7;
    color:#166534;
    padding:13px 18px;
    border-radius:14px;
    font-weight:700;
    margin-top:20px;
}

.ask-title {
    font-size:28px;
    font-weight:800;
    margin-bottom:18px;
    color:var(--text);
}

.info-box {
    background:#f8fafc;
    border:1px dashed #cbd5e1;
    padding:14px 16px;
    border-radius:14px;
    color:#334155;
    margin-bottom:16px;
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

.stButton > button {
    border-radius:14px !important;
    font-weight:800 !important;
    min-height:52px;
    border:1px solid var(--border) !important;
    background:white !important;
    color:#111827 !important;
    box-shadow:0 5px 16px rgba(15,23,42,0.05) !important;
}

.stButton > button:hover {
    background:#eff6ff !important;
    border-color:#93c5fd !important;
}

div[data-testid="stForm"] {
    border:1px solid var(--border);
    background:#ffffff;
    padding:20px;
    border-radius:17px;
    box-shadow:0 8px 22px rgba(15,23,42,0.05);
}

div[data-testid="stFormSubmitButton"] button {
    background:var(--blue) !important;
    color:white !important;
    border:none !important;
}

div[data-testid="stTextInput"] input {
    border-radius:12px;
    min-height:50px;
}

div[data-testid="stExpander"] {
    background:#ffffff;
    border:1px solid var(--border);
    border-radius:16px;
    box-shadow:0 5px 16px rgba(15,23,42,0.04);
    margin-bottom:10px;
}

@media only screen and (max-width:900px) {
    .brand-title h1 { font-size:30px; }
    .brand-subtitle { margin-left:0; }
    .hero { padding:26px 22px; }
    .hero h2 { font-size:28px; }
    .hero-graphic { display:none; }
    .avatar-img { width:200px; height:200px; }
}
</style>
""", unsafe_allow_html=True)

# =====================================================
# LOAD KNOWLEDGE
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

# =====================================================
# HELPERS
# =====================================================

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

TAX_CATEGORIES = {
    "advance tax",
    "form 16",
    "home loan & insurance",
    "hra",
    "income tax 2026",
    "nps",
    "penalty & delay",
    "salary tax basics",
    "sodexo / meal benefit",
    "tax claim process",
    "tax regime",
}

SALARY_CATEGORIES = {
    "reimbursements",
    "salary structure",
}

LABOUR_CATEGORIES = {
    "labour code",
    "labor code",
    "labour codes",
    "labor codes",
}

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

    if any(x in combined for x in ["compliance", "tds", "gst", "filing", "return", "deduction", "80c", "80ccd"]):
        return "Compliance Support"

    if any(x in combined for x in ["salary", "payroll", "ctc", "reimbursement"]):
        return "Salary Queries"

    return "Tax FAQs"

def add_module_column(df):
    if df.empty:
        return df
    df = df.copy()
    df["Main Module"] = df.apply(get_module_for_row, axis=1)
    return df

faq_df = add_module_column(faq_df)

def get_categories_for_module(df, module):
    if df.empty:
        return []
    cat_col = get_category_column(df)
    if not cat_col:
        return []

    filtered = df[df["Main Module"] == module].copy()
    excluded = ["section mapping", "mapping", "section-mapping", ""]
    categories = (
        filtered[cat_col]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )
    categories = [c for c in categories if c.lower() not in excluded]
    categories.sort(key=lambda x: x.lower())
    return categories

def get_questions_by_module_category(df, module, category):
    cat_col = get_category_column(df)
    if not cat_col:
        return pd.DataFrame()

    filtered = df[
        (df["Main Module"] == module) &
        (df[cat_col].astype(str).str.strip().str.lower() == category.strip().lower())
    ].copy()

    q_col = get_question_column(filtered)
    if q_col:
        filtered = filtered[filtered[q_col].astype(str).str.strip() != ""]
    return filtered

def render_answer(row):
    if is_protected(row):
        spoc, email = get_spoc(row)
        email_html = f"<br><b>Email:</b> {email}" if email else ""
        st.markdown(f"""
        <div class="protected-box">
        <b>🔒 Protected Information</b><br>
        This information is protected and cannot be displayed here.<br><br>
        Please contact the designated SPOC:<br>
        <b>SPOC:</b> {spoc}
        {email_html}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="answer-box">
        <b>Koenig Stride Answer:</b><br>
        {get_answer_text(row)}
        </div>
        """, unsafe_allow_html=True)

# =====================================================
# AI / SEARCH
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

    # fallback keyword search
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

Rules:
1. Use only the knowledge base below.
2. Do not invent facts.
3. If Protected is YES, do not reveal protected information.
4. If protected, route employee to SPOC.
5. Be concise and professional.

Knowledge Base:
{context}
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": query}
            ],
            temperature=0.2
        )
        return resp.choices[0].message.content
    except Exception:
        return get_answer_text(top)

# =====================================================
# SESSION STATE
# =====================================================

if "menu_open" not in st.session_state:
    st.session_state.menu_open = False

if "selected_module" not in st.session_state:
    st.session_state.selected_module = None

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

def submit_query(query):
    results = semantic_search(query)

    if results.empty:
        st.session_state.chat_history.append({
            "query": query,
            "type": "not_found",
            "answer": "Knowledge base is not loaded.",
            "similarity": 0,
            "source": ""
        })
        return

    top = results.iloc[0]
    sim = float(top.get("similarity", 0))

    if sim < 0.15:
        st.session_state.chat_history.append({
            "query": query,
            "type": "not_found",
            "answer": "I could not find a relevant answer. Please try differently or contact the relevant SPOC.",
            "similarity": sim,
            "source": safe_get(top, "Source")
        })
        return

    if is_protected(top):
        spoc, email = get_spoc(top)
        st.session_state.chat_history.append({
            "query": query,
            "type": "protected",
            "answer": "This information is protected and cannot be displayed here.",
            "spoc": spoc,
            "email": email,
            "similarity": sim,
            "source": safe_get(top, "Source")
        })
        return

    ans = generate_response(query, results)
    st.session_state.chat_history.append({
        "query": query,
        "type": "answer",
        "answer": ans,
        "similarity": sim,
        "source": safe_get(top, "Source")
    })

# =====================================================
# TOP HEADER
# =====================================================

st.markdown("<div class='topbar'>", unsafe_allow_html=True)

h1, h2, h3 = st.columns([1.3, 3.2, 1.2])

with h1:
    if LOGO_B64:
        st.markdown(f"<img class='logo-img' src='data:image/png;base64,{LOGO_B64}'>", unsafe_allow_html=True)
    else:
        st.markdown("## KOENIG")

with h2:
    st.markdown("""
    <div class="brand-title">
        <div class="bot-icon">☻</div>
        <h1>Koenig Stride</h1>
    </div>
    <div class="brand-subtitle">Tax & Entity Nexus Assistant — Step Forward</div>
    """, unsafe_allow_html=True)

with h3:
    st.markdown("<div class='user-pill'>👤 Sarika · ●</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

if load_error:
    st.error(load_error)

# =====================================================
# MAIN UI
# =====================================================

left, right = st.columns([1.05, 3.8], gap="large")

with left:
    st.markdown("<div class='layout-card'>", unsafe_allow_html=True)
    st.markdown("<div class='assistant-name'>👩‍💼 Sarika</div>", unsafe_allow_html=True)

    if SARIKA_B64:
        st.markdown(f"""
        <div class="avatar-wrap">
            <img class="avatar-img" src="data:image/png;base64,{SARIKA_B64}">
            <span class="status-dot"></span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("Sarika image not found.")

    st.markdown("<div class='online-box'>● Sarika is online</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with right:
    st.markdown("""
    <div class="hero">
        <div>
            <h2>Welcome to Koenig Stride</h2>
            <p>Select Start Here to browse guided help, or use the chat box to ask directly.</p>
        </div>
        <div class="hero-graphic">💬</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div class='layout-card'>", unsafe_allow_html=True)
    
    if st.button("🚀 Start Here", use_container_width=True):
        st.session_state.menu_open = True

    if st.session_state.menu_open:
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
        st.markdown("<div class='layout-card'>", unsafe_allow_html=True)
        st.markdown(f"<span class='selected-pill'>Selected: {selected}</span>", unsafe_allow_html=True)
        st.markdown("<div class='ask-title'>Select Category</div>", unsafe_allow_html=True)

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

    st.markdown("<div class='layout-card'>", unsafe_allow_html=True)
    st.markdown("<div class='ask-title'>💬 Ask Koenig Stride Directly</div>", unsafe_allow_html=True)

    with st.form("ask_form", clear_on_submit=True):
        query = st.text_input("Type your question here", placeholder="Example: What is NPS?")
        submitted = st.form_submit_button("➤ Ask Koenig Stride")

    if submitted and query.strip():
        with st.spinner("Koenig Stride is thinking..."):
            submit_query(query.strip())

    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.chat_history:
        st.markdown("<div class='layout-card'>", unsafe_allow_html=True)
        st.markdown("<div class='ask-title'>Conversation</div>", unsafe_allow_html=True)

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
                st.markdown(f"""
                <div class='bot-bubble'>
                <b>Koenig Stride:</b><br>
                {item['answer']}<br><br>
                <span class='small-text'>Source: {item.get('source','')} | Similarity: {item.get('similarity',0):.2f}</span>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

# =====================================================
# ADMIN PREVIEW
# =====================================================

with st.expander("Admin Preview: Knowledge Base"):
    if not faq_df.empty:
        st.success(f"Knowledge base loaded successfully. Total records: {len(faq_df)}")
        cols = [c for c in ["Main Module", "Source", "Category", "Question", "Protected", "SPOC Name", "SPOC Email"] if c in faq_df.columns]
        st.dataframe(faq_df[cols], use_container_width=True)
    else:
        st.warning("No knowledge records loaded.")

st.caption("Koenig Stride · Internal Tax & Entity Nexus Assistant")
