# Koenig Stride — Quick-Win Roadmap Changelog

This release applies the **complete quick-win roadmap** from the code review.
Database, knowledge file, and assets remain untouched.

## 🐞 Critical bug fixes

| # | Fix | Where |
|---|---|---|
| 1 | `tax_year` NameError on Salary & TDS upload — variable renamed from `financial_year` → `tax_year` | `render_payroll_upload_engine()` |
| 2 | Ask Sarika chat widget restored — uses `st.chat_input` + `st.chat_message` (input at bottom, history above, like ChatGPT/WhatsApp) | Ask Sarika panel |
| 3 | Removed 6 redundant `init_payroll_database()` calls inside individual functions. One module-level call now cached via `@st.cache_resource` | `init_payroll_database`, `load_salary_structure_master`, `save_salary_structure_master`, `import_employee_master`, `import_salary_monthly`, `import_tds_monthly`, `render_payroll_data_preview` |

## 🔒 Security improvements

| # | Improvement | Default |
|---|---|---|
| 4 | `Welcome@123` auto-reset fallback now disabled by default. Toggle via `st.secrets["ALLOW_DEFAULT_PWD_RESET"] = true` for pilots | `false` (secure) |
| 5 | Admin password no longer hardcoded — reads from `st.secrets["ADMIN_PASSWORD"]`, falls back to `admin123` only if unset | Move to secrets |
| 6 | Proof upload allowlist: only `.pdf`, `.png`, `.jpg`, `.jpeg`, `.xlsx`, `.xls` accepted. Max 5 MB. Filename sanitised | Enforced |
| 9 | Password hashing upgraded from raw SHA-256 to **bcrypt** (12 rounds, salted). Existing SHA-256 hashes in `users.csv` continue to work and are silently re-hashed to bcrypt on next successful login | Auto-upgrade |
| 12 | New `audit_log` table records every login (success/fail), password update, admin reset, declaration submit/approve/reject/delete. Surfaced in Admin Analytics with CSV export | Logged |

## 🎨 UX polish

| # | Polish | Where |
|---|---|---|
| 8 | Locked panels (Ask Sarika, Declarations, Admin tools) now show a clear info banner instead of silently redirecting to Home | Right pane router |
| 8 | Home hero `margin-top` reduced from `80px` → `24px` so the welcome card no longer pushes below the fold on smaller screens | Home panel |
| 8 | Voice Sarika now passes `language="en"` and an Indian-English / tax-jargon prompt to Whisper for far better transcription accuracy on terms like NPS, HRA, Section 80C, Sodexo | `transcribe_audio_with_openai` |
| 10 | Excel template (`.xlsx`) download button added to Payroll Upload Engine for each upload type. Employee Master panel now has both CSV + XLSX template downloads | Upload panels |
| 11 | **`render_admin_analytics_dashboard()` implemented** — Users, Declarations (counts + amounts + section breakdown + top employees), Knowledge base, Payroll DB row counts, Storage health warning, recent Audit Log (CSV-exportable) | New panel |

## 📦 New files

- `.streamlit_secrets_example.toml` — copy-paste template for Streamlit Cloud Secrets
- `CHANGELOG_QUICKWINS.md` — this file

## ⚠️ Still pending (intentionally NOT done in this release)

- **Migrate SQLite + proofs to Postgres + S3** — requires you to choose a host (Supabase / Neon / RDS / S3 / R2). Streamlit Cloud's filesystem **will wipe** your DB on container restart. You can keep using the app as a pilot, but for go-live this is the next blocker.
- **Split `app.py` into modules** — 3892 lines is still a lot. We can do this in a follow-up release once you confirm the structure (suggestion: `auth/`, `knowledge/`, `payroll/`, `declarations/`, `employees/`, `voice/`, `ui/`).

## How to deploy

1. Replace `app.py` and `requirements.txt` in your GitHub repo with the files from this ZIP.
2. (Recommended) In Streamlit Cloud → App settings → Secrets, paste:
   ```toml
   OPENAI_API_KEY = "sk-..."
   ADMIN_PASSWORD = "YourStrongAdminPwd#2026"
   ALLOW_DEFAULT_PWD_RESET = false
   ```
3. Push. Streamlit Cloud auto-redeploys in ~1 minute.
4. Existing employee accounts continue to work. The first time each user logs in, their SHA-256 hash will be silently upgraded to bcrypt.
