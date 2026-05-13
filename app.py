import streamlit as st
import pandas as pd
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from openai import OpenAI
import numpy as np

# =====================================================
# KOENIG STRIDE
# GPT + Semantic Search Version with Logo Correction
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
# BASIC CSS
# =====================================================

st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
    background: #f7f9fc;
}

.block-container {
    padding-top: 2rem;
    max-width: 1250px;
}

.header-box {
    background: linear-gradient(120deg, #0f172a 0%, #123c92 55%, #2563eb 100%);
    color: white;
    padding: 28px 32px;
    border-radius: 24px;
    margin-bottom: 25px;
    box-shadow: 0 12px 30px rgba(15, 23, 42, 0.15);
}

.header-box h1 {
    margin: 0;
    font-size: 42px;
    font-weight: 800;
}

.header-box p {
    margin: 6px 0 0 0;
    font-size: 16px;
    opacity: 0.92;
}

.assistant-card {
    background: white;
    padding: 18px;
    border-radius: 22px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
}

.chat-card {
    background: white;
    padding: 22px;
    border-radius: 22px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
}

.user-bubble {
    background: #dbeafe;
    padding: 14px 16px;
    border-radius: 16px;
    margin: 10px 0;
    border: 1px solid #bfdbfe;
}

.bot-bubble {
    background: #f8fafc;
    padding: 14px 16px;
    border-radius: 16px;
    margin: 10px 0;
    border: 1px solid #e2e8f0;
}

.protected-bubble {
    background: #fff7ed;
    padding: 14px 16px;
    border-radius: 16px;
    margin: 10px 0;
    border-left: 6px solid #f97316;
    border-top: 1px solid #fed7aa;
    border-bottom: 1px solid #fed7aa;
    border-right: 1px solid #fed7aa;
}

.online-pill {
    background: #dcfce7;
    color: #166534;
    padding: 10px 14px;
    border-radius: 14px;
    font-weight: 600;
    margin-top: 12px;
}

.help-list {
    background: #f8fafc;
    padding: 16px;
    border-radius: 16px;
    border: 1px solid #e2e8f0;
    margin-top: 16px;
}

.small-text {
    color: #64748b;
    font-size: 12px;
}

.stButton button {
    border-radius: 12px !important;
    font-weight: 600 !important;
}

@media only screen and (max-width: 768px) {
    .header-box h1 {
        font-size: 30px;
    }
    .header-box {
        padding: 20px;
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
# HEADER WITH LOGO FIX
# =====================================================

logo_col, title_col = st.columns([1.2, 4.2])

with logo_col:
    if LOGO_PATH.exists():
        st.image(
            str(LOGO_PATH),
            use_container_width=True
        )
    else:
        st.markdown("### KOENIG")

with title_col:
    st.markdown("""
    <div class="header-box">
        <h1>🤖 Koenig Stride</h1>
        <p>Tax & Entity Nexus Assistant — Step Forward</p>
    </div>
    """, unsafe_allow_html=True)

if load_error:
    st.error(load_error)

if client is None:
    st.warning("OpenAI API key not found in Streamlit Secrets. The app will use direct knowledge-base answers instead of GPT responses.")

# =====================================================
# MAIN UI
# =====================================================

left, right = st.columns([1.15, 3.2])

with left:
    st.markdown("<div class='assistant-card'>", unsafe_allow_html=True)

    st.markdown("### 👩‍💼 Sarika")

    if SARIKA_PATH.exists():
        st.image(str(SARIKA_PATH), use_container_width=True)
    else:
        st.info("Sarika image not found.")

    st.markdown("<div class='online-pill'>● Sarika is online</div>", unsafe_allow_html=True)

    st.markdown("""
    <div class="help-list">
        <b>I can help with:</b><br><br>
        ✅ Tax FAQs<br>
        ✅ Salary queries<br>
        ✅ Entity Nexus<br>
        ✅ SPOC routing<br>
        🔒 Protected information routing<br>
        ✅ Compliance support
    </div>
    """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

with right:
    st.markdown("<div class='chat-card'>", unsafe_allow_html=True)
    st.markdown("## 💬 Ask Koenig Stride")

    st.markdown("""
    <div class="bot-bubble">
        <b>Koenig Stride:</b><br>
        Hello 👋 I am Koenig Stride, your interactive Tax & Entity Nexus Assistant.
        Ask me about tax, salary FAQs, entity details, or SPOC guidance.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### Suggested Questions")

    q1, q2 = st.columns(2)
    q3, q4 = st.columns(2)

    suggestions = [
        "Who handles UAE entity compliance?",
        "Tell me about Netherlands entity",
        "Who is the SPOC for payroll tax issues?",
        "What changed in income tax this year?"
    ]

    with q1:
        if st.button(suggestions[0], key="suggest_1"):
            submit_query(suggestions[0])

    with q2:
        if st.button(suggestions[1], key="suggest_2"):
            submit_query(suggestions[1])

    with q3:
        if st.button(suggestions[2], key="suggest_3"):
            submit_query(suggestions[2])

    with q4:
        if st.button(suggestions[3], key="suggest_4"):
            submit_query(suggestions[3])

    with st.form("ask_form", clear_on_submit=True):
        user_query = st.text_input(
            "Type your question here",
            placeholder="Example: Who handles UAE entity compliance?"
        )
        submitted = st.form_submit_button("Ask Koenig Stride", type="primary")

    if submitted and user_query.strip():
        with st.spinner("Koenig Stride is thinking..."):
            submit_query(user_query.strip())

    if st.session_state.chat_history:
        st.markdown("---")
        st.markdown("### Conversation")

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
