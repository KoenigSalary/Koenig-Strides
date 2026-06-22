"""
compliance_module.py
====================
Tax Compliance Workflow merged into Koenig Strides.

Provides employee-facing declaration / proof submission panels and
admin-facing review panels. Data lives in Supabase (Postgres) so it
survives Streamlit restarts. Falls back to local SQLite if
DATABASE_URL is not configured (dev only — data wipes on restart).

This module is import-safe: it only touches the database when a
public function is called, never at import time.

Phase A scope (current ship):
    - Tax Regime selection + lock + one-time change request
    - Form 12BB / 124 Investment Declaration (Old Regime only)
    - My Declaration report + Submit & Lock with certification
    - Admin: Review Queue, Regime Change Requests, Compliance Reports

Phase B (next ship):
    - Monthly Allowances (Telephone, Electricity, Professional, Software)
"""

from __future__ import annotations

import io
import html
import json
import re
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


# =====================================================
# CONFIG
# =====================================================

CURRENT_FY = "Tax Year 2026-27"

# 5 MB cap; PDFs and common images only.
MAX_PROOF_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_PROOF_EXT = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_PROOF_MIME = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
}

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


# =====================================================
# TAX RULES MASTER (from tax_rules.py — embedded for self-containment)
# =====================================================

FORM_TITLE = "Form 12BB / 124 — Investment Declaration Form"
FORM_SUBTITLE = (
    "Statement showing particulars of claims by an employee for deduction of tax "
    "under section 392(5)(b) of the Income-tax Act, 2025 read with Rule 205 of the "
    "Income-tax Rules, 2026."
)
DECLARATION_DISCLAIMER = (
    "Non-submission or incorrect submission of documents for Form 12BB / 124 within "
    "the stipulated timeline may lead to disallowance of claimed deductions."
)
PROOF_SUBMISSION_VISIBLE = False

SECTION_MASTER: List[Dict[str, Any]] = [
    {
        "section_code": "80C",
        "display_name": "Section 123 (Earlier 80C) — Specified savings / investments",
        "group_name": "Chapter VIII-A / Schedule XV",
        "items": [
            "Life Insurance Premium", "PPF", "EPF", "ELSS", "Tuition Fees",
            "Tax Saver FD", "NSC", "Sukanya Samriddhi", "Home Loan Principal",
        ],
        "amount_cap": 150000,
        "expected_proof": "Receipt / statement / policy receipt / bank advice",
    },
    {
        "section_code": "80CCD(1B)",
        "display_name": "Section 124 (Earlier 80CCD(1B)) — Additional NPS contribution",
        "group_name": "Chapter VIII-A / Pension deduction",
        "items": ["NPS Additional Contribution"],
        "amount_cap": 50000,
        "expected_proof": "NPS contribution statement / transaction receipt",
    },
    {
        "section_code": "80D",
        "display_name": "Section 126 (Earlier 80D) — Health insurance / preventive health check-up",
        "group_name": "Chapter VIII-A",
        "items": [
            "Medical Insurance - Self / Spouse / Children",
            "Medical Insurance - Parents",
            "Preventive Health Check-up",
        ],
        "amount_cap": None,
        "expected_proof": "Policy receipt / premium certificate / preventive check-up receipt",
    },
    {
        "section_code": "80DD",
        "display_name": "Section 127 (Earlier 80DD) — Maintenance of dependant with disability",
        "group_name": "Chapter VIII-A",
        "items": ["Maintenance including medical treatment of dependant with disability"],
        "amount_cap": None,
        "expected_proof": "Disability certificate and payment proof",
    },
    {
        "section_code": "80DDB",
        "display_name": "Section 128 (Earlier 80DDB) — Specified disease / ailment",
        "group_name": "Chapter VIII-A",
        "items": ["Medical treatment for specified disease / ailment"],
        "amount_cap": None,
        "expected_proof": "Specialist certificate and payment proof",
    },
    {
        "section_code": "80E",
        "display_name": "Section 129 (Earlier 80E) — Interest on higher education loan",
        "group_name": "Chapter VIII-A",
        "items": ["Education Loan Interest"],
        "amount_cap": None,
        "expected_proof": "Interest certificate from lender",
    },
    {
        "section_code": "80G",
        "display_name": "Section 133 (Earlier 80G) — Eligible donations",
        "group_name": "Chapter VIII-A",
        "items": ["Eligible donation"],
        "amount_cap": None,
        "expected_proof": "Donation receipt with donee PAN / registration details",
    },
    {
        "section_code": "24(b)",
        "display_name": "Section 22(1)(b) (Earlier 24(b)) — Interest on home loan",
        "group_name": "Income from House Property",
        "items": ["Interest on home loan"],
        "amount_cap": None,
        "expected_proof": "Home loan interest certificate",
    },
    {
        "section_code": "HRA",
        "display_name": "Form No. 124 — House Rent Allowance",
        "group_name": "Form No. 124 allowances",
        "items": ["House Rent Allowance"],
        "amount_cap": None,
        "expected_proof": "Rent receipts / rent agreement / landlord PAN where applicable",
    },
    {
        "section_code": "CHILD_EDU",
        "display_name": "Form No. 124 — Children Declaration / Children Education Allowance",
        "group_name": "Form No. 124 allowances",
        "items": ["Children Education Allowance"],
        "amount_cap": None,
        "expected_proof": "School fee receipt",
    },
    {
        "section_code": "OTHER_VIA",
        "display_name": "Other eligible Chapter VIII-A deduction (specify section)",
        "group_name": "Chapter VIII-A",
        "items": ["Other eligible deduction"],
        "amount_cap": None,
        "expected_proof": "Applicable proof as per section",
    },
]

SECTION_LOOKUP = {row["section_code"]: row for row in SECTION_MASTER}
SECTION_CODES = [row["section_code"] for row in SECTION_MASTER]

CLAIMANT_OPTIONS = ["Self", "Self + Family", "Parents", "Spouse", "Children", "Dependent"]
CLAIMANT_OPTIONS_80E = ["Self", "Spouse", "Children"]
RELATION_OPTIONS = ["Self", "Father", "Mother", "Spouse", "Son", "Daughter", "Brother", "Sister", "Other"]
LANDLORD_RELATIONS = ["Unrelated", "Father", "Mother", "Spouse", "Brother", "Sister", "Other Relative"]
PROPERTY_OCCUPANCY_OPTIONS = ["Self Occupied", "Rented"]




# =====================================================
# DATABASE LAYER


# =====================================================
# DATABASE LAYER
# Uses Strides' existing DB helpers (_using_postgres, _get_database_url, etc.)
# We accept them via dependency injection from app.py to avoid circular imports.
# =====================================================

_db_ctx: Dict[str, Any] = {}


def init(
    using_postgres_fn,
    get_database_url_fn,
    psycopg2_available: bool,
    write_audit_log_fn=None,
):
    """Wire up the module to Strides' shared DB helpers.

    Called once from app.py at startup. Keeps this module self-contained
    while reusing Strides' existing Postgres / SQLite abstraction.
    """
    _db_ctx["using_postgres"] = using_postgres_fn
    _db_ctx["get_db_url"] = get_database_url_fn
    _db_ctx["psycopg2_available"] = psycopg2_available
    _db_ctx["write_audit_log"] = write_audit_log_fn or (lambda *a, **k: None)


def _get_conn():
    """Return a fresh DB connection (Postgres if configured, else SQLite)."""
    if _db_ctx.get("using_postgres", lambda: False)():
        import psycopg2
        import psycopg2.extras
        return psycopg2.connect(
            _db_ctx["get_db_url"](),
            connect_timeout=8,
            sslmode="require",
        )
    # SQLite fallback (dev only)
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).resolve().parent / "koenig_strides.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _ph() -> str:
    """Parameter placeholder for the active DB engine."""
    return "%s" if _db_ctx.get("using_postgres", lambda: False)() else "?"


def _is_pg() -> bool:
    return _db_ctx.get("using_postgres", lambda: False)()


def _rows_to_dicts(cur) -> List[Dict[str, Any]]:
    """Convert a cursor's rows into list-of-dict regardless of engine."""
    cols = [d[0] for d in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _row_to_dict(cur) -> Optional[Dict[str, Any]]:
    cols = [d[0] for d in cur.description] if cur.description else []
    row = cur.fetchone()
    return dict(zip(cols, row)) if row else None


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _table_columns(conn, table_name: str) -> set[str]:
    cur = conn.cursor()
    try:
        if _is_pg():
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name=%s",
                (table_name,),
            )
            return {row[0] for row in cur.fetchall()}
        cur.execute(f"PRAGMA table_info({table_name})")
        return {row[1] for row in cur.fetchall()}
    finally:
        cur.close()


def _ensure_columns(conn, table_name: str, columns: Dict[str, str]) -> None:
    existing = _table_columns(conn, table_name)
    cur = conn.cursor()
    try:
        for column_name, column_type in columns.items():
            if column_name not in existing:
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        conn.commit()
    finally:
        cur.close()


def _declaration_locked(header: Optional[Dict[str, Any]]) -> bool:
    if not header:
        return False
    return str(header.get("status") or "").upper() == "DECLARATION_LOCKED" or \
        str(header.get("workflow_stage") or "").upper() == "DECLARATION_LOCKED"


# =====================================================
# SCHEMA INITIALISATION
# Auto-creates tables on first call. Idempotent.
# =====================================================

_INIT_DONE = False


def ensure_schema() -> None:
    """Create compliance tables if they don't exist. Safe to call repeatedly."""
    global _INIT_DONE
    if _INIT_DONE:
        return

    pg = _is_pg()
    pk = "SERIAL PRIMARY KEY" if pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    blob = "BYTEA" if pg else "BLOB"
    ts = "TIMESTAMPTZ" if pg else "TEXT"

    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS compliance_declaration_header (
                id {pk},
                employee_id TEXT NOT NULL,
                financial_year TEXT NOT NULL,
                tax_regime TEXT,
                workflow_stage TEXT DEFAULT 'REGIME_SELECTION',
                status TEXT DEFAULT 'DRAFT',
                is_locked INTEGER DEFAULT 0,
                regime_change_used INTEGER DEFAULT 0,
                submitted_on {ts},
                locked_on {ts},
                created_on {ts},
                updated_on {ts}
            )
        """)
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_compliance_header_emp_fy
            ON compliance_declaration_header (employee_id, financial_year)
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS compliance_declaration_items (
                id {pk},
                header_id INTEGER NOT NULL,
                employee_id TEXT NOT NULL,
                financial_year TEXT NOT NULL,
                section_code TEXT NOT NULL,
                section_group TEXT,
                item_name TEXT NOT NULL,
                declared_amount NUMERIC DEFAULT 0,
                actual_amount NUMERIC DEFAULT 0,
                approved_amount NUMERIC DEFAULT 0,
                remarks TEXT,
                expected_proof TEXT,
                status TEXT DEFAULT 'DRAFT',
                reviewer_remarks TEXT,
                claimant_for TEXT,
                relation_to_employee TEXT,
                disease_name TEXT,
                landlord_name TEXT,
                landlord_pan TEXT,
                landlord_relation TEXT,
                rental_property_address TEXT,
                annual_rent NUMERIC DEFAULT 0,
                children_count INTEGER DEFAULT 0,
                metadata_json TEXT,
                resubmission_count INTEGER DEFAULT 0,
                created_on {ts},
                updated_on {ts}
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS compliance_proof_uploads (
                id {pk},
                item_id INTEGER NOT NULL,
                employee_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_size INTEGER,
                file_type TEXT,
                file_bytes {blob},
                uploaded_on {ts},
                review_status TEXT DEFAULT 'SUBMITTED'
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS compliance_regime_change_requests (
                id {pk},
                header_id INTEGER NOT NULL,
                employee_id TEXT NOT NULL,
                financial_year TEXT NOT NULL,
                old_regime TEXT NOT NULL,
                requested_regime TEXT NOT NULL,
                request_reason TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                approver_name TEXT,
                approver_id TEXT,
                reviewer_remarks TEXT,
                requested_on {ts},
                decided_on {ts}
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS compliance_audit_logs (
                id {pk},
                actor_employee_id TEXT,
                action_type TEXT,
                entity_type TEXT,
                entity_id TEXT,
                details TEXT,
                created_on {ts}
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS compliance_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT,
                updated_on {ts}
            )
        """)
        # ---- Phase B: Monthly Allowance Claims ----
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS compliance_allowance_claims (
                id {pk},
                employee_id TEXT NOT NULL,
                financial_year TEXT NOT NULL,
                claim_month TEXT NOT NULL,
                allowance_type TEXT NOT NULL,
                amount NUMERIC NOT NULL DEFAULT 0,
                approved_amount NUMERIC DEFAULT 0,
                expense_details TEXT,
                vendor_name TEXT,
                bill_reference TEXT,
                status TEXT DEFAULT 'SUBMITTED',
                reviewer_remarks TEXT,
                file_name TEXT,
                file_size INTEGER,
                file_type TEXT,
                file_bytes {blob},
                resubmission_count INTEGER DEFAULT 0,
                submitted_on {ts},
                reviewed_on {ts},
                updated_on {ts}
            )
        """)
        _ensure_columns(conn, "compliance_declaration_header", {
            "declaration_verified": "INTEGER DEFAULT 0",
            "declaration_verification_name": "TEXT",
            "declaration_parent_name": "TEXT"
        })
        conn.commit()
        _INIT_DONE = True
    finally:
        cur.close()
        conn.close()


# =====================================================
# AUDIT LOGGING (compliance-local + Strides global)
# =====================================================

def _audit(actor: str, action: str, entity_type: str, entity_id: str, details: str = "") -> None:
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO compliance_audit_logs "
            f"(actor_employee_id, action_type, entity_type, entity_id, details, created_on) "
            f"VALUES ({_ph()},{_ph()},{_ph()},{_ph()},{_ph()},{_ph()})",
            (actor, action, entity_type, entity_id, details, _now()),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass
    # Also notify Strides' global audit log so admin analytics can see compliance activity.
    try:
        _db_ctx.get("write_audit_log", lambda *a, **k: None)(
            f"COMPLIANCE_{action}",
            target_id=entity_id,
            details=f"{entity_type}: {details}",
        )
    except Exception:
        pass


# =====================================================
# CORE DATA FUNCTIONS — HEADER
# =====================================================

def get_or_create_header(employee_id: str, fy: str = CURRENT_FY) -> Dict[str, Any]:
    ensure_schema()
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT * FROM compliance_declaration_header "
            f"WHERE employee_id={_ph()} AND financial_year={_ph()}",
            (employee_id, fy),
        )
        row = _row_to_dict(cur)
        if row:
            return row
        cur.execute(
            f"INSERT INTO compliance_declaration_header "
            f"(employee_id, financial_year, created_on, updated_on) "
            f"VALUES ({_ph()},{_ph()},{_ph()},{_ph()})",
            (employee_id, fy, _now(), _now()),
        )
        conn.commit()
        cur.execute(
            f"SELECT * FROM compliance_declaration_header "
            f"WHERE employee_id={_ph()} AND financial_year={_ph()}",
            (employee_id, fy),
        )
        return _row_to_dict(cur) or {}
    finally:
        cur.close()
        conn.close()


def save_regime(employee_id: str, regime: str) -> None:
    header = get_or_create_header(employee_id)
    if header.get("is_locked"):
        raise ValueError("Tax regime is locked. Raise a regime-change request.")
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"UPDATE compliance_declaration_header "
            f"SET tax_regime={_ph()}, status='DRAFT', updated_on={_ph()} "
            f"WHERE id={_ph()}",
            (regime, _now(), header["id"]),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(employee_id, "SAVE_REGIME", "header", str(header["id"]), regime)


def submit_regime(employee_id: str) -> None:
    header = get_or_create_header(employee_id)
    if not header.get("tax_regime"):
        raise ValueError("Select a regime before submitting.")
    next_stage = "COMPLETE" if header["tax_regime"] == "New Regime" else "DECLARATION"
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"UPDATE compliance_declaration_header "
            f"SET status='SUBMITTED', is_locked=1, submitted_on={_ph()}, locked_on={_ph()}, "
            f"workflow_stage={_ph()}, updated_on={_ph()} WHERE id={_ph()}",
            (_now(), _now(), next_stage, _now(), header["id"]),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(employee_id, "SUBMIT_REGIME", "header", str(header["id"]), header["tax_regime"])


# =====================================================
# CORE DATA FUNCTIONS — DECLARATION ITEMS
# =====================================================

def add_declaration_item(employee_id: str, payload: Dict[str, Any]) -> None:
    header = get_or_create_header(employee_id)
    if header.get("tax_regime") != "Old Regime":
        raise ValueError("Investment declaration is allowed only under Old Regime.")
    if _declaration_locked(header):
        raise ValueError("Declaration is already submitted and locked.")

    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""INSERT INTO compliance_declaration_items
            (header_id, employee_id, financial_year, section_code, section_group, item_name,
             declared_amount, remarks, expected_proof, claimant_for, relation_to_employee,
             disease_name, landlord_name, landlord_pan, landlord_relation,
             rental_property_address, annual_rent, children_count, metadata_json,
             created_on, updated_on)
            VALUES ({','.join([_ph()] * 21)})""",
            (
                header["id"], employee_id, CURRENT_FY,
                payload["section_code"], payload.get("section_group", ""), payload["item_name"],
                int(payload.get("declared_amount") or 0),
                payload.get("remarks", ""), payload.get("expected_proof", ""),
                payload.get("claimant_for", ""), payload.get("relation_to_employee", ""),
                payload.get("disease_name", ""), payload.get("landlord_name", ""),
                payload.get("landlord_pan", ""), payload.get("landlord_relation", ""),
                payload.get("rental_property_address", ""),
                float(payload.get("annual_rent") or 0),
                int(payload.get("children_count") or 0),
                json.dumps(payload.get("metadata", {})),
                _now(), _now(),
            ),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(employee_id, "ADD_DECLARATION_ITEM", "declaration_item", str(header["id"]),
           f"{payload['section_code']}:{payload.get('declared_amount', 0)}")


def update_declaration_item(item_id: int, employee_id: str, payload: Dict[str, Any]) -> None:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT * FROM compliance_declaration_items "
            f"WHERE id={_ph()} AND employee_id={_ph()}",
            (item_id, employee_id),
        )
        item = _row_to_dict(cur)
        if not item:
            raise ValueError("Declaration item not found.")
        if item.get("status") not in ("DRAFT", "RESUBMISSION_REQUIRED", "REJECTED", "RESUBMITTED"):
            raise ValueError("Only draft / resubmission items can be updated.")

        next_status = "RESUBMITTED" if item.get("status") in ("RESUBMISSION_REQUIRED", "REJECTED") else "DRAFT"
        cur.execute(
            f"""UPDATE compliance_declaration_items SET
            section_code={_ph()}, section_group={_ph()}, item_name={_ph()},
            declared_amount={_ph()}, remarks={_ph()}, expected_proof={_ph()},
            claimant_for={_ph()}, relation_to_employee={_ph()}, disease_name={_ph()},
            landlord_name={_ph()}, landlord_pan={_ph()}, landlord_relation={_ph()},
            rental_property_address={_ph()}, annual_rent={_ph()}, children_count={_ph()},
            metadata_json={_ph()}, status={_ph()}, updated_on={_ph()}
            WHERE id={_ph()}""",
            (
                payload["section_code"], payload.get("section_group", ""), payload["item_name"],
                int(payload.get("declared_amount") or 0),
                payload.get("remarks", ""), payload.get("expected_proof", ""),
                payload.get("claimant_for", ""), payload.get("relation_to_employee", ""),
                payload.get("disease_name", ""), payload.get("landlord_name", ""),
                payload.get("landlord_pan", ""), payload.get("landlord_relation", ""),
                payload.get("rental_property_address", ""),
                float(payload.get("annual_rent") or 0),
                int(payload.get("children_count") or 0),
                json.dumps(payload.get("metadata", {})),
                next_status, _now(), item_id,
            ),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(employee_id, "UPDATE_DECLARATION_ITEM", "declaration_item", str(item_id), next_status)


def delete_declaration_item(item_id: int, employee_id: str) -> None:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT status FROM compliance_declaration_items "
            f"WHERE id={_ph()} AND employee_id={_ph()}",
            (item_id, employee_id),
        )
        row = _row_to_dict(cur)
        if not row:
            raise ValueError("Item not found.")
        if row.get("status") not in ("DRAFT", "RESUBMISSION_REQUIRED"):
            raise ValueError("Only draft items can be deleted.")
        cur.execute(
            f"DELETE FROM compliance_proof_uploads WHERE item_id={_ph()}",
            (item_id,),
        )
        cur.execute(
            f"DELETE FROM compliance_declaration_items WHERE id={_ph()}",
            (item_id,),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(employee_id, "DELETE_DECLARATION_ITEM", "declaration_item", str(item_id), "")


def list_declaration_items(employee_id: str) -> List[Dict[str, Any]]:
    ensure_schema()
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""SELECT di.*,
                (SELECT COUNT(*) FROM compliance_proof_uploads pu WHERE pu.item_id = di.id) AS proof_count
            FROM compliance_declaration_items di
            WHERE di.employee_id={_ph()} AND di.financial_year={_ph()}
            ORDER BY di.id DESC""",
            (employee_id, CURRENT_FY),
        )
        rows = _rows_to_dicts(cur)
    finally:
        cur.close()
        conn.close()

    for row in rows:
        row["section_label"] = _section_display(row.get("section_code", ""))
        try:
            row["metadata"] = json.loads(row.get("metadata_json") or "{}")
        except Exception:
            row["metadata"] = {}
        meta = row.get("metadata") or {}
        if row.get("section_code") == "24(b)":
            row["lender_name"] = meta.get("lender_name", "")
            row["lender_pan"] = meta.get("lender_pan", "")
            row["lender_address"] = meta.get("lender_address", "")
            row["property_occupancy"] = meta.get("property_occupancy", "")
        if row.get("section_code") == "CHILD_EDU":
            row["school_name"] = meta.get("school_name", "")
    return rows


def submit_declaration(employee_id: str, verification_name: str, parent_name: str,
                       declaration_confirmed: bool = False) -> None:
    header = get_or_create_header(employee_id)
    items = list_declaration_items(employee_id)
    if header.get("tax_regime") != "Old Regime":
        raise ValueError("Form 12BB / 124 declaration is required only for Old Regime employees.")
    if _declaration_locked(header):
        raise ValueError("Declaration is already submitted and locked.")
    if not items:
        raise ValueError("Add at least one declaration item before submitting.")
    if not (verification_name or "").strip():
        raise ValueError("Employee name is required for certification.")
    if not (parent_name or "").strip():
        raise ValueError("Parent name is required for certification.")
    if not declaration_confirmed:
        raise ValueError("Please accept the certification before submitting and locking the declaration.")

    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""UPDATE compliance_declaration_items
                SET status = CASE
                    WHEN status IN ('DRAFT','RESUBMITTED','RESUBMISSION_REQUIRED','REJECTED') THEN 'SUBMITTED'
                    ELSE status END,
                    updated_on={_ph()}
                WHERE employee_id={_ph()} AND financial_year={_ph()}""",
            (_now(), employee_id, CURRENT_FY),
        )
        cur.execute(
            f"UPDATE compliance_declaration_header "
            f"SET workflow_stage='DECLARATION_LOCKED', status='DECLARATION_LOCKED', "
            f"declaration_verified=1, declaration_verification_name={_ph()}, "
            f"declaration_parent_name={_ph()}, submitted_on={_ph()}, locked_on={_ph()}, updated_on={_ph()} "
            f"WHERE id={_ph()}",
            (verification_name.strip(), parent_name.strip(), _now(), _now(), _now(), header["id"]),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(
        employee_id,
        "SUBMIT_DECLARATION",
        "header",
        str(header["id"]),
        f"items={len(items)}; verified_by={verification_name.strip()}; parent={parent_name.strip()}"
    )


# =====================================================
# PROOF UPLOADS (BYTEA in DB — no S3 dependency)
# =====================================================

def save_proof(item_id: int, employee_id: str, actual_amount: float, file_obj) -> None:
    if file_obj is None:
        raise ValueError("No file provided.")
    file_bytes = file_obj.getbuffer().tobytes() if hasattr(file_obj.getbuffer(), "tobytes") else bytes(file_obj.getbuffer())
    size = len(file_bytes)
    if size > MAX_PROOF_SIZE_BYTES:
        raise ValueError(f"File too large ({size//1024} KB). Max allowed is {MAX_PROOF_SIZE_BYTES//1024} KB.")
    fname = getattr(file_obj, "name", "proof")
    ext = "." + fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in ALLOWED_PROOF_EXT:
        raise ValueError(f"File type '{ext}' not allowed. Use PDF / JPG / PNG.")
    ftype = getattr(file_obj, "type", "") or ""
    if ftype and ftype not in ALLOWED_PROOF_MIME:
        raise ValueError(f"Unsupported MIME type: {ftype}")

    conn = _get_conn()
    cur = conn.cursor()
    try:
        # Verify item belongs to employee.
        cur.execute(
            f"SELECT status FROM compliance_declaration_items "
            f"WHERE id={_ph()} AND employee_id={_ph()}",
            (item_id, employee_id),
        )
        row = _row_to_dict(cur)
        if not row:
            raise ValueError("Declaration item not found.")

        # Insert proof blob.
        if _is_pg():
            import psycopg2
            cur.execute(
                f"""INSERT INTO compliance_proof_uploads
                (item_id, employee_id, file_name, file_size, file_type, file_bytes, uploaded_on)
                VALUES ({_ph()},{_ph()},{_ph()},{_ph()},{_ph()},{_ph()},{_ph()})""",
                (item_id, employee_id, fname, size, ftype, psycopg2.Binary(file_bytes), _now()),
            )
        else:
            cur.execute(
                f"""INSERT INTO compliance_proof_uploads
                (item_id, employee_id, file_name, file_size, file_type, file_bytes, uploaded_on)
                VALUES (?,?,?,?,?,?,?)""",
                (item_id, employee_id, fname, size, ftype, file_bytes, _now()),
            )

        # Bump item status + actual_amount.
        next_status = "RESUBMITTED" if row.get("status") in ("RESUBMISSION_REQUIRED", "REJECTED") else "PROOF_SUBMITTED"
        cur.execute(
            f"UPDATE compliance_declaration_items "
            f"SET actual_amount={_ph()}, status={_ph()}, updated_on={_ph()} WHERE id={_ph()}",
            (int(actual_amount or 0), next_status, _now(), item_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(employee_id, "UPLOAD_PROOF", "declaration_item", str(item_id), f"{fname} ({size} bytes)")


def list_proofs_for_item(item_id: int) -> List[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT id, item_id, file_name, file_size, file_type, uploaded_on, review_status "
            f"FROM compliance_proof_uploads WHERE item_id={_ph()} ORDER BY id DESC",
            (item_id,),
        )
        return _rows_to_dicts(cur)
    finally:
        cur.close()
        conn.close()


def get_proof_bytes(proof_id: int) -> Optional[Tuple[bytes, str, str]]:
    """Return (bytes, filename, mime) for download. Admin only."""
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT file_bytes, file_name, file_type FROM compliance_proof_uploads WHERE id={_ph()}",
            (proof_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        blob = bytes(row[0]) if row[0] is not None else b""
        return blob, row[1], row[2] or "application/octet-stream"
    finally:
        cur.close()
        conn.close()


# =====================================================
# REGIME CHANGE REQUESTS
# =====================================================

def create_regime_change_request(employee_id: str, requested_regime: str, reason: str) -> None:
    header = get_or_create_header(employee_id)
    if header.get("regime_change_used", 0) and int(header.get("regime_change_used", 0)) >= 1:
        raise ValueError("One-time regime change already used for this FY.")
    if not header.get("tax_regime"):
        raise ValueError("Submit initial regime first.")
    if not header.get("is_locked"):
        raise ValueError("Submit and lock your regime first before requesting a change.")
    if header["tax_regime"] == requested_regime:
        raise ValueError("Requested regime is same as current.")

    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""SELECT id FROM compliance_regime_change_requests
                WHERE employee_id={_ph()} AND financial_year={_ph()} AND status='PENDING'""",
            (employee_id, CURRENT_FY),
        )
        if cur.fetchone():
            raise ValueError("A pending regime change request already exists.")

        cur.execute(
            f"""INSERT INTO compliance_regime_change_requests
            (header_id, employee_id, financial_year, old_regime, requested_regime,
             request_reason, requested_on)
            VALUES ({','.join([_ph()] * 7)})""",
            (header["id"], employee_id, CURRENT_FY,
             header["tax_regime"], requested_regime, reason, _now()),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(employee_id, "CREATE_REGIME_CHANGE", "header", str(header["id"]), requested_regime)


def list_regime_change_requests(only_pending: bool = False) -> List[Dict[str, Any]]:
    ensure_schema()
    conn = _get_conn()
    cur = conn.cursor()
    try:
        sql = f"SELECT * FROM compliance_regime_change_requests WHERE financial_year={_ph()}"
        params: tuple = (CURRENT_FY,)
        if only_pending:
            sql += " AND status='PENDING'"
        sql += " ORDER BY requested_on DESC"
        cur.execute(sql, params)
        return _rows_to_dicts(cur)
    finally:
        cur.close()
        conn.close()


def decide_regime_change_request(request_id: int, decision: str,
                                  reviewer_id: str, reviewer_name: str,
                                  remarks: str = "") -> None:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT * FROM compliance_regime_change_requests WHERE id={_ph()}",
            (request_id,),
        )
        req = _row_to_dict(cur)
        if not req:
            raise ValueError("Request not found.")

        cur.execute(
            f"""UPDATE compliance_regime_change_requests
            SET status={_ph()}, approver_name={_ph()}, approver_id={_ph()},
                decided_on={_ph()}, reviewer_remarks={_ph()} WHERE id={_ph()}""",
            (decision, reviewer_name, reviewer_id, _now(), remarks, request_id),
        )
        if decision == "APPROVED":
            next_stage = "COMPLETE" if req["requested_regime"] == "New Regime" else "DECLARATION"
            cur.execute(
                f"""UPDATE compliance_declaration_header
                SET tax_regime={_ph()}, is_locked=0,
                    regime_change_used=regime_change_used+1,
                    workflow_stage={_ph()}, status='REOPENED', updated_on={_ph()}
                WHERE id={_ph()}""",
                (req["requested_regime"], next_stage, _now(), req["header_id"]),
            )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(reviewer_id, "DECIDE_REGIME_CHANGE", "regime_change_request", str(request_id), decision)


# =====================================================
# ADMIN QUERIES
# =====================================================

def list_review_items() -> List[Dict[str, Any]]:
    ensure_schema()
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"""SELECT di.*,
                (SELECT COUNT(*) FROM compliance_proof_uploads pu WHERE pu.item_id = di.id) AS proof_count
            FROM compliance_declaration_items di
            WHERE di.financial_year={_ph()}
              AND di.status IN ('SUBMITTED','PROOF_SUBMITTED','RESUBMITTED','UNDER REVIEW')
            ORDER BY di.updated_on DESC, di.id DESC""",
            (CURRENT_FY,),
        )
        return _rows_to_dicts(cur)
    finally:
        cur.close()
        conn.close()


def review_declaration_item(item_id: int, approved_amount: float, status: str,
                             remarks: str, reviewer_id: str) -> None:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"UPDATE compliance_declaration_items "
            f"SET approved_amount={_ph()}, status={_ph()}, reviewer_remarks={_ph()}, updated_on={_ph()} "
            f"WHERE id={_ph()}",
            (int(approved_amount or 0), status, remarks, _now(), item_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(reviewer_id, "REVIEW_DECLARATION", "declaration_item", str(item_id),
           f"{status}:{approved_amount}")


def reopen_employee_declaration(item_id: int, reviewer_id: str, remarks: str = "") -> None:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT header_id, employee_id FROM compliance_declaration_items WHERE id={_ph()}",
            (item_id,),
        )
        row = _row_to_dict(cur)
        if not row:
            raise ValueError("Declaration item not found.")
        header_id = row["header_id"]
        employee_id = row["employee_id"]
        cur.execute(
            f"UPDATE compliance_declaration_header SET is_locked=0, status='DECLARATION_REOPENED', "
            f"workflow_stage='DECLARATION', updated_on={_ph()} WHERE id={_ph()}",
            (_now(), header_id),
        )
        cur.execute(
            f"UPDATE compliance_declaration_items SET status='RESUBMISSION_REQUIRED', updated_on={_ph()} "
            f"WHERE header_id={_ph()} AND employee_id={_ph()} AND financial_year={_ph()}",
            (_now(), header_id, employee_id, CURRENT_FY),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(reviewer_id, "REOPEN_DECLARATION", "header", str(header_id), remarks or employee_id)


def compliance_dashboard() -> Dict[str, Any]:
    ensure_schema()
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT COUNT(*) FROM compliance_declaration_header WHERE financial_year={_ph()}",
            (CURRENT_FY,),
        )
        total_employees = cur.fetchone()[0]
        cur.execute(
            f"SELECT COUNT(*) FROM compliance_declaration_header "
            f"WHERE financial_year={_ph()} AND tax_regime IS NOT NULL",
            (CURRENT_FY,),
        )
        regime_selected = cur.fetchone()[0]
        cur.execute(
            f"SELECT COUNT(*) FROM compliance_declaration_items WHERE financial_year={_ph()}",
            (CURRENT_FY,),
        )
        total_items = cur.fetchone()[0]
        cur.execute(
            f"""SELECT COUNT(*) FROM compliance_declaration_items
                WHERE financial_year={_ph()}
                  AND status IN ('SUBMITTED','PROOF_SUBMITTED','RESUBMITTED','UNDER REVIEW')""",
            (CURRENT_FY,),
        )
        pending = cur.fetchone()[0]
        cur.execute(
            f"SELECT COALESCE(SUM(declared_amount),0), COALESCE(SUM(approved_amount),0) "
            f"FROM compliance_declaration_items WHERE financial_year={_ph()}",
            (CURRENT_FY,),
        )
        declared, approved = cur.fetchone()
        return {
            "total_employees": int(total_employees or 0),
            "regime_selected": int(regime_selected or 0),
            "total_items": int(total_items or 0),
            "pending_review": int(pending or 0),
            "total_declared": float(declared or 0),
            "total_approved": float(approved or 0),
        }
    finally:
        cur.close()
        conn.close()


def export_compliance_excel() -> bytes:
    """Build an Excel workbook for tax-team export."""
    ensure_schema()
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT * FROM compliance_declaration_header WHERE financial_year={_ph()}",
                    (CURRENT_FY,))
        headers = _rows_to_dicts(cur)
        cur.execute(f"SELECT * FROM compliance_declaration_items WHERE financial_year={_ph()}",
                    (CURRENT_FY,))
        items = _rows_to_dicts(cur)
        cur.execute(f"SELECT * FROM compliance_regime_change_requests WHERE financial_year={_ph()}",
                    (CURRENT_FY,))
        rcrs = _rows_to_dicts(cur)
        # Allowances — exclude the binary blob so the Excel stays small.
        cur.execute(
            f"""SELECT id, employee_id, financial_year, claim_month, allowance_type,
                   amount, approved_amount, expense_details, vendor_name, bill_reference,
                   status, reviewer_remarks, file_name, file_size, file_type,
                   resubmission_count, submitted_on, reviewed_on, updated_on
            FROM compliance_allowance_claims WHERE financial_year={_ph()}""",
            (CURRENT_FY,),
        )
        allowances = _rows_to_dicts(cur)
        cur.execute("SELECT * FROM compliance_audit_logs ORDER BY id DESC LIMIT 500")
        audit = _rows_to_dicts(cur)
    finally:
        cur.close()
        conn.close()

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        _excel_safe_df(pd.DataFrame(headers)).to_excel(writer, sheet_name="Headers", index=False)
        _excel_safe_df(pd.DataFrame(items)).to_excel(writer, sheet_name="Declarations", index=False)
        _excel_safe_df(pd.DataFrame(allowances)).to_excel(writer, sheet_name="Allowances", index=False)
        _excel_safe_df(pd.DataFrame(rcrs)).to_excel(writer, sheet_name="Regime Changes", index=False)
        _excel_safe_df(pd.DataFrame(audit)).to_excel(writer, sheet_name="Audit", index=False)
    buf.seek(0)
    return buf.getvalue()


# =====================================================
# AI RISK ENGINE (rule-based)
# =====================================================

def evaluate_declaration(item: Dict[str, Any]) -> Dict[str, Any]:
    reasons: List[str] = []
    risk = "LOW"
    recommended_status = "APPROVED"

    section = item.get("section_code", "")
    declared = float(item.get("declared_amount") or 0)
    actual = float(item.get("actual_amount") or 0)
    proof_count = int(item.get("proof_count") or 0)
    approved_ceiling = declared

    section_cfg = SECTION_LOOKUP.get(section)
    cap = section_cfg["amount_cap"] if section_cfg else None
    if cap and declared > cap:
        risk = "MEDIUM"
        approved_ceiling = min(approved_ceiling, cap)
        reasons.append(f"Declared exceeds {section} statutory cap of ₹{cap:,.0f}.")

    if actual and actual > declared:
        risk = "HIGH"
        recommended_status = "UNDER REVIEW"
        reasons.append("Actual proof amount exceeds earlier declaration.")

    if item.get("status") in ("PROOF_SUBMITTED", "SUBMITTED", "RESUBMITTED") \
       and proof_count == 0 and section not in ("HRA", "CHILD_EDU"):
        risk = "HIGH"
        recommended_status = "RESUBMISSION_REQUIRED"
        reasons.append("Submitted declaration has no proof uploaded.")

    if section == "HRA":
        annual_rent = float(item.get("annual_rent") or declared or 0)
        landlord_pan = (item.get("landlord_pan") or "").strip().upper()
        landlord_rel = item.get("landlord_relation") or ""
        if annual_rent > 100000 and not landlord_pan:
            risk = "HIGH"
            recommended_status = "RESUBMISSION_REQUIRED"
            reasons.append("Annual rent > ₹1L but landlord PAN missing.")
        if landlord_pan and not PAN_REGEX.match(landlord_pan):
            risk = "HIGH"
            recommended_status = "RESUBMISSION_REQUIRED"
            reasons.append("Landlord PAN format invalid.")
        if landlord_rel in ("Father", "Mother", "Spouse", "Brother", "Sister", "Other Relative"):
            risk = "MEDIUM" if risk == "LOW" else risk
            if recommended_status == "APPROVED":
                recommended_status = "UNDER REVIEW"
            reasons.append("Relative-landlord HRA — verify genuine tenancy and payment trail.")

    if section == "80DDB":
        if not item.get("disease_name"):
            risk = "HIGH"
            recommended_status = "RESUBMISSION_REQUIRED"
            reasons.append("Disease name mandatory for 80DDB.")
        if proof_count == 0:
            risk = "HIGH"
            recommended_status = "RESUBMISSION_REQUIRED"
            reasons.append("80DDB requires specialist certificate.")

    if section == "CHILD_EDU" and int(item.get("children_count") or 0) <= 0:
        risk = "MEDIUM" if risk == "LOW" else risk
        if recommended_status == "APPROVED":
            recommended_status = "RESUBMISSION_REQUIRED"
        reasons.append("Child Education Allowance needs eligible children count.")

    if not reasons:
        reasons.append("Item looks structurally complete — no rule breach detected.")

    return {
        "risk": risk,
        "recommended_status": recommended_status,
        "approved_ceiling": approved_ceiling,
        "reasons": reasons,
    }


# =====================================================
# VALIDATION
# =====================================================

def validate_declaration_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    section = payload.get("section_code", "")
    if section not in SECTION_LOOKUP:
        errors.append("Invalid section code.")

    try:
        declared = float(payload.get("declared_amount") or 0)
        if section != "CHILD_EDU" and declared <= 0:
            errors.append("Declared amount must be greater than zero.")
        if section != "CHILD_EDU" and not float(declared).is_integer():
            errors.append("Declared amount should be a whole number.")
    except Exception:
        errors.append("Declared amount must be numeric.")
        declared = 0

    cfg = SECTION_LOOKUP.get(section)
    if cfg and cfg.get("amount_cap") and declared > float(cfg["amount_cap"]):
        errors.append(f"Declared amount exceeds the limit of ₹{int(cfg['amount_cap']):,}.")

    meta = payload.get("metadata") or {}

    if section == "HRA":
        if not (payload.get("landlord_name") or "").strip():
            errors.append("Landlord name is mandatory for HRA.")
        if not (payload.get("landlord_relation") or "").strip():
            errors.append("Landlord relation is mandatory for HRA.")
        if not (payload.get("rental_property_address") or "").strip():
            errors.append("Rental property address is mandatory for HRA.")
        try:
            annual_rent = float(payload.get("annual_rent") or 0)
        except Exception:
            annual_rent = 0
        if annual_rent <= 0:
            errors.append("Annual rent paid must be greater than zero.")
        pan = (payload.get("landlord_pan") or "").strip().upper()
        if annual_rent > 100000 and not pan:
            errors.append("Landlord PAN required when annual rent > ₹1,00,000.")
        if pan and not PAN_REGEX.match(pan):
            errors.append("Landlord PAN format is invalid (e.g., AAAPL1234C).")

    if section == "80E":
        claimant = payload.get("claimant_for") or ""
        if claimant not in CLAIMANT_OPTIONS_80E:
            errors.append("Section 129 (Earlier 80E) can be claimed only for Self, Spouse, or Children.")

    if section == "80DD" and not payload.get("relation_to_employee"):
        errors.append("Relation to employee is mandatory for Section 127 (Earlier 80DD).")

    if section == "80DDB":
        if not payload.get("relation_to_employee"):
            errors.append("Relation to employee is mandatory for Section 128 (Earlier 80DDB).")
        if not (payload.get("disease_name") or "").strip():
            errors.append("Disease name is mandatory for Section 128 (Earlier 80DDB).")

    if section == "24(b)":
        lender_name = (meta.get("lender_name") or "").strip()
        lender_pan = (meta.get("lender_pan") or "").strip().upper()
        lender_address = (meta.get("lender_address") or "").strip()
        property_occupancy = (meta.get("property_occupancy") or "").strip()
        if not lender_name:
            errors.append("Name of lender is mandatory for Interest on home loan.")
        if not lender_pan:
            errors.append("PAN of lender is mandatory for Interest on home loan.")
        elif not PAN_REGEX.match(lender_pan):
            errors.append("Lender PAN format is invalid (e.g., AAAPL1234C).")
        if not lender_address:
            errors.append("Address of lender is mandatory for Interest on home loan.")
        if property_occupancy not in PROPERTY_OCCUPANCY_OPTIONS:
            errors.append("Select whether the property is Self Occupied or Rented.")

    if section == "CHILD_EDU":
        if int(payload.get("children_count") or 0) <= 0:
            errors.append("Eligible children count must be at least 1 for Children Declaration.")
        if not (meta.get("school_name") or "").strip():
            errors.append("School / institution name is mandatory for Children Declaration.")

    if section == "OTHER_VIA" and not (meta.get("section_reference") or "").strip():
        errors.append("Section reference is mandatory for other eligible deductions.")

    return errors


# =====================================================
# UI PANELS — EMPLOYEE
# =====================================================

def _money(value) -> str:
    try:
        return f"₹ {float(value or 0):,.0f}"
    except Exception:
        return "₹ 0"


def _required_label(label: str) -> str:
    return f"{label} *"


def _safe_key(text_value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text_value).strip("_") or "field"


def _section_display(section_code: str) -> str:
    row = SECTION_LOOKUP.get(section_code)
    return row["display_name"] if row else section_code


def _section_options() -> List[str]:
    return [row["display_name"] for row in SECTION_MASTER]


def _parse_section(selected: str) -> str:
    for row in SECTION_MASTER:
        if row["display_name"] == selected:
            return row["section_code"]
    for row in SECTION_MASTER:
        fallback = f"{row['section_code']} | {row['display_name']}"
        if selected == fallback:
            return row["section_code"]
    return "80C"


def _state_val(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)


def _render_remarks_box(label: str, text_value: str) -> None:
    if not str(text_value or '').strip():
        return
    safe_label = html.escape(str(label))
    safe_text = html.escape(str(text_value))
    st.markdown(
        f"<div style='background:#fff7d6;border-left:4px solid #f2c94c;padding:0.7rem 0.9rem;border-radius:0.6rem;margin:0.35rem 0 0.85rem 0;'>"
        f"<div style='font-size:0.82rem;font-weight:700;color:#7a5a00;margin-bottom:0.2rem;'>{safe_label}</div>"
        f"<div style='color:#333333;white-space:pre-wrap;'>{safe_text}</div></div>",
        unsafe_allow_html=True,
    )


def _style_remarks_df(df: pd.DataFrame):
    remark_cols = [c for c in ('remarks', 'reviewer_remarks') if c in df.columns]
    if not remark_cols:
        return df
    styler = df.style
    for col in remark_cols:
        styler = styler.applymap(
            lambda v: 'background-color:#fff7d6;color:#5f4b00;' if pd.notna(v) and str(v).strip() else '',
            subset=[col],
        )
    return styler


def _excel_safe_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        if value.tzinfo is not None:
            value = value.tz_convert(None)
        return value.to_pydatetime()
    if isinstance(value, dt.datetime):
        if value.tzinfo is not None:
            value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return value
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, (dict, list, tuple, set)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return value


def _excel_safe_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    safe_df = df.copy()
    for col in safe_df.columns:
        safe_df[col] = safe_df[col].map(_excel_safe_value)
    return safe_df


def _form_step_state(prefix: str, section_code: str) -> Dict[str, int]:
    nav_key = f"nav_step_{prefix}"
    sec_key = f"nav_section_{prefix}"
    last_section = st.session_state.get(sec_key)
    if last_section != section_code:
        st.session_state[sec_key] = section_code
        if last_section is not None:
            st.session_state[nav_key] = 1
    max_step = 3 if section_code in {"HRA", "24(b)", "80D", "80DD", "80DDB", "80E", "CHILD_EDU", "OTHER_VIA"} else 2
    step = int(st.session_state.get(nav_key, 1) or 1)
    if step < 1 or step > max_step:
        step = 1
        st.session_state[nav_key] = step
    return {"step": step, "max_step": max_step}


def _set_form_step(prefix: str, step: int) -> None:
    st.session_state[f"nav_step_{prefix}"] = max(1, int(step))


def _workflow_panels() -> List[tuple[str, str]]:
    return [
        ("tax_regime", "Tax Regime"),
        ("investment", "Form 12BB / 124 Declaration"),
        ("my_declaration", "My Declaration"),
        ("monthly_allowances", "Monthly Allowances"),
        ("proof_submission", "Proof Submission"),
    ]


_COMPLIANCE_PANEL_KEY_BY_TARGET = {
    "tax_regime": "Compliance Tax Regime",
    "investment": "Compliance Investment Declaration",
    "my_declaration": "Compliance My Declaration",
    "monthly_allowances": "Compliance Monthly Allowances",
    "proof_submission": "Compliance Proof Submission",
}


def _navigate_to_target(target_key: str) -> None:
    """Route to another Strides panel using the host app's own selector."""
    panel_name = _COMPLIANCE_PANEL_KEY_BY_TARGET.get(target_key)
    if not panel_name:
        return
    st.session_state["selected_panel"] = panel_name
    # Some hosts gate panels behind "start_completed"; ensure the gate is open.
    if "start_completed" in st.session_state:
        st.session_state["start_completed"] = True
    st.rerun()


def _workflow_nav_buttons(current_key: str) -> None:
    panels = _workflow_panels()
    keys = [key for key, _ in panels]
    labels = {key: label for key, label in panels}
    if current_key not in keys:
        return
    idx = keys.index(current_key)
    prev_key = keys[idx - 1] if idx > 0 else None
    next_key = keys[idx + 1] if idx < len(keys) - 1 else None
    c1, c2, c3 = st.columns([1, 2.6, 1])
    if c1.button("◀ Previous step", key=f"page_back_{current_key}", use_container_width=True, disabled=prev_key is None):
        _navigate_to_target(prev_key)
    c2.markdown(
        f"<div style='background:#eef6ff;border:1px solid #c9def7;padding:0.6rem 0.8rem;border-radius:0.75rem;text-align:center;font-weight:600;color:#194b7a;'>◀ Previous step &nbsp; • &nbsp; Current step: {labels[current_key]} &nbsp; • &nbsp; Next step ▶</div>",
        unsafe_allow_html=True,
    )
    if c3.button("Next step ▶", key=f"page_next_{current_key}", use_container_width=True, disabled=next_key is None):
        _navigate_to_target(next_key)


def _delegate_employee_panel(current_key: str, employee_id: str) -> bool:
    """Compatibility shim.

    Earlier versions used an internal target panel state to switch the rendered
    panel from inside the module. That hijacked the host app's own sidebar
    selection and caused every compliance button to re-render the first panel.
    The router is now handled by the host app via ``selected_panel``, so this
    function intentionally does nothing and always returns False so that the
    caller renders its own panel content.
    """
    # Clear any legacy target state so it cannot interfere with future renders.
    if "compliance_target_panel" in st.session_state:
        del st.session_state["compliance_target_panel"]
    return False


def _render_item_form(prefix: str, defaults: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], Dict[str, int]]:
    defaults = dict(defaults or {})
    if defaults.get("metadata_json") and not defaults.get("metadata"):
        try:
            defaults["metadata"] = json.loads(defaults.get("metadata_json") or "{}")
        except Exception:
            defaults["metadata"] = {}
    meta_defaults = defaults.get("metadata") or {}

    options = _section_options()
    default_code = defaults.get("section_code", "80C")
    default_label = _section_display(default_code)
    default_idx = options.index(default_label) if default_label in options else 0
    selected = st.selectbox(_required_label("Section / Claim type"), options, index=default_idx, key=f"sec_{prefix}")
    section_code = _parse_section(selected)
    cfg = SECTION_LOOKUP[section_code]
    st.caption(f"Current section: **{cfg['display_name']}**")

    item_key = f"item_{prefix}_{_safe_key(section_code)}"
    amt_key = f"amt_{prefix}"
    proof_key = f"proof_{prefix}"
    remarks_key = f"rem_{prefix}"
    claimant_key = f"claim_{prefix}"
    relation_key = f"rel_{prefix}"
    disease_key = f"dis_{prefix}"
    landlord_name_key = f"lname_{prefix}"
    landlord_relation_key = f"lrel_{prefix}"
    landlord_pan_key = f"lpan_{prefix}"
    landlord_address_key = f"laddr_{prefix}"
    monthly_rent_key = f"mrent_{prefix}"
    kids_key = f"kids_{prefix}"
    school_key = f"school_{prefix}"
    other_section_key = f"other_sec_{prefix}"
    lender_name_key = f"lender_name_{prefix}"
    lender_pan_key = f"lender_pan_{prefix}"
    lender_address_key = f"lender_addr_{prefix}"
    property_occ_key = f"prop_occ_{prefix}"

    items = cfg["items"]
    default_item = defaults.get("item_name", items[0]) if defaults.get("item_name") in items else items[0]

    c1, c2 = st.columns(2)
    c1.selectbox(_required_label("Item"), items, index=items.index(default_item), key=item_key)
    if section_code == "CHILD_EDU":
        c2.info("No amount entry required for Children Declaration.")
        st.session_state[amt_key] = 0
        st.info("Children declaration reminder: if you are claiming Children Education Allowance, please fill the eligible children count and school / institution name below.")
    else:
        c2.number_input(
            _required_label("Declared amount (₹)"), min_value=0, step=1,
            value=int(defaults.get("declared_amount") or 0), key=amt_key,
        )

    # Claim-specific inputs
    if section_code in ("80DD", "80DDB", "80E"):
        opts = [""] + (CLAIMANT_OPTIONS_80E if section_code == "80E" else CLAIMANT_OPTIONS)
        cur = defaults.get("claimant_for", "")
        st.selectbox(
            _required_label("Claiming for"), opts,
            index=opts.index(cur) if cur in opts else 0, key=claimant_key,
        )

    if section_code in ("80DD", "80DDB"):
        opts = [""] + RELATION_OPTIONS
        cur = defaults.get("relation_to_employee", "")
        st.selectbox(
            _required_label("Relation to employee"), opts,
            index=opts.index(cur) if cur in opts else 0, key=relation_key,
        )

    if section_code == "80DDB":
        st.text_input(
            _required_label("Disease name"), value=defaults.get("disease_name", ""), key=disease_key,
        )

    if section_code == "HRA":
        c1, c2 = st.columns(2)
        c1.text_input(_required_label("Landlord name"), value=defaults.get("landlord_name", ""), key=landlord_name_key)
        cur_rel = defaults.get("landlord_relation", LANDLORD_RELATIONS[0])
        c2.selectbox(
            _required_label("Landlord relation"), LANDLORD_RELATIONS,
            index=LANDLORD_RELATIONS.index(cur_rel) if cur_rel in LANDLORD_RELATIONS else 0,
            key=landlord_relation_key,
        )
        st.text_input(
            "Landlord PAN (mandatory if annual rent exceeds ₹1,00,000)",
            value=(defaults.get("landlord_pan") or "").upper(), key=landlord_pan_key,
        )
        st.text_area(
            _required_label("Rental property address"),
            value=defaults.get("rental_property_address", ""), key=landlord_address_key,
        )
        default_monthly_rent = int(meta_defaults.get("monthly_rent") or ((defaults.get("annual_rent") or 0) / 12 if defaults.get("annual_rent") else 0))
        st.number_input(
            _required_label("Monthly rent (₹)"), min_value=0, step=1,
            value=default_monthly_rent, key=monthly_rent_key,
        )
        monthly_rent = int(_state_val(monthly_rent_key, default_monthly_rent) or 0)
        st.metric("Annual rent paid (auto-calculated)", _money(monthly_rent * 12))

    if section_code == "24(b)":
        c1, c2 = st.columns(2)
        c1.text_input(_required_label("Name of lender"), value=meta_defaults.get("lender_name", ""), key=lender_name_key)
        c2.text_input(_required_label("PAN of lender"), value=(meta_defaults.get("lender_pan", "") or "").upper(), key=lender_pan_key)
        st.text_area(_required_label("Address of lender"), value=meta_defaults.get("lender_address", ""), key=lender_address_key)
        current_occupancy = meta_defaults.get("property_occupancy", PROPERTY_OCCUPANCY_OPTIONS[0])
        st.selectbox(
            _required_label("Property is self occupied or rented"), PROPERTY_OCCUPANCY_OPTIONS,
            index=PROPERTY_OCCUPANCY_OPTIONS.index(current_occupancy) if current_occupancy in PROPERTY_OCCUPANCY_OPTIONS else 0,
            key=property_occ_key,
        )

    if section_code == "CHILD_EDU":
        st.number_input(
            _required_label("Eligible children count"), min_value=0, max_value=4, step=1,
            value=int(defaults.get("children_count") or 0), key=kids_key,
        )
        st.text_input(
            _required_label("School / institution name"), value=meta_defaults.get("school_name", ""), key=school_key,
        )

    if section_code == "OTHER_VIA":
        st.text_input(
            _required_label("Section reference"), value=meta_defaults.get("section_reference", ""), key=other_section_key,
            placeholder="Example: Section 131 / relevant Chapter VIII-A clause",
        )

    st.text_input(
        _required_label("Expected proof"),
        value=defaults.get("expected_proof") or cfg["expected_proof"], key=proof_key,
    )
    if section_code != "24(b)":
        st.text_area("Remarks", value=defaults.get("remarks", ""), key=remarks_key)
    else:
        st.info("Remarks are not required for Interest on home loan in this release.")

    payload: Dict[str, Any] = {
        "section_code": section_code,
        "section_group": cfg["group_name"],
        "item_name": _state_val(item_key, default_item),
        "declared_amount": 0 if section_code == "CHILD_EDU" else int(_state_val(amt_key, defaults.get("declared_amount") or 0) or 0),
        "expected_proof": _state_val(proof_key, defaults.get("expected_proof") or cfg["expected_proof"]),
        "remarks": "" if section_code == "24(b)" else _state_val(remarks_key, defaults.get("remarks", "")),
        "claimant_for": _state_val(claimant_key, defaults.get("claimant_for", "")),
        "relation_to_employee": _state_val(relation_key, defaults.get("relation_to_employee", "")),
        "disease_name": _state_val(disease_key, defaults.get("disease_name", "")),
        "landlord_name": _state_val(landlord_name_key, defaults.get("landlord_name", "")),
        "landlord_pan": str(_state_val(landlord_pan_key, defaults.get("landlord_pan", "")) or "").upper(),
        "landlord_relation": _state_val(landlord_relation_key, defaults.get("landlord_relation", "")),
        "rental_property_address": _state_val(landlord_address_key, defaults.get("rental_property_address", "")),
        "annual_rent": float(defaults.get("annual_rent") or 0),
        "children_count": int(_state_val(kids_key, defaults.get("children_count") or 0) or 0),
        "metadata": {},
    }

    if payload["item_name"] not in items:
        payload["item_name"] = items[0]

    if section_code == "HRA":
        monthly_rent = int(_state_val(monthly_rent_key, meta_defaults.get("monthly_rent") or 0) or 0)
        payload["annual_rent"] = float(monthly_rent * 12)
        payload["metadata"]["monthly_rent"] = monthly_rent
    else:
        payload["annual_rent"] = float(defaults.get("annual_rent") or 0)

    if section_code == "24(b)":
        payload["metadata"].update({
            "lender_name": _state_val(lender_name_key, meta_defaults.get("lender_name", "")),
            "lender_pan": str(_state_val(lender_pan_key, meta_defaults.get("lender_pan", "")) or "").upper(),
            "lender_address": _state_val(lender_address_key, meta_defaults.get("lender_address", "")),
            "property_occupancy": _state_val(property_occ_key, meta_defaults.get("property_occupancy", PROPERTY_OCCUPANCY_OPTIONS[0])),
        })
    if section_code == "CHILD_EDU":
        payload["metadata"]["school_name"] = _state_val(school_key, meta_defaults.get("school_name", ""))
    if section_code == "OTHER_VIA":
        payload["metadata"]["section_reference"] = _state_val(other_section_key, meta_defaults.get("section_reference", ""))

    return payload, {"step": 1, "max_step": 1}


def render_tax_regime_panel(employee_id: str) -> None:
    if _delegate_employee_panel("tax_regime", employee_id):
        return
    ensure_schema()
    header = get_or_create_header(employee_id)
    st.markdown("## 📋 Tax Regime Selection")
    _workflow_nav_buttons("tax_regime")
    st.caption(f"Tax Year: **{CURRENT_FY}** • Employee: **{employee_id}**")

    c1, c2, c3 = st.columns(3)
    c1.metric("Current Regime", header.get("tax_regime") or "Not selected")
    c2.metric("Status", header.get("status") or "DRAFT")
    c3.metric("Locked", "Yes" if header.get("is_locked") else "No")

    with st.container(border=True):
        st.markdown("#### Choose your tax regime for the year")
        current = header.get("tax_regime") or "Old Regime"
        regime = st.radio(
            "Regime", ["Old Regime", "New Regime"],
            index=0 if current == "Old Regime" else 1,
            horizontal=True,
            disabled=bool(header.get("is_locked")),
        )
        st.info(
            "**Old Regime** — claim deductions like 80C, 80D, HRA. Mandatory to submit "
            "declaration + proofs.\n\n"
            "**New Regime** — lower flat rates; only Meal Passes + Employer NPS are "
            "deductible. No declaration needed."
        )

        a, b = st.columns(2)
        if a.button("💾 Save Regime", disabled=bool(header.get("is_locked")), use_container_width=True):
            try:
                save_regime(employee_id, regime)
                st.success("Regime saved.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        if b.button("✅ Submit & Lock", type="primary", disabled=bool(header.get("is_locked")),
                    use_container_width=True):
            try:
                save_regime(employee_id, regime)
                submit_regime(employee_id)
                st.success("Regime submitted and locked.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    if header.get("is_locked"):
        with st.container(border=True):
            st.markdown("#### 🔄 One-time Regime Change Request")
            st.caption("Allowed once per tax year, subject to admin approval.")
            current = header.get("tax_regime") or ""
            other = "New Regime" if current == "Old Regime" else "Old Regime"
            reason = st.text_area("Reason for change", placeholder="Explain why you'd like to switch...")
            already_used = int(header.get("regime_change_used") or 0) >= 1
            if already_used:
                st.warning("⚠️ One-time regime change already used for this tax year.")
            if st.button(f"Request change to {other}", disabled=already_used):
                if not reason.strip():
                    st.error("Please provide a reason.")
                else:
                    try:
                        create_regime_change_request(employee_id, other, reason.strip())
                        st.success("Request submitted to tax team for approval.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))


def render_investment_declaration_panel(employee_id: str) -> None:
    if _delegate_employee_panel("investment", employee_id):
        return
    ensure_schema()
    header = get_or_create_header(employee_id)
    locked = _declaration_locked(header)
    st.markdown(f"## 🧾 {FORM_TITLE}")
    st.caption(FORM_SUBTITLE)
    st.warning(DECLARATION_DISCLAIMER)

    if header.get("tax_regime") != "Old Regime":
        st.warning(
            "Form 12BB / 124 declaration is available only for **Old Regime** employees. "
            "Visit the **Tax Regime** panel first to select Old Regime."
        )
        return

    if locked:
        st.success("Declaration is already submitted and locked. Review the summary in **My Declaration**.")

    st.info(
        "Children declaration highlight: if you want to claim **Children Education Allowance**, "
        "please add the dedicated **Form No. 124 — Children Declaration / Children Education Allowance** item and complete the children count + school details."
    )
    _workflow_nav_buttons("investment")

    add_tab, manage_tab = st.tabs(["➕ Add Item", "✏️ Manage / Resubmit"])

    with add_tab:
        if locked:
            st.info("Add item is disabled because the declaration has already been submitted and locked.")
        else:
            payload, _nav = _render_item_form("add")
            if st.button("Add declaration item", key="decl_add_submit", type="primary", use_container_width=True):
                errors = validate_declaration_payload(payload)
                if errors:
                    for err in errors:
                        st.error(err)
                else:
                    try:
                        add_declaration_item(employee_id, payload)
                        st.success("Declaration item added.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

    items = list_declaration_items(employee_id)

    with manage_tab:
        editable_statuses = {"DRAFT", "RESUBMISSION_REQUIRED", "REJECTED", "RESUBMITTED"}
        editable = [x for x in items if x.get("status") in editable_statuses]
        if locked:
            st.info("Manage / Resubmit is disabled because the declaration has been submitted and locked.")
        elif not editable:
            st.info("No editable items right now.")
        for item in editable:
            with st.expander(f"#{item['id']} • {item.get('section_label') or item['section_code']} • {item['item_name']} • {_money(item.get('declared_amount'))} • {item.get('status')}"):
                payload, _nav = _render_item_form(f"edit_{item['id']}", item)
                c1, c2 = st.columns(2)
                if c1.button("💾 Update item", key=f"edit_save_{item['id']}", type="primary", use_container_width=True):
                    errors = validate_declaration_payload(payload)
                    if errors:
                        for err in errors:
                            st.error(err)
                    else:
                        try:
                            update_declaration_item(item["id"], employee_id, payload)
                            st.success("Declaration item updated.")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
                if c2.button("🗑️ Delete item", key=f"edit_delete_{item['id']}", use_container_width=True):
                    try:
                        delete_declaration_item(item["id"], employee_id)
                        st.success("Declaration item deleted.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
                _render_remarks_box("Employee remarks", item.get("remarks") or "")
                _render_remarks_box("Reviewer remarks", item.get("reviewer_remarks") or "")

    if items:
        st.markdown("---")
        st.subheader("📋 Current Form 12BB / 124 declaration register")
        df = pd.DataFrame(items)
        display_cols = [c for c in [
            "id", "section_label", "section_code", "item_name", "declared_amount",
            "children_count", "remarks", "actual_amount", "approved_amount", "status", "proof_count", "reviewer_remarks",
        ] if c in df.columns]
        display_df = df[display_cols].copy()
        st.dataframe(_style_remarks_df(display_df), use_container_width=True, hide_index=True)
        total = float(pd.to_numeric(df["declared_amount"], errors="coerce").fillna(0).sum())
        c1, c2 = st.columns(2)
        c1.metric("Total declared", _money(total))
        c2.info("Go to **My Declaration** to complete the declaration by employee and use **Preview and Confirm** or **Submit & Lock Declaration**.")
    else:
        st.info("No declaration items yet. Add one above to get started.")


def render_proof_submission_panel(employee_id: str) -> None:
    if _delegate_employee_panel("proof_submission", employee_id):
        return
    st.markdown("## 📎 Proof Submission")
    _workflow_nav_buttons("proof_submission")
    st.button("Proof Submission will open in February 2027", disabled=True, use_container_width=True)
    st.info("This will be open in February 2027 for submission of proofs towards your investment declaration, so please make sure to arrange and upload them.")


def render_my_declaration_panel(employee_id: str) -> None:
    if _delegate_employee_panel("my_declaration", employee_id):
        return
    ensure_schema()
    header = get_or_create_header(employee_id)
    items = list_declaration_items(employee_id)
    locked = _declaration_locked(header)
    st.markdown(f"## 📊 My Declaration — {FORM_TITLE}")
    _workflow_nav_buttons("my_declaration")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Regime", header.get("tax_regime") or "Not selected")
    c2.metric("Items", len(items))
    c3.metric("Stage", header.get("workflow_stage") or "REGIME_SELECTION")
    c4.metric("Locked", "Yes" if locked else "No")

    if not any((item.get("section_code") == "CHILD_EDU") for item in items):
        st.info("Reminder: add the Children Declaration item if you need to claim Children Education Allowance for Tax Year 2026-27.")

    if items:
        df = pd.DataFrame(items)
        display_cols = [c for c in [
            "id", "section_label", "section_code", "item_name", "declared_amount", "children_count",
            "remarks", "actual_amount", "approved_amount", "status", "proof_count", "reviewer_remarks",
        ] if c in df.columns]
        display_df = df[display_cols].copy()
        st.dataframe(_style_remarks_df(display_df), use_container_width=True, hide_index=True)
        csv = df.to_csv(index=False).encode("utf-8")
        export_df = _excel_safe_df(df)
        xbuf = io.BytesIO()
        with pd.ExcelWriter(xbuf, engine="openpyxl") as writer:
            export_df.to_excel(writer, sheet_name="My Declaration", index=False)
        xbuf.seek(0)
        d1, d2, d3 = st.columns(3)
        d1.download_button(
            "⬇️ Download my declaration (CSV)",
            data=csv,
            file_name=f"{employee_id}_declaration_{CURRENT_FY.replace(' ','_')}.csv",
            mime="text/csv",
        )
        d2.download_button(
            "⬇️ Download my declaration (Excel)",
            data=xbuf.getvalue(),
            file_name=f"{employee_id}_declaration_{CURRENT_FY.replace(' ','_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        if d3.button("🔎 Preview and Confirm", use_container_width=True):
            _navigate_to_target("tax_regime")
    else:
        st.info("No declarations yet.")

    if header.get("tax_regime") == "Old Regime":
        with st.container(border=True):
            st.markdown("### ✅ Submit & Lock Declaration")
            st.caption("Declaration by employee")
            verification_name = st.text_input(
                _required_label("Employee name"),
                value=header.get("declaration_verification_name") or st.session_state.get("employee_name", ""),
                key="decl_verification_name",
                disabled=locked,
            )
            parent_name = st.text_input(
                _required_label("Father / Mother name"),
                value=header.get("declaration_parent_name") or "",
                key="decl_parent_name",
                disabled=locked,
            )
            st.markdown(
                f"I, **{verification_name or '..............'}**, son/daughter of **{parent_name or '......................'}**, do hereby certify that the information given in the form is complete and correct."
            )
            declaration_ok = st.checkbox(
                "I confirm the above declaration and want to submit & lock Form 12BB / 124.",
                key="decl_verify_tick",
                disabled=locked,
            )
            if locked:
                st.success(
                    f"Declaration locked on {header.get('locked_on') or '-'} for {header.get('declaration_verification_name') or verification_name}."
                )
            elif st.button("🔒 Submit & Lock Declaration", type="primary", use_container_width=True, disabled=not items):
                try:
                    submit_declaration(employee_id, verification_name, parent_name, declaration_ok)
                    st.success("Declaration submitted and locked successfully.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


# =====================================================
# UI PANELS — ADMIN
# =====================================================

def render_admin_review_queue() -> None:
    ensure_schema()
    st.markdown("## 🛡️ Compliance Review Queue")
    if not _sarika_only():
        st.error("Only Sarika Gupta can approve, reject, or reopen declarations in this release.")
        return
    items = list_review_items()
    if not items:
        st.info("Nothing waiting for review.")
        return
    st.caption(f"📋 {len(items)} declaration item(s) awaiting review")

    for item in items:
        advice = evaluate_declaration(item)
        with st.container(border=True):
            risk_color = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}.get(advice["risk"], "⚪")
            st.markdown(
                f"**{item.get('employee_id')}** — {_section_display(item['section_code'])} / {item['item_name']} "
                f"{risk_color} Risk: {advice['risk']}"
            )
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Declared", _money(item.get("declared_amount")))
            c2.metric("Actual", _money(item.get("actual_amount")))
            c3.metric("Proofs", int(item.get("proof_count") or 0))
            c4.metric("Status", item.get("status"))

            with st.expander("🤖 AI advice & reasons"):
                st.markdown(f"**Recommendation:** `{advice['recommended_status']}`")
                for r in advice["reasons"]:
                    st.markdown(f"- {r}")

            proofs = list_proofs_for_item(item["id"])
            if proofs:
                with st.expander(f"📁 {len(proofs)} proof file(s)"):
                    for p in proofs:
                        size_kb = (p.get("file_size") or 0) // 1024
                        col_a, col_b = st.columns([3, 1])
                        col_a.markdown(f"• {p.get('file_name')} ({size_kb} KB) — {p.get('uploaded_on')}")
                        if col_b.button("⬇️ Download", key=f"dl_{p['id']}"):
                            blob = get_proof_bytes(p["id"])
                            if blob:
                                data, fname, mime = blob
                                st.download_button(
                                    f"Save {fname}",
                                    data=data, file_name=fname, mime=mime,
                                    key=f"dl_btn_{p['id']}",
                                )

            approved = st.number_input(
                "Approved amount (₹)", min_value=0, step=1,
                value=int(item.get("approved_amount") or advice["approved_ceiling"] or 0),
                key=f"appr_{item['id']}",
            )
            actions = ["UNDER REVIEW", "RESUBMISSION_REQUIRED", "APPROVED", "REJECTED", "REOPEN FOR EDIT"]
            default_action = advice["recommended_status"] if advice["recommended_status"] in actions else "UNDER REVIEW"
            action = st.selectbox(
                "Action", actions,
                index=actions.index(default_action), key=f"act_{item['id']}",
            )
            remarks = st.text_area(
                "Reviewer remarks", value="; ".join(advice["reasons"]),
                key=f"rem_{item['id']}",
            )
            if st.button(f"💾 Save review #{item['id']}", key=f"save_r_{item['id']}",
                         type="primary"):
                reviewer_id = st.session_state.get("employee_id", "admin")
                try:
                    if action == "REOPEN FOR EDIT":
                        reopen_employee_declaration(item["id"], reviewer_id, remarks)
                        st.success("Declaration reopened for employee edits.")
                    else:
                        review_declaration_item(item["id"], approved, action, remarks, reviewer_id)
                        st.success("Review saved.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def render_admin_regime_change_panel() -> None:
    ensure_schema()
    if not _sarika_only():
        st.error("Only Sarika Gupta can access this admin workflow in this release.")
        return
    st.markdown("## 🔄 Regime Change Requests")
    requests = list_regime_change_requests()
    if not requests:
        st.info("No regime change requests on file.")
        return

    pending = [r for r in requests if r.get("status") == "PENDING"]
    decided = [r for r in requests if r.get("status") != "PENDING"]

    st.caption(f"📬 {len(pending)} pending • {len(decided)} decided")

    for req in pending:
        with st.container(border=True):
            st.markdown(f"**{req['employee_id']}** • {req['old_regime']} → "
                        f"**{req['requested_regime']}**")
            st.caption(f"Requested on {req.get('requested_on')}")
            st.info(f"**Reason:** {req.get('request_reason')}")
            remarks = st.text_area("Approver remarks (optional)", key=f"rcr_{req['id']}")
            c1, c2 = st.columns(2)
            if c1.button("✅ Approve", key=f"appr_rcr_{req['id']}", type="primary"):
                rid = st.session_state.get("employee_id", "admin")
                rname = st.session_state.get("employee_name", "Admin")
                try:
                    decide_regime_change_request(req["id"], "APPROVED", rid, rname, remarks)
                    st.success("Approved.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
            if c2.button("❌ Reject", key=f"rej_rcr_{req['id']}"):
                rid = st.session_state.get("employee_id", "admin")
                rname = st.session_state.get("employee_name", "Admin")
                try:
                    decide_regime_change_request(req["id"], "REJECTED", rid, rname, remarks)
                    st.success("Rejected.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    if decided:
        st.markdown("### Past decisions")
        df = pd.DataFrame(decided)
        cols = [c for c in ["id", "employee_id", "old_regime", "requested_regime",
                            "status", "approver_name", "decided_on",
                            "reviewer_remarks", "request_reason"] if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)


def render_admin_compliance_reports() -> None:
    ensure_schema()
    if not _sarika_only():
        st.error("Only Sarika Gupta can access this admin workflow in this release.")
        return
    st.markdown("## 📈 Compliance Reports")

    dash = compliance_dashboard()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Employees", dash["total_employees"])
    c2.metric("Regime selected", dash["regime_selected"])
    c3.metric("Declaration items", dash["total_items"])
    c4.metric("Pending review", dash["pending_review"])
    c5, c6 = st.columns(2)
    c5.metric("Total declared", _money(dash["total_declared"]))
    c6.metric("Total approved", _money(dash["total_approved"]))

    # Allowance KPIs
    adash = allowance_dashboard()
    st.markdown("### 🧾 Monthly Allowances")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Total claims", adash["total_claims"])
    a2.metric("Pending review", adash["pending_review"])
    a3.metric("Total claimed", _money(adash["total_claimed"]))
    a4.metric("Total approved", _money(adash["total_approved"]))

    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT * FROM compliance_declaration_items WHERE financial_year={_ph()}",
                    (CURRENT_FY,))
        items = _rows_to_dicts(cur)
    finally:
        cur.close()
        conn.close()

    if items:
        df = pd.DataFrame(items)
        st.subheader("Section-wise summary")
        if "section_code" in df.columns:
            summary = df.groupby("section_code", dropna=False).agg(
                items=("id", "count"),
                declared=("declared_amount", lambda x: pd.to_numeric(x, errors="coerce").sum()),
                approved=("approved_amount", lambda x: pd.to_numeric(x, errors="coerce").sum()),
            ).reset_index()
            st.dataframe(summary, use_container_width=True, hide_index=True)

        st.subheader("All declaration items")
        display_cols = [c for c in [
            "id", "employee_id", "section_code", "item_name", "declared_amount",
            "actual_amount", "approved_amount", "status", "updated_on",
        ] if c in df.columns]
        st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

    # Allowance breakdown
    all_claims = list_allowance_claims()
    if all_claims:
        adf = pd.DataFrame(all_claims)
        st.subheader("Allowance-type breakdown")
        if "allowance_type" in adf.columns:
            summary = adf.groupby("allowance_type", dropna=False).agg(
                claims=("id", "count"),
                claimed=("amount", lambda x: pd.to_numeric(x, errors="coerce").sum()),
                approved=("approved_amount", lambda x: pd.to_numeric(x, errors="coerce").sum()),
            ).reset_index()
            st.dataframe(summary, use_container_width=True, hide_index=True)

        st.subheader("All allowance claims")
        display_cols = [c for c in [
            "id", "employee_id", "claim_month", "allowance_type",
            "amount", "approved_amount", "status", "submitted_on",
        ] if c in adf.columns]
        st.dataframe(adf[display_cols], use_container_width=True, hide_index=True)

    st.markdown("---")
    excel_bytes = export_compliance_excel()
    d1, d2, d3 = st.columns(3)
    d1.download_button(
        "⬇️ Download Tax-Team Excel export",
        data=excel_bytes,
        file_name=f"compliance_export_{CURRENT_FY.replace(' ','_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    if items:
        d2.download_button(
            "⬇️ Declarations CSV",
            data=pd.DataFrame(items).to_csv(index=False).encode("utf-8"),
            file_name=f"declarations_{CURRENT_FY.replace(' ','_')}.csv",
            mime="text/csv",
        )
    if all_claims:
        d3.download_button(
            "⬇️ Allowances CSV",
            data=pd.DataFrame(all_claims).to_csv(index=False).encode("utf-8"),
            file_name=f"allowances_{CURRENT_FY.replace(' ','_')}.csv",
            mime="text/csv",
        )

    # Audit trail
    with st.expander("🕓 Recent audit trail (last 100 entries)"):
        conn = _get_conn()
        cur = conn.cursor()
        try:
            cur.execute("SELECT * FROM compliance_audit_logs ORDER BY id DESC LIMIT 100")
            audit = _rows_to_dicts(cur)
        finally:
            cur.close()
            conn.close()
        if audit:
            adf = pd.DataFrame(audit)
            st.dataframe(adf, use_container_width=True, hide_index=True)
        else:
            st.info("No audit entries yet.")


# =====================================================
# PHASE B — MONTHLY ALLOWANCES
# =====================================================

ALLOWANCE_TYPES: List[str] = [
    "Telephone / Internet Expenses",
    "Electricity Expenses",
    "Professional Membership Fees",
    "Software Subscription Costs",
]


# --- Settings helpers (allowance window + cutoff day) ---

def get_setting(key: str, default: str = "") -> str:
    ensure_schema()
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT setting_value FROM compliance_settings WHERE setting_key={_ph()}",
            (key,),
        )
        row = cur.fetchone()
        return row[0] if row else default
    finally:
        cur.close()
        conn.close()


def set_setting(key: str, value: str, actor_id: str = "admin") -> None:
    ensure_schema()
    conn = _get_conn()
    cur = conn.cursor()
    try:
        # Upsert: try update, then insert if no row.
        cur.execute(
            f"UPDATE compliance_settings SET setting_value={_ph()}, updated_on={_ph()} "
            f"WHERE setting_key={_ph()}",
            (value, _now(), key),
        )
        affected = cur.rowcount or 0
        if affected == 0:
            cur.execute(
                f"INSERT INTO compliance_settings (setting_key, setting_value, updated_on) "
                f"VALUES ({_ph()},{_ph()},{_ph()})",
                (key, value, _now()),
            )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(actor_id, "UPDATE_SETTING", "settings", key, f"{key}={value}")


def allowance_window_open() -> bool:
    """True if today is within the configured submission window."""
    override = get_setting("allowance_window_override", "OPEN")
    if override == "OPEN":
        return True
    if override == "CLOSED":
        return False
    # 'CONTROLLED' — gate by cutoff day
    try:
        cutoff = int(get_setting("allowance_cutoff_day", "25"))
    except ValueError:
        cutoff = 25
    return dt.datetime.now().day <= cutoff


# --- Validation ---

def validate_allowance_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not payload.get("claim_month"):
        errors.append("Claim month is required.")
    if payload.get("allowance_type") not in ALLOWANCE_TYPES:
        errors.append("Allowance type is invalid.")
    try:
        amount = float(payload.get("amount") or 0)
        if amount <= 0:
            errors.append("Amount must be greater than zero.")
        if not float(amount).is_integer():
            errors.append("Amount should be a whole number only.")
    except Exception:
        errors.append("Amount must be numeric.")
    if not (payload.get("expense_details") or "").strip():
        errors.append("Expense details / business justification is required.")
    return errors


# --- CRUD ---

def save_allowance_claim(employee_id: str, payload: Dict[str, Any], file_obj) -> int:
    """Insert a new allowance claim. Returns new claim id."""
    if not allowance_window_open():
        raise ValueError("Allowance submission window is currently closed.")
    if file_obj is None:
        raise ValueError("A supporting document is required.")

    file_bytes = file_obj.getbuffer().tobytes() if hasattr(file_obj.getbuffer(), "tobytes") else bytes(file_obj.getbuffer())
    size = len(file_bytes)
    if size > MAX_PROOF_SIZE_BYTES:
        raise ValueError(f"File too large ({size//1024} KB). Max is {MAX_PROOF_SIZE_BYTES//1024} KB.")
    fname = getattr(file_obj, "name", "claim")
    ext = "." + fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in ALLOWED_PROOF_EXT:
        raise ValueError(f"File type '{ext}' not allowed. Use PDF / JPG / PNG.")
    ftype = getattr(file_obj, "type", "") or ""

    conn = _get_conn()
    cur = conn.cursor()
    try:
        if _is_pg():
            import psycopg2
            cur.execute(
                f"""INSERT INTO compliance_allowance_claims
                (employee_id, financial_year, claim_month, allowance_type, amount,
                 expense_details, vendor_name, bill_reference, status,
                 file_name, file_size, file_type, file_bytes,
                 submitted_on, updated_on)
                VALUES ({','.join([_ph()] * 15)}) RETURNING id""",
                (
                    employee_id, CURRENT_FY, payload["claim_month"],
                    payload["allowance_type"], int(payload["amount"] or 0),
                    payload.get("expense_details", ""),
                    payload.get("vendor_name", ""), payload.get("bill_reference", ""),
                    "SUBMITTED",
                    fname, size, ftype, psycopg2.Binary(file_bytes),
                    _now(), _now(),
                ),
            )
            new_id = cur.fetchone()[0]
        else:
            cur.execute(
                f"""INSERT INTO compliance_allowance_claims
                (employee_id, financial_year, claim_month, allowance_type, amount,
                 expense_details, vendor_name, bill_reference, status,
                 file_name, file_size, file_type, file_bytes,
                 submitted_on, updated_on)
                VALUES ({','.join([_ph()] * 15)})""",
                (
                    employee_id, CURRENT_FY, payload["claim_month"],
                    payload["allowance_type"], int(payload["amount"] or 0),
                    payload.get("expense_details", ""),
                    payload.get("vendor_name", ""), payload.get("bill_reference", ""),
                    "SUBMITTED",
                    fname, size, ftype, file_bytes,
                    _now(), _now(),
                ),
            )
            new_id = cur.lastrowid
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(employee_id, "ADD_ALLOWANCE_CLAIM", "allowance_claim", str(new_id),
           f"{payload['allowance_type']}:{payload['amount']}")
    return new_id


def update_allowance_claim(claim_id: int, employee_id: str,
                            payload: Dict[str, Any], file_obj=None) -> None:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT status FROM compliance_allowance_claims "
            f"WHERE id={_ph()} AND employee_id={_ph()}",
            (claim_id, employee_id),
        )
        row = _row_to_dict(cur)
        if not row:
            raise ValueError("Claim not found.")
        if row.get("status") not in ("RESUBMISSION_REQUIRED", "REJECTED", "DRAFT", "RESUBMITTED", "SUBMITTED"):
            raise ValueError("Only draft / submitted / resubmission / rejected claims can be updated.")

        next_status = "RESUBMITTED" if row.get("status") in ("RESUBMISSION_REQUIRED", "REJECTED", "RESUBMITTED") else "SUBMITTED"

        file_args: tuple = ()
        if file_obj is not None:
            blob = file_obj.getbuffer().tobytes() if hasattr(file_obj.getbuffer(), "tobytes") else bytes(file_obj.getbuffer())
            size = len(blob)
            if size > MAX_PROOF_SIZE_BYTES:
                raise ValueError(f"File too large ({size//1024} KB).")
            fname = getattr(file_obj, "name", "claim")
            ext = "." + fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
            if ext not in ALLOWED_PROOF_EXT:
                raise ValueError(f"File type '{ext}' not allowed.")
            ftype = getattr(file_obj, "type", "") or ""
            if _is_pg():
                import psycopg2
                blob = psycopg2.Binary(blob)

            cur.execute(
                f"""UPDATE compliance_allowance_claims SET
                claim_month={_ph()}, allowance_type={_ph()}, amount={_ph()},
                expense_details={_ph()}, vendor_name={_ph()}, bill_reference={_ph()},
                status={_ph()}, file_name={_ph()}, file_size={_ph()}, file_type={_ph()},
                file_bytes={_ph()}, resubmission_count=resubmission_count+1,
                updated_on={_ph()} WHERE id={_ph()}""",
                (
                    payload["claim_month"], payload["allowance_type"], int(payload["amount"] or 0),
                    payload.get("expense_details", ""), payload.get("vendor_name", ""),
                    payload.get("bill_reference", ""),
                    next_status, fname, size, ftype, blob,
                    _now(), claim_id,
                ),
            )
        else:
            cur.execute(
                f"""UPDATE compliance_allowance_claims SET
                claim_month={_ph()}, allowance_type={_ph()}, amount={_ph()},
                expense_details={_ph()}, vendor_name={_ph()}, bill_reference={_ph()},
                status={_ph()}, resubmission_count=resubmission_count+1,
                updated_on={_ph()} WHERE id={_ph()}""",
                (
                    payload["claim_month"], payload["allowance_type"], int(payload["amount"] or 0),
                    payload.get("expense_details", ""), payload.get("vendor_name", ""),
                    payload.get("bill_reference", ""),
                    next_status, _now(), claim_id,
                ),
            )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(employee_id, "UPDATE_ALLOWANCE_CLAIM", "allowance_claim", str(claim_id), next_status)


def delete_allowance_claim(claim_id: int, employee_id: str) -> None:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT status FROM compliance_allowance_claims "
            f"WHERE id={_ph()} AND employee_id={_ph()}",
            (claim_id, employee_id),
        )
        row = _row_to_dict(cur)
        if not row:
            raise ValueError("Claim not found.")
        if row.get("status") not in ("DRAFT", "RESUBMISSION_REQUIRED", "REJECTED"):
            raise ValueError("Only draft / resubmission / rejected claims can be deleted.")
        cur.execute(
            f"DELETE FROM compliance_allowance_claims WHERE id={_ph()}",
            (claim_id,),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(employee_id, "DELETE_ALLOWANCE_CLAIM", "allowance_claim", str(claim_id), "")


def list_allowance_claims(employee_id: Optional[str] = None,
                           only_pending: bool = False) -> List[Dict[str, Any]]:
    ensure_schema()
    conn = _get_conn()
    cur = conn.cursor()
    try:
        sql = (
            f"SELECT id, employee_id, financial_year, claim_month, allowance_type, "
            f"amount, approved_amount, expense_details, vendor_name, bill_reference, "
            f"status, reviewer_remarks, file_name, file_size, file_type, "
            f"resubmission_count, submitted_on, reviewed_on, updated_on "
            f"FROM compliance_allowance_claims WHERE financial_year={_ph()}"
        )
        params: List[Any] = [CURRENT_FY]
        if employee_id:
            sql += f" AND employee_id={_ph()}"
            params.append(employee_id)
        if only_pending:
            sql += " AND status IN ('SUBMITTED','RESUBMITTED','UNDER REVIEW')"
        sql += " ORDER BY submitted_on DESC, id DESC"
        cur.execute(sql, tuple(params))
        return _rows_to_dicts(cur)
    finally:
        cur.close()
        conn.close()


def review_allowance_claim(claim_id: int, approved_amount: float, status: str,
                            remarks: str, reviewer_id: str) -> None:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"UPDATE compliance_allowance_claims SET "
            f"approved_amount={_ph()}, status={_ph()}, reviewer_remarks={_ph()}, "
            f"reviewed_on={_ph()}, updated_on={_ph()} WHERE id={_ph()}",
            (int(approved_amount or 0), status, remarks, _now(), _now(), claim_id),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(reviewer_id, "REVIEW_ALLOWANCE", "allowance_claim", str(claim_id),
           f"{status}:{approved_amount}")


def get_allowance_proof_bytes(claim_id: int) -> Optional[Tuple[bytes, str, str]]:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT file_bytes, file_name, file_type FROM compliance_allowance_claims "
            f"WHERE id={_ph()}",
            (claim_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        blob = bytes(row[0]) if row[0] is not None else b""
        return blob, row[1] or "claim", row[2] or "application/octet-stream"
    finally:
        cur.close()
        conn.close()


# --- AI risk engine for allowances ---

def evaluate_allowance(claim: Dict[str, Any]) -> Dict[str, Any]:
    reasons: List[str] = []
    risk = "LOW"
    recommended_status = "APPROVED"

    amount = float(claim.get("amount") or 0)
    approved_ceiling = amount

    if amount <= 0:
        risk = "HIGH"
        recommended_status = "REJECTED"
        reasons.append("Allowance amount must be greater than zero.")
        approved_ceiling = 0

    if not float(amount).is_integer():
        risk = "HIGH"
        recommended_status = "RESUBMISSION_REQUIRED"
        reasons.append("Amount should be a whole number.")

    if not claim.get("file_name"):
        risk = "HIGH"
        recommended_status = "RESUBMISSION_REQUIRED"
        reasons.append("Supporting document is missing.")

    if not (claim.get("expense_details") or "").strip():
        risk = "MEDIUM" if risk == "LOW" else risk
        if recommended_status == "APPROVED":
            recommended_status = "RESUBMISSION_REQUIRED"
        reasons.append("Expense details / business justification missing.")

    if amount > 25000:
        if risk == "LOW":
            risk = "MEDIUM"
        reasons.append("High-value claim (>₹25,000) — manual verification recommended.")

    if not (claim.get("vendor_name") or "").strip():
        if risk == "LOW":
            risk = "MEDIUM"
        if recommended_status == "APPROVED":
            recommended_status = "UNDER REVIEW"
        reasons.append("Vendor name not specified.")

    if not reasons:
        reasons.append("Claim looks structurally complete.")

    return {
        "risk": risk,
        "recommended_status": recommended_status,
        "approved_ceiling": int(approved_ceiling),
        "reasons": reasons,
    }


# --- Aggregates for reports ---

def allowance_dashboard() -> Dict[str, Any]:
    ensure_schema()
    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT COUNT(*) FROM compliance_allowance_claims WHERE financial_year={_ph()}",
            (CURRENT_FY,),
        )
        total = cur.fetchone()[0] or 0
        cur.execute(
            f"""SELECT COUNT(*) FROM compliance_allowance_claims
                WHERE financial_year={_ph()} AND status IN ('SUBMITTED','RESUBMITTED','UNDER REVIEW')""",
            (CURRENT_FY,),
        )
        pending = cur.fetchone()[0] or 0
        cur.execute(
            f"SELECT COALESCE(SUM(amount),0), COALESCE(SUM(approved_amount),0) "
            f"FROM compliance_allowance_claims WHERE financial_year={_ph()}",
            (CURRENT_FY,),
        )
        claimed, approved = cur.fetchone()
        return {
            "total_claims": int(total),
            "pending_review": int(pending),
            "total_claimed": float(claimed or 0),
            "total_approved": float(approved or 0),
        }
    finally:
        cur.close()
        conn.close()


# =====================================================
# UI PANELS — ALLOWANCES (employee)
# =====================================================

def _claim_month_options() -> List[str]:
    """Return the current month and the previous two months as YYYY-MM strings."""
    today = dt.date.today()
    months = []
    y, m = today.year, today.month
    for _ in range(3):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return months


def _render_allowance_form(prefix: str, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    defaults = defaults or {}
    months = _claim_month_options()
    default_month = defaults.get("claim_month") or months[0]
    if default_month not in months:
        months = [default_month] + months
    c1, c2, c3 = st.columns(3)
    claim_month = c1.selectbox(
        "Claim month", months,
        index=months.index(default_month),
        key=f"am_{prefix}",
    )
    default_type = defaults.get("allowance_type", ALLOWANCE_TYPES[0])
    allowance_type = c2.selectbox(
        "Allowance type", ALLOWANCE_TYPES,
        index=ALLOWANCE_TYPES.index(default_type) if default_type in ALLOWANCE_TYPES else 0,
        key=f"at_{prefix}",
    )
    amount = c3.number_input(
        "Amount (₹)", min_value=0, step=1,
        value=int(defaults.get("amount") or 0),
        key=f"aa_{prefix}",
    )
    expense_details = st.text_area(
        "Expense details / business justification",
        value=defaults.get("expense_details", ""),
        key=f"ae_{prefix}",
        placeholder="Briefly explain the business purpose / what this claim covers",
    )
    c1, c2 = st.columns(2)
    vendor_name = c1.text_input(
        "Vendor name", value=defaults.get("vendor_name", ""),
        key=f"av_{prefix}",
    )
    bill_reference = c2.text_input(
        "Bill / invoice reference", value=defaults.get("bill_reference", ""),
        key=f"ab_{prefix}",
    )
    return {
        "claim_month": claim_month,
        "allowance_type": allowance_type,
        "amount": amount,
        "expense_details": expense_details,
        "vendor_name": vendor_name,
        "bill_reference": bill_reference,
    }


def render_monthly_allowances_panel(employee_id: str) -> None:
    if _delegate_employee_panel("monthly_allowances", employee_id):
        return
    ensure_schema()
    st.markdown("## 🧾 Monthly Allowances")
    _workflow_nav_buttons("monthly_allowances")
    st.caption(
        "Submit reimbursable expenses (Telephone / Internet, Electricity, Professional "
        "Membership, Software, Skill Development, etc.). Attach a supporting bill / "
        "receipt with each claim."
    )

    window_open = allowance_window_open()
    if not window_open:
        cutoff = get_setting("allowance_cutoff_day", "25")
        st.error(
            f"⛔ Submission window is currently **closed**. "
            f"(Cutoff day: {cutoff} of every month.)"
        )

    add_tab, manage_tab = st.tabs(["➕ Submit New Claim", "✏️ Manage / Resubmit"])

    with add_tab:
        with st.form("add_allowance_form"):
            payload = _render_allowance_form("add")
            file_obj = st.file_uploader(
                "Supporting document (PDF / JPG / PNG, max 5MB)",
                type=["pdf", "jpg", "jpeg", "png"],
                accept_multiple_files=False,
                key="add_allowance_file",
            )
            if st.form_submit_button("Submit allowance claim", type="primary",
                                       use_container_width=True,
                                       disabled=not window_open):
                errors = validate_allowance_payload(payload)
                if file_obj is None:
                    errors.append("Please attach a supporting document.")
                if errors:
                    for err in errors:
                        st.error(err)
                else:
                    try:
                        new_id = save_allowance_claim(employee_id, payload, file_obj)
                        st.success(f"✅ Allowance claim #{new_id} submitted.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

    claims = list_allowance_claims(employee_id)

    with manage_tab:
        editable = [c for c in claims if c.get("status") in
                    {"DRAFT", "SUBMITTED", "RESUBMISSION_REQUIRED", "REJECTED", "RESUBMITTED"}]
        if not editable:
            st.info("No editable claims right now.")
        for claim in editable:
            with st.expander(
                f"#{claim['id']} • {claim['allowance_type']} • "
                f"₹{int(claim['amount'] or 0):,} • {claim['claim_month']} • {claim['status']}"
            ):
                with st.form(f"edit_allowance_{claim['id']}"):
                    payload = _render_allowance_form(f"e{claim['id']}", claim)
                    new_file = st.file_uploader(
                        "Replace supporting document (optional)",
                        type=["pdf", "jpg", "jpeg", "png"],
                        accept_multiple_files=False,
                        key=f"replace_file_{claim['id']}",
                    )
                    c1, c2 = st.columns(2)
                    save_clicked = c1.form_submit_button("💾 Update claim",
                                                          type="primary",
                                                          use_container_width=True)
                    del_clicked = c2.form_submit_button("🗑️ Delete claim",
                                                         use_container_width=True)
                    if save_clicked:
                        errors = validate_allowance_payload(payload)
                        if errors:
                            for err in errors:
                                st.error(err)
                        else:
                            try:
                                update_allowance_claim(claim["id"], employee_id,
                                                        payload, new_file)
                                st.success("Claim updated.")
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))
                    if del_clicked:
                        try:
                            delete_allowance_claim(claim["id"], employee_id)
                            st.success("Claim deleted.")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))

    if claims:
        st.markdown("---")
        st.subheader("📋 All my allowance claims")
        df = pd.DataFrame(claims)
        display_cols = [c for c in [
            "id", "claim_month", "allowance_type", "amount", "approved_amount",
            "vendor_name", "bill_reference", "status", "reviewer_remarks",
            "submitted_on", "reviewed_on",
        ] if c in df.columns]
        st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
        csv = df[display_cols].to_csv(index=False).encode("utf-8")
        xbuf = io.BytesIO()
        with pd.ExcelWriter(xbuf, engine="openpyxl") as writer:
            _excel_safe_df(df[display_cols]).to_excel(writer, sheet_name="Monthly Allowances", index=False)
        xbuf.seek(0)
        d1, d2 = st.columns(2)
        d1.download_button(
            "⬇️ Download my allowances (CSV)",
            data=csv,
            file_name=f"{employee_id}_allowances_{CURRENT_FY.replace(' ','_')}.csv",
            mime="text/csv",
        )
        d2.download_button(
            "⬇️ Download my allowances (Excel)",
            data=xbuf.getvalue(),
            file_name=f"{employee_id}_allowances_{CURRENT_FY.replace(' ','_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.info("No allowance claims yet. Submit your first claim above.")


# =====================================================
# UI PANELS — ALLOWANCES (admin)
# =====================================================

def render_admin_allowance_review_queue() -> None:
    ensure_schema()
    if not _sarika_only():
        st.error("Only Sarika Gupta can access this admin workflow in this release.")
        return
    st.markdown("## 🧾 Allowance Review Queue")
    claims = list_allowance_claims(only_pending=True)
    if not claims:
        st.info("No allowance claims awaiting review.")
        return
    st.caption(f"📬 {len(claims)} claim(s) awaiting review")

    for claim in claims:
        advice = evaluate_allowance(claim)
        with st.container(border=True):
            risk_icon = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}.get(advice["risk"], "⚪")
            st.markdown(
                f"**{claim['employee_id']}** • {claim['allowance_type']} "
                f"({claim['claim_month']}) {risk_icon} Risk: {advice['risk']}"
            )
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Claimed", _money(claim.get("amount")))
            c2.metric("Suggested cap", _money(advice["approved_ceiling"]))
            c3.metric("Status", claim.get("status"))
            c4.metric("Resubmissions", int(claim.get("resubmission_count") or 0))

            if claim.get("vendor_name"):
                st.caption(f"**Vendor:** {claim.get('vendor_name')}  "
                           f"• **Bill ref:** {claim.get('bill_reference') or '-'}")
            if claim.get("expense_details"):
                st.caption(f"**Details:** {claim.get('expense_details')}")

            with st.expander("🤖 AI advice"):
                st.markdown(f"**Recommendation:** `{advice['recommended_status']}`")
                for r in advice["reasons"]:
                    st.markdown(f"- {r}")

            # Proof viewer
            if claim.get("file_name"):
                size_kb = (claim.get("file_size") or 0) // 1024
                col_a, col_b = st.columns([3, 1])
                col_a.markdown(f"📎 {claim['file_name']} ({size_kb} KB)")
                if col_b.button("⬇️ Download", key=f"adl_{claim['id']}"):
                    res = get_allowance_proof_bytes(claim["id"])
                    if res:
                        data, fname, mime = res
                        st.download_button(
                            f"Save {fname}",
                            data=data, file_name=fname, mime=mime,
                            key=f"adl_btn_{claim['id']}",
                        )

            approved = st.number_input(
                "Approved amount (₹)", min_value=0, step=1,
                value=int(claim.get("approved_amount") or advice["approved_ceiling"] or 0),
                key=f"apa_{claim['id']}",
            )
            actions = ["UNDER REVIEW", "RESUBMISSION_REQUIRED", "APPROVED", "REJECTED"]
            default_action = advice["recommended_status"] if advice["recommended_status"] in actions else "UNDER REVIEW"
            action = st.selectbox(
                "Action", actions,
                index=actions.index(default_action),
                key=f"aaa_{claim['id']}",
            )
            remarks = st.text_area(
                "Reviewer remarks", value="; ".join(advice["reasons"]),
                key=f"ara_{claim['id']}",
            )
            if st.button(f"💾 Save review #{claim['id']}",
                         key=f"asa_{claim['id']}", type="primary"):
                reviewer_id = st.session_state.get("employee_id", "admin")
                try:
                    review_allowance_claim(claim["id"], approved, action, remarks, reviewer_id)
                    st.success("Review saved.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def render_admin_workflow_settings() -> None:
    ensure_schema()
    if not _sarika_only():
        st.error("Only Sarika Gupta can access this admin workflow in this release.")
        return
    st.markdown("## ⚙️ Compliance Workflow Settings")
    st.caption("Controls the allowance submission window for employees.")

    current_override = get_setting("allowance_window_override", "OPEN")
    current_cutoff = int(get_setting("allowance_cutoff_day", "25") or 25)

    with st.container(border=True):
        st.markdown("### Allowance Submission Window")
        override_options = ["OPEN", "CONTROLLED", "CLOSED"]
        new_override = st.radio(
            "Window mode",
            override_options,
            index=override_options.index(current_override) if current_override in override_options else 0,
            help=(
                "**OPEN** — employees can submit any day (default).\n\n"
                "**CONTROLLED** — submissions allowed only up to the cutoff day each month.\n\n"
                "**CLOSED** — submissions blocked completely (e.g. during freeze week)."
            ),
        )
        new_cutoff = st.number_input(
            "Cutoff day (used only in CONTROLLED mode)",
            min_value=1, max_value=31, step=1,
            value=current_cutoff,
        )
        if st.button("💾 Save settings", type="primary"):
            reviewer_id = st.session_state.get("employee_id", "admin")
            try:
                set_setting("allowance_window_override", new_override, reviewer_id)
                set_setting("allowance_cutoff_day", str(int(new_cutoff)), reviewer_id)
                st.success("Settings saved.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.markdown("---")
    st.markdown("### Current effective status")
    is_open = allowance_window_open()
    if is_open:
        st.success(f"✅ Allowance window is currently **OPEN** (mode: {current_override}).")
    else:
        st.error(f"⛔ Allowance window is currently **CLOSED** (mode: {current_override}, "
                 f"cutoff: day {current_cutoff}).")
