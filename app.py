import streamlit as st
import pandas as pd
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from openai import OpenAI
import numpy as np
import base64

# =====================================================
# KOENIG STRIDE - CATEGORY FAQ + MODERN UI VERSION
# GPT + Semantic Search + Protected Logic + Category Navigation
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
    --bg: #f6f8fb;
    --card: #ffffff;
    --blue: #155be8;
    --blue-dark: #071a4f;
    --text: #111827;
    --muted: #64748b;
    --border: #dbe3ef;
    --shadow: 0 14px 35px rgba(15, 23, 42, 0.08);
}

[data-testid="stAppViewContainer"] {
    background: var(--bg);
}

[data-testid="stHeader"] {
    background: rgba(246, 248, 251, 0.85);
}

.block-container {
    padding-top: 1.1rem;
    max-width: 1380px;
}

#MainMenu, footer {
    visibility: hidden;
}

.topbar {
    background: #ffffff;
    border-bottom: 1px solid #e5eaf2;
    padding: 18px 22px;
    border-radius: 0 0 24px 24px;
    box-shadow: 0 8px 26px rgba(15,23,42,0.05);
    margin-bottom: 22px;
}

.logo-img {
    width: 220px;
    max-width: 100%;
    object-fit: contain;
    display: block;
}

.brand-title {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-top: 2px;
}

.bot-icon {
    width: 46px;
    height: 46px;
    border-radius: 50%;
    background: #155be8;
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 23px;
    font-weight: 800;
}

.brand-title h1 {
    margin: 0;
    font-size: 38px;
    font-weight: 800;
    letter-spacing: -0.7px;
    color: var(--text);
}

.brand-subtitle {
    color: #334155;
    margin-left: 62px;
    margin-top: 4px;
    font-size: 16px;
}

.header-actions {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    align-items: center;
    padding-top: 10px;
}

.help-pill {
    color: #111827;
    font-weight: 600;
    padding: 10px 12px;
}

.user-pill {
    background: #ffffff;
    border: 1px solid var(--border);
    padding: 12px 18px;
    border-radius: 14px;
    box-shadow: 0 4px 16px rgba(15,23,42,0.06);
    font-weight: 700;
}

.layout-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 22px;
    box-shadow: var(--shadow);
}

.assistant-card {
    padding: 22px;
    margin-bottom: 16px;
}

.assistant-name {
    font-size: 27px;
    font-weight: 800;
    color: var(--text);
    margin-bottom: 20px;
}

.avatar-circle-wrap {
    width: 100%;
    display: flex;
    justify-content: center;
    position: relative;
}

.avatar-circle {
    width: 245px;
    height: 245px;
    border-radius: 50%;
    overflow: hidden;
    border: 5px solid #0b4f8a;
    background: #111827;
    box-shadow: inset 0 0 0 8px #ffffff;
}

.avatar-circle img {
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.status-dot {
    position: absolute;
    bottom: 18px;
    right: 35px;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: #22c55e;
    border: 4px solid white;
}

.online-pill {
    background: #dcfce7;
    color: #166534;
    padding: 13px 18px;
    border-radius: 14px;
    margin-top: 22px;
    font-weight: 700;
}

.help-card {
    padding: 24px;
}

.help-card h3 {
    margin: 0 0 20px 0;
    font-size: 22px;
}

.help-line {
    font-size: 17px;
    margin: 12px 0;
    color: #111827;
}

.hero {
    min-height: 170px;
    border-radius: 22px;
    background:
        radial-gradient(circle at 85% 40%, rgba(255,255,255,0.18), transparent 30%),
        linear-gradient(120deg, #071a4f 0%, #063a9e 55%, #1267f1 100%);
    color: white;
    padding: 42px 46px;
    box-shadow: var(--shadow);
    margin-bottom: 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.hero h2 {
    font-size: 34px;
    margin: 0 0 14px 0;
    font-weight: 800;
}

.hero p {
    font-size: 18px;
    line-height: 1.6;
    margin: 0;
    max-width: 760px;
}

.hero-graphic {
    font-size: 76px;
    opacity: 0.9;
    margin-right: 15px;
}

.main-card {
    padding: 28px 30px;
}

.ask-title {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 29px;
    font-weight: 800;
    margin-bottom: 22px;
    color: var(--text);
}

.welcome-bubble {
    background: linear-gradient(180deg, #f8fbff 0%, #eef5ff 100%);
    border: 1px solid var(--border);
    padding: 20px 24px;
    border-radius: 17px;
    font-size: 18px;
    line-height: 1.55;
    margin-bottom: 26px;
}

.section-title {
    font-size: 22px;
    font-weight: 800;
    margin: 10px 0 18px 0;
}

.user-bubble {
    background: #dbeafe;
    padding: 16px 18px;
    border-radius: 17px;
    margin: 13px 0;
    border: 1px solid #bfdbfe;
    font-size: 16px;
}

.bot-bubble {
    background: #f8fafc;
    padding: 16px 18px;
    border-radius: 17px;
    margin: 13px 0;
    border: 1px solid #e2e8f0;
    font-size: 16px;
}

.answer-bubble {
    background: #f0fdf4;
    padding: 16px 18px;
    border-radius: 17px;
    margin: 10px 0 15px 0;
    border: 1px solid #bbf7d0;
    font-size: 16px;
}

.protected-bubble {
    background: #fff7ed;
    padding: 16px 18px;
    border-radius: 17px;
    margin: 13px 0;
    border-left: 6px solid #f97316;
    border-top: 1px solid #fed7aa;
    border-bottom: 1px solid #fed7aa;
    border-right: 1px solid #fed7aa;
    font-size: 16px;
}

.small-text {
    color: var(--muted);
    font-size: 12px;
}

.category-help {
    background: #f8fafc;
    border: 1px dashed #cbd5e1;
    padding: 14px 16px;
    border-radius: 14px;
    color: #334155;
    margin-bottom: 18px;
}

div[data-testid="stExpander"] {
    background: #ffffff;
    border: 1px solid var(--border);
    border-radius: 16px;
    box-shadow: 0 5px 16px rgba(15,23,42,0.04);
    margin-bottom: 10px;
}

.stButton > button {
    border-radius: 13px !important;
    font-weight: 700 !important;
    border: 1px solid var(--border) !important;
    background: #ffffff !important;
    color: #111827 !important;
    box-shadow: 0 5px 16px rgba(15,23,42,0.05) !important;
    min-height: 48px;
}

.stButton > button:hover {
    border-color: #93c5fd !important;
    background: #eff6ff !important;
}

div[data-testid="stForm"] {
    border: 1px solid var(--border);
    background: #ffffff;
    padding: 20px;
    border-radius: 17px;
    box-shadow: 0 8px 22px rgba(15,23,42,0.05);
}

div[data-testid="stFormSubmitButton"] button {
    background: #155be8 !important;
    color: white !important;
    border: none !important;
    padding-left: 22px !important;
    padding-right: 22px !important;
}

div[data-testid="stTextInput"] input {
    border-radius: 12px;
    min-height: 50px;
    font-size: 16px;
}

@media only screen and (max-width: 900px) {
    .brand-title h1 {
        font-size: 29px;
    }
    .brand-subtitle {
        margin-left: 0;
    }
    .hero {
        padding: 28px 24px;
    }
    .hero h2 {
        font-size: 27px;
    }
    .hero-graphic {
        display: none;
    }
    .avatar-circle {
        width: 210px;
        height: 210px;
    }
}
</style>
""", unsafe_allow_html=True)

# =====================================================
# OPENAI CLIENT
# =====================================================

def get_openai_client():
    api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)

client = get_openai_client()

# =====================================================
# EMBEDDING MODEL
# =====================================================

@st.cache_resource
def load_embedding_model():
    return SentenceTransformer("all-MiniLM-L6-v2")

model = load_embedding_model()

# =====================================================
# LOAD KNOWLEDGE BASE
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

        faq_df = pd.concat(frames, ignore_index=True).fillna("")
        return faq_df, ""

    except Exception as e:
        return pd.DataFrame(), str(e)

faq_df, load_error = load_knowledge()

# =====================================================
# HELPER FUNCTIONS
# =====================================================

def safe_col(df, col):
    if col not in df.columns:
        df[col] = ""
    return df[col].astype(str)

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
    for col in [
        "Display Message (Voice)",
        "Voice Response",
        "Answer (Internal)",
        "Answer",
        "Response"
    ]:
        value = safe_get(row, col)
        if value:
            return value
    return "Answer found, but response text is blank in the knowledge file."

def get_spoc(row):
    spoc_name = safe_get(row, "SPOC Name", "Relevant SPOC")
    spoc_email = safe_get(row, "SPOC Email", "")
    return spoc_name, spoc_email

def get_category_column(df):
    possible_cols = ["Category", "Section", "Topic", "Module"]
    for col in possible_cols:
        if col in df.columns:
            return col
    return None

def get_question_column(df):
    possible_cols = ["Question", "Questions", "FAQ", "Query"]
    for col in possible_cols:
        if col in df.columns:
            return col
    return None

def get_categories(df):
    category_col = get_category_column(df)

    if category_col is None or df.empty:
        return []

    categories = (
        df[category_col]
        .dropna()
        .astype(str)
        .str.strip()
        .replace("", np.nan)
        .dropna()
        .unique()
        .tolist()
    )

    excluded = ["section mapping", "mapping", "section-mapping"]
    categories = [
        c for c in categories
        if c.strip().lower() not in excluded
    ]

    categories.sort(key=lambda x: x.lower())
    return categories

def get_questions_by_category(df, category):
    category_col = get_category_column(df)

    if category_col is None:
        return pd.DataFrame()

    filtered = df[
        df[category_col].astype(str).str.strip().str.lower() == category.strip().lower()
    ].copy()

    question_col = get_question_column(filtered)
    if question_col:
        filtered = filtered[
            filtered[question_col].astype(str).str.strip() != ""
        ]

    return filtered

def render_answer_from_row(row):
    if is_protected(row):
        spoc_name, spoc_email = get_spoc(row)

        email_line = f"<br><b>Email:</b> {spoc_email}" if spoc_email else ""

        st.markdown(f"""
        <div class="protected-bubble">
            <b>🔒 Protected Information</b><br>
            This information is protected and cannot be displayed here.<br><br>
            Please contact the designated SPOC:<br>
            <b>SPOC:</b> {spoc_name}
            {email_line}
        </div>
        """, unsafe_allow_html=True)

    else:
        answer = get_answer_text(row)

        st.markdown(f"""
        <div class="answer-bubble">
            <b>Koenig Stride Answer:</b><br>
            {answer}
        </div>
        """, unsafe_allow_html=True)

# =====================================================
# PREPARE SEMANTIC SEARCH DATA
# =====================================================

if not faq_df.empty:
    faq_df["combined_text"] = (
        safe_col(faq_df, "Question") + " " +
        safe_col(faq_df, "Keywords") + " " +
        safe_col(faq_df, "Alternate Phrases") + " " +
        safe_col(faq_df, "Category") + " " +
        safe_col(faq_df, "Answer (Internal)") + " " +
        safe_col(faq_df, "Display Message (Voice)")
    )
else:
    faq_df["combined_text"] = ""

@st.cache_resource
def create_embeddings(texts):
    if not texts:
        return np.array([])
    return model.encode(texts, show_progress_bar=False)

embeddings = create_embeddings(faq_df["combined_text"].tolist()) if not faq_df.empty else np.array([])

def semantic_search(user_query, top_k=3):
    if faq_df.empty or embeddings.size == 0:
        return pd.DataFrame()

    query_embedding = model.encode([user_query])
    similarities = cosine_similarity(query_embedding, embeddings)[0]
    top_indices = np.argsort(similarities)[::-1][:top_k]

    results = faq_df.iloc[top_indices].copy()
    results["similarity"] = similarities[top_indices]
    return results

# =====================================================
# GPT RESPONSE
# =====================================================

def generate_gpt_response(user_query, search_results):
    if client is None:
        top_row = search_results.iloc[0]
        return get_answer_text(top_row)

    context = ""

    for _, row in search_results.iterrows():
        context += f"""
Question: {safe_get(row, 'Question')}
Answer: {get_answer_text(row)}
Protected: {safe_get(row, 'Protected')}
SPOC: {safe_get(row, 'SPOC Name')}
Email: {safe_get(row, 'SPOC Email')}
Source: {safe_get(row, 'Source')}

"""

    system_prompt = f"""
You are Koenig Stride, an internal Tax & Entity Nexus Assistant for Koenig.

Rules:
1. Use only the provided knowledge base context.
2. Do not invent facts.
3. Be professional, concise, and helpful.
4. If information is protected, do not reveal the protected answer.
5. If information is protected, tell the employee to contact the SPOC.
6. If the answer is not available in the context, say that it is not available in the current knowledge base.

Knowledge Base Context:
{context}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ],
        temperature=0.2
    )

    return response.choices[0].message.content

# =====================================================
# SESSION STATE
# =====================================================

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

def submit_query(query):
    results = semantic_search(query)

    if results.empty:
        st.session_state.chat_history.append({
            "query": query,
            "type": "not_found",
            "answer": "Knowledge base is empty or not loaded.",
            "spoc_name": "",
            "spoc_email": "",
            "similarity": 0,
            "source": ""
        })
        return

    top_row = results.iloc[0]
    similarity = float(top_row.get("similarity", 0))

    if similarity < 0.25:
        st.session_state.chat_history.append({
            "query": query,
            "type": "not_found",
            "answer": "I could not find a relevant answer in the current Koenig Stride knowledge base. Please try asking differently or contact the relevant SPOC.",
            "spoc_name": "",
            "spoc_email": "",
            "similarity": similarity,
            "source": safe_get(top_row, "Source")
        })
        return

    if is_protected(top_row):
        spoc_name, spoc_email = get_spoc(top_row)
        st.session_state.chat_history.append({
            "query": query,
            "type": "protected",
            "answer": "This information is protected and cannot be displayed here.",
            "spoc_name": spoc_name,
            "spoc_email": spoc_email,
            "similarity": similarity,
            "source": safe_get(top_row, "Source")
        })
        return

    answer = generate_gpt_response(query, results)

    st.session_state.chat_history.append({
        "query": query,
        "type": "answer",
        "answer": answer,
        "spoc_name": safe_get(top_row, "SPOC Name"),
        "spoc_email": safe_get(top_row, "SPOC Email"),
        "similarity": similarity,
        "source": safe_get(top_row, "Source")
    })

# =====================================================
# TOP HEADER
# =====================================================

st.markdown("<div class='topbar'>", unsafe_allow_html=True)

h1, h2, h3 = st.columns([1.35, 3.3, 1.25])

with h1:
    if LOGO_B64:
        st.markdown(
            f"<img class='logo-img' src='data:image/png;base64,{LOGO_B64}'>",
            unsafe_allow_html=True
        )
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
    st.markdown("""
    <div class="header-actions">
        <div class="help-pill">❔ Help</div>
        <div class="user-pill">👤 Sarika · ●</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

if load_error:
    st.error(load_error)

if client is None:
    st.warning("OpenAI API key not found in Streamlit Secrets. The app will use direct knowledge-base answers instead of GPT responses.")

# =====================================================
# MAIN UI
# =====================================================

left, right = st.columns([1.05, 3.8], gap="large")

with left:
    st.markdown("<div class='layout-card assistant-card'>", unsafe_allow_html=True)
    st.markdown("<div class='assistant-name'>👩‍💼 Sarika</div>", unsafe_allow_html=True)

    if SARIKA_B64:
        st.markdown(f"""
        <div class="avatar-circle-wrap">
            <div class="avatar-circle">
                <img src="data:image/png;base64,{SARIKA_B64}">
            </div>
            <span class="status-dot"></span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("Sarika image not found.")

    st.markdown("<div class='online-pill'>● Sarika is online</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("""
    <div class="layout-card help-card">
        <h3>I can help with:</h3>
        <div class="help-line">✅ Tax FAQs</div>
        <div class="help-line">✅ Salary queries</div>
        <div class="help-line">✅ Entity Nexus</div>
        <div class="help-line">✅ SPOC routing</div>
        <div class="help-line">🔒 Protected information routing</div>
        <div class="help-line">✅ Compliance support</div>
    </div>
    """, unsafe_allow_html=True)

with right:
    st.markdown("""
    <div class="hero">
        <div>
            <h2>Welcome to Koenig Stride</h2>
            <p>Your interactive Tax & Entity Nexus Assistant. Browse categories or ask your question directly.</p>
        </div>
        <div class="hero-graphic">💬</div>
    </div>
    """, unsafe_allow_html=True)

    # -------------------------
    # CATEGORY FAQ NAVIGATION
    # -------------------------
    st.markdown("<div class='layout-card main-card'>", unsafe_allow_html=True)
    st.markdown("<div class='ask-title'>📚 Browse Knowledge by Category</div>", unsafe_allow_html=True)

    st.markdown("""
    <div class="category-help">
        Click any category to view all related questions. Then click a question to see the answer.
        Protected answers will show the correct SPOC instead of sensitive details.
    </div>
    """, unsafe_allow_html=True)

    categories = get_categories(faq_df)

    if categories:
        for category in categories:
            category_df = get_questions_by_category(faq_df, category)

            if category_df.empty:
                continue

            with st.expander(f"📂 {category} ({len(category_df)} questions)", expanded=False):
                question_col = get_question_column(category_df)

                for idx, row in category_df.iterrows():
                    question = safe_get(row, question_col or "Question")

                    if not question:
                        continue

                    with st.expander(f"❓ {question}", expanded=False):
                        render_answer_from_row(row)
    else:
        st.info("No categories found in the knowledge base. Please check the Category column in Excel.")

    st.markdown("</div>", unsafe_allow_html=True)

    # -------------------------
    # CHAT / GPT ASK SECTION
    # -------------------------
    st.markdown("<div class='layout-card main-card' style='margin-top:16px;'>", unsafe_allow_html=True)
    st.markdown("<div class='ask-title'>💬 Ask Koenig Stride</div>", unsafe_allow_html=True)

    st.markdown("""
    <div class="welcome-bubble">
        👋 Hello! I am Koenig Stride, your interactive Tax & Entity Nexus Assistant.<br>
        You can also ask in your own words below.
    </div>
    """, unsafe_allow_html=True)

    with st.form("ask_form", clear_on_submit=True):
        user_query = st.text_input(
            "Type your question here",
            placeholder="Example: Who handles UAE entity compliance?"
        )
        submitted = st.form_submit_button("➤ Ask Koenig Stride")

    if submitted and user_query.strip():
        with st.spinner("Koenig Stride is thinking..."):
            submit_query(user_query.strip())

    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.chat_history:
        st.markdown("<div class='layout-card main-card' style='margin-top:16px;'>", unsafe_allow_html=True)
        st.markdown("<div class='section-title'>Conversation</div>", unsafe_allow_html=True)

        for item in reversed(st.session_state.chat_history[-10:]):
            st.markdown(f"""
            <div class="user-bubble">
                <b>You:</b><br>{item["query"]}
            </div>
            """, unsafe_allow_html=True)

            if item["type"] == "protected":
                email_line = f"<br><b>Email:</b> {item['spoc_email']}" if item.get("spoc_email") else ""
                st.markdown(f"""
                <div class="protected-bubble">
                    <b>🔒 Koenig Stride:</b><br>
                    {item["answer"]}<br><br>
                    Please contact the designated SPOC:<br>
                    <b>SPOC:</b> {item.get("spoc_name", "Relevant SPOC")}
                    {email_line}
                    <br><br>
                    <span class="small-text">
                    Source: {item.get("source", "")} |
                    Similarity: {item.get("similarity", 0):.2f}
                    </span>
                </div>
                """, unsafe_allow_html=True)

            else:
                st.markdown(f"""
                <div class="bot-bubble">
                    <b>Koenig Stride:</b><br>
                    {item["answer"]}
                    <br><br>
                    <span class="small-text">
                    Source: {item.get("source", "")} |
                    Similarity: {item.get("similarity", 0):.2f}
                    </span>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

# =====================================================
# ADMIN PREVIEW
# =====================================================

with st.expander("Admin Preview: Knowledge Base"):
    if not faq_df.empty:
        st.success(f"Knowledge base loaded successfully. Total records: {len(faq_df)}")
        preview_cols = [c for c in ["Source", "Category", "Question", "Protected", "SPOC Name", "SPOC Email"] if c in faq_df.columns]
        st.dataframe(faq_df[preview_cols], use_container_width=True)
    else:
        st.warning("No knowledge records loaded.")

with st.expander("Admin Preview: Semantic Match Test"):
    test_query = st.text_input("Test semantic matching", placeholder="Example: UAE finance SPOC")
    if st.button("Run Match Test"):
        if test_query.strip():
            test_results = semantic_search(test_query.strip())
            if not test_results.empty:
                cols = [c for c in ["Question", "Source", "Protected", "SPOC Name", "SPOC Email", "similarity"] if c in test_results.columns]
                st.dataframe(test_results[cols], use_container_width=True)

st.caption("Koenig Stride · Internal Tax & Entity Nexus Assistant")