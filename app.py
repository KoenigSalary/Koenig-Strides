import streamlit as st
import pandas as pd
from rapidfuzz import fuzz
from pathlib import Path
from datetime import datetime

# -----------------------------
# Page Config
# -----------------------------
st.set_page_config(
    page_title="Koenig Stride",
    page_icon="🤖",
    layout="wide"
)

# -----------------------------
# File Paths
# -----------------------------
BASE_DIR = Path(__file__).parent

EXCEL_PATH = BASE_DIR / "knowledge" / "Koenig_VoiceBot_FAQ_Master.xlsx"
LOGO_PATH = BASE_DIR / "assets" / "koenig_logo.png"
SARIKA_PATH = BASE_DIR / "assets" / "sarika.png"

# -----------------------------
# Styling
# -----------------------------
st.markdown("""
<style>
.main {
    background-color: #f7f9fc;
}
.koenig-header {
    background: linear-gradient(90deg, #0f172a, #1d4ed8);
    padding: 22px;
    border-radius: 18px;
    color: white;
    margin-bottom: 20px;
}
.chat-box {
    background: white;
    padding: 18px;
    border-radius: 16px;
    box-shadow: 0px 2px 12px rgba(0,0,0,0.08);
    margin-bottom: 12px;
}
.user-msg {
    background: #e0f2fe;
    padding: 14px;
    border-radius: 14px;
    margin-bottom: 10px;
}
.bot-msg {
    background: #f1f5f9;
    padding: 14px;
    border-radius: 14px;
    margin-bottom: 10px;
}
.protected-msg {
    background: #fff7ed;
    border-left: 5px solid #f97316;
    padding: 14px;
    border-radius: 12px;
}
.small-muted {
    color: #64748b;
    font-size: 13px;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Load Knowledge Base
# -----------------------------
@st.cache_data
def load_knowledge():
    if not EXCEL_PATH.exists():
        st.error(f"Knowledge file not found: {EXCEL_PATH}")
        return pd.DataFrame(), pd.DataFrame()

    salary_df = pd.read_excel(EXCEL_PATH, sheet_name="Salary & Tax FAQs")
    entity_df = pd.read_excel(EXCEL_PATH, sheet_name="Entity Nexus FAQs")

    salary_df["Source"] = "Salary & Tax FAQs"
    entity_df["Source"] = "Entity Nexus FAQs"

    faq_df = pd.concat([salary_df, entity_df], ignore_index=True)
    faq_df = faq_df.fillna("")

    spoc_df = pd.read_excel(EXCEL_PATH, sheet_name="SPOC Master").fillna("")

    return faq_df, spoc_df


faq_df, spoc_df = load_knowledge()

# -----------------------------
# Helper Functions
# -----------------------------
def normalize(value):
    return str(value).strip().lower()


def is_protected(row):
    return normalize(row.get("Protected", "")) in ["yes", "y", "true", "1"]


def build_search_text(row):
    parts = [
        row.get("Question", ""),
        row.get("Alternate Phrases", ""),
        row.get("Keywords", ""),
        row.get("Category", "")
    ]
    return " ".join([str(x) for x in parts if str(x).strip()])


def search_faq(user_query, df):
    if df.empty or not user_query.strip():
        return None, 0

    best_row = None
    best_score = 0

    for _, row in df.iterrows():
        search_text = build_search_text(row)

        score_question = fuzz.token_sort_ratio(user_query, str(row.get("Question", "")))
        score_keywords = fuzz.partial_ratio(user_query, search_text)
        score = max(score_question, score_keywords)

        if score > best_score:
            best_score = score
            best_row = row

    return best_row, best_score


def get_response(row, score):
    if row is None or score < 55:
        return {
            "type": "not_found",
            "message": (
                "I could not find an exact answer in the Koenig Stride knowledge base. "
                "Please contact the relevant SPOC or try asking in a different way."
            )
        }

    spoc_name = row.get("SPOC Name", "Relevant SPOC")
    spoc_email = row.get("SPOC Email", "")

    if is_protected(row):
        return {
            "type": "protected",
            "message": (
                "This information is protected and cannot be displayed here.\n\n"
                f"Please contact the designated SPOC:\n\n"
                f"**SPOC:** {spoc_name}\n\n"
                f"**Email:** {spoc_email}"
            ),
            "category": row.get("Category", ""),
            "source": row.get("Source", "")
        }

    answer = (
        row.get("Display Message (Voice)", "")
        or row.get("Voice Response", "")
        or row.get("Answer (Internal)", "")
    )

    return {
        "type": "answer",
        "message": answer,
        "category": row.get("Category", ""),
        "source": row.get("Source", ""),
        "spoc_name": spoc_name,
        "spoc_email": spoc_email
    }


def log_query(user_query, result_type, score):
    log_file = BASE_DIR / "chat_logs.csv"
    new_row = pd.DataFrame([{
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "query": user_query,
        "result_type": result_type,
        "score": score
    }])

    if log_file.exists():
        old = pd.read_csv(log_file)
        pd.concat([old, new_row], ignore_index=True).to_csv(log_file, index=False)
    else:
        new_row.to_csv(log_file, index=False)


# -----------------------------
# Header
# -----------------------------
col_logo, col_title = st.columns([1, 5])

with col_logo:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=110)
    else:
        st.markdown("### Koenig")

with col_title:
    st.markdown("""
    <div class="koenig-header">
        <h1 style="margin:0;">Koenig Stride</h1>
        <p style="margin:4px 0 0 0;">Tax & Entity Nexus Support</p>
    </div>
    """, unsafe_allow_html=True)

# -----------------------------
# Main Layout
# -----------------------------
left, right = st.columns([1.2, 3])

with left:
    st.markdown("### 👩‍💼 Support")
    if SARIKA_PATH.exists():
        st.image(str(SARIKA_PATH), use_container_width=True)
    else:
        st.info("Sarika image not found.")

    st.success("Sarika is online")

    st.markdown("#### I can help with:")
    st.write("✅ Tax FAQs")
    st.write("✅ Salary FAQs")
    st.write("✅ Entity Nexus queries")
    st.write("✅ SPOC guidance")
    st.write("🔒 Protected info routing")

    st.markdown("---")
    st.markdown("#### Quick Topics")
    quick_topics = [
        "What changed in income tax from 1 April 2026?",
        "What is the company name of the South Africa entity?",
        "Who is the SPOC for tax queries?",
        "What is my tax regime?"
    ]

    for i, topic in enumerate(quick_topics):
        if st.button(topic, key=f"quick_{i}"):
            st.session_state["pending_query"] = topic

with right:
    st.markdown("### 💬 Ask Koenig Stride")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    default_query = st.session_state.pop("pending_query", "")

    user_query = st.text_input(
        "Type your question here",
        value=default_query,
        placeholder="Example: What changed in income tax from April 2026?"
    )

    ask_clicked = st.button("Ask Koenig Stride", type="primary")

    if ask_clicked and user_query.strip():
        row, score = search_faq(user_query, faq_df)
        response = get_response(row, score)
        log_query(user_query, response["type"], score)

        st.session_state.chat_history.append({
            "query": user_query,
            "response": response,
            "score": score
        })

    if st.session_state.chat_history:
        for item in reversed(st.session_state.chat_history[-8:]):
            st.markdown(f"""
            <div class="user-msg">
                <b>You:</b><br>{item['query']}
            </div>
            """, unsafe_allow_html=True)

            response = item["response"]

            if response["type"] == "protected":
                st.markdown(f"""
                <div class="protected-msg">
                    <b>Koenig Stride:</b><br>
                    {response['message']}
                    <br><br>
                    <span class="small-muted">
                    Category: {response.get('category', '')} | Source: {response.get('source', '')}
                    </span>
                </div>
                """, unsafe_allow_html=True)

            else:
                st.markdown(f"""
                <div class="bot-msg">
                    <b>Koenig Stride:</b><br>
                    {response['message']}
                    <br><br>
                    <span class="small-muted">
                    Match Score: {item['score']}%
                    </span>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="chat-box">
            <b>Koenig Stride:</b><br>
            Hello 👋 I am Koenig Stride, your interactive Tax & Entity Nexus Support.
            Ask me about tax, salary FAQs, entity details, or SPOC guidance.
        </div>
        """, unsafe_allow_html=True)

# -----------------------------
# Admin Knowledge Preview
# -----------------------------
with st.expander("Admin Preview: Knowledge Base Loaded"):
    st.write(f"Total FAQs loaded: {len(faq_df)}")
    st.dataframe(
        faq_df[["Source", "Category", "Question", "Protected", "SPOC Name", "SPOC Email"]],
        use_container_width=True
    )

with st.expander("SPOC Master"):
    st.dataframe(spoc_df, use_container_width=True)
