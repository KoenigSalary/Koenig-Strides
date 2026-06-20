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
    - Investment Declaration (Old Regime only)
    - Proof Submission (PDF/JPG/PNG, max 5MB)
    - My Declaration report + CSV export
    - Admin: Review Queue, Regime Change Requests, Compliance Reports

Phase B (next ship):
    - Monthly Allowances (Telephone, Electricity, Professional, etc.)
"""

from __future__ import annotations

import io
import json
import re
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


# =====================================================
# CONFIG
# =====================================================

CURRENT_FY = "FY 2026-27"

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

SECTION_MASTER: List[Dict[str, Any]] = [
    {
        "section_code": "80C",
        "display_name": "Section 80C",
        "group_name": "Chapter VI-A",
        "items": [
            "Life Insurance Premium", "PPF", "EPF", "ELSS", "Tuition Fees",
            "Tax Saver FD", "NSC", "Sukanya Samriddhi", "Home Loan Principal",
        ],
        "amount_cap": 150000,
        "expected_proof": "Receipt / statement / policy receipt / bank advice",
    },
    {
        "section_code": "80CCD(1B)",
        "display_name": "Section 80CCD(1B)",
        "group_name": "Chapter VI-A",
        "items": ["NPS Additional Contribution"],
        "amount_cap": 50000,
        "expected_proof": "NPS contribution statement / transaction receipt",
    },
    {
        "section_code": "80D",
        "display_name": "Section 80D",
        "group_name": "Chapter VI-A",
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
        "display_name": "Section 80DD",
        "group_name": "Chapter VI-A",
        "items": ["Maintenance including medical treatment of dependent with disability"],
        "amount_cap": None,
        "expected_proof": "Disability certificate and payment proof",
    },
    {
        "section_code": "80DDB",
        "display_name": "Section 80DDB",
        "group_name": "Chapter VI-A",
        "items": ["Medical treatment for specified disease / ailment"],
        "amount_cap": None,
        "expected_proof": "Specialist certificate and payment proof",
    },
    {
        "section_code": "80E",
        "display_name": "Section 80E",
        "group_name": "Chapter VI-A",
        "items": ["Education Loan Interest"],
        "amount_cap": None,
        "expected_proof": "Interest certificate from lender",
    },
    {
        "section_code": "80G",
        "display_name": "Section 80G",
        "group_name": "Chapter VI-A",
        "items": ["Eligible donation"],
        "amount_cap": None,
        "expected_proof": "Donation receipt with donee PAN / registration details",
    },
    {
        "section_code": "24(b)",
        "display_name": "Section 24(b)",
        "group_name": "House Property",
        "items": ["Home Loan Interest"],
        "amount_cap": None,
        "expected_proof": "Home loan interest certificate",
    },
    {
        "section_code": "HRA",
        "display_name": "House Rent Allowance",
        "group_name": "Salary Allowances",
        "items": ["House Rent Allowance"],
        "amount_cap": None,
        "expected_proof": "Rent receipts / rent agreement / landlord PAN where applicable",
    },
    {
        "section_code": "CHILD_EDU",
        "display_name": "Children Education Allowance",
        "group_name": "Salary Allowances",
        "items": ["Children Education Allowance"],
        "amount_cap": None,
        "expected_proof": "School fee receipt",
    },
    {
        "section_code": "OTHER_VIA",
        "display_name": "Other Chapter VI-A",
        "group_name": "Chapter VI-A",
        "items": ["Other eligible deduction"],
        "amount_cap": None,
        "expected_proof": "Applicable proof as per section",
    },
]

SECTION_LOOKUP = {row["section_code"]: row for row in SECTION_MASTER}
SECTION_CODES = [row["section_code"] for row in SECTION_MASTER]

CLAIMANT_OPTIONS = ["Self", "Self + Family", "Parents", "Spouse", "Children", "Dependent"]
RELATION_OPTIONS = ["Self", "Father", "Mother", "Spouse", "Son", "Daughter", "Brother", "Sister", "Other"]
LANDLORD_RELATIONS = ["Unrelated", "Father", "Mother", "Spouse", "Brother", "Sister", "Other Relative"]


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
        return _rows_to_dicts(cur)
    finally:
        cur.close()
        conn.close()


def submit_declaration(employee_id: str) -> None:
    header = get_or_create_header(employee_id)
    items = list_declaration_items(employee_id)
    if not items:
        raise ValueError("Add at least one declaration item before submitting.")
    conn = _get_conn()
    cur = conn.cursor()
    try:
        # Move DRAFT / RESUBMITTED items to SUBMITTED state.
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
            f"SET workflow_stage='PROOF_WAIT', status='DECLARATION_SUBMITTED', updated_on={_ph()} "
            f"WHERE id={_ph()}",
            (_now(), header["id"]),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
    _audit(employee_id, "SUBMIT_DECLARATION", "header", str(header["id"]), f"items={len(items)}")


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
        cur.execute("SELECT * FROM compliance_audit_logs ORDER BY id DESC LIMIT 500")
        audit = _rows_to_dicts(cur)
    finally:
        cur.close()
        conn.close()

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(headers).to_excel(writer, sheet_name="Headers", index=False)
        pd.DataFrame(items).to_excel(writer, sheet_name="Declarations", index=False)
        pd.DataFrame(rcrs).to_excel(writer, sheet_name="Regime Changes", index=False)
        pd.DataFrame(audit).to_excel(writer, sheet_name="Audit", index=False)
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

    if section == "80D" and not item.get("claimant_for"):
        risk = "MEDIUM" if risk == "LOW" else risk
        if recommended_status == "APPROVED":
            recommended_status = "RESUBMISSION_REQUIRED"
        reasons.append("Section 80D needs claimant type (Self/Family/Parents).")

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
    declared = payload.get("declared_amount", 0)
    try:
        declared = float(declared)
        if declared <= 0:
            errors.append("Declared amount must be greater than zero.")
        if not float(declared).is_integer():
            errors.append("Declared amount should be a whole number.")
    except Exception:
        errors.append("Declared amount must be numeric.")

    if section == "HRA":
        if not payload.get("landlord_name"):
            errors.append("Landlord name is mandatory for HRA.")
        if not payload.get("rental_property_address"):
            errors.append("Rental property address is mandatory for HRA.")
        rent = float(payload.get("annual_rent") or 0)
        pan = (payload.get("landlord_pan") or "").strip().upper()
        if rent > 100000 and not pan:
            errors.append("Landlord PAN required when annual rent > ₹1,00,000.")
        if pan and not PAN_REGEX.match(pan):
            errors.append("Landlord PAN format is invalid (e.g., AAAPL1234C).")
    if section == "80DDB" and not payload.get("disease_name"):
        errors.append("Disease name is mandatory for 80DDB.")
    if section == "80D" and not payload.get("claimant_for"):
        errors.append("Claimant type is mandatory for 80D.")
    if section == "CHILD_EDU" and int(payload.get("children_count") or 0) <= 0:
        errors.append("Children count must be at least 1 for CEA.")
    return errors


# =====================================================
# UI PANELS — EMPLOYEE
# =====================================================

def _money(value) -> str:
    try:
        return f"₹ {float(value or 0):,.0f}"
    except Exception:
        return "₹ 0"


def _section_options() -> List[str]:
    return [f"{row['section_code']} | {row['display_name']}" for row in SECTION_MASTER]


def _parse_section(selected: str) -> str:
    return selected.split("|", 1)[0].strip()


def _render_item_form(prefix: str, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    defaults = defaults or {}
    options = _section_options()
    default_code = defaults.get("section_code", "80C")
    default_idx = SECTION_CODES.index(default_code) if default_code in SECTION_CODES else 0
    selected = st.selectbox("Section / Claim type", options, index=default_idx, key=f"sec_{prefix}")
    section_code = _parse_section(selected)
    cfg = SECTION_LOOKUP[section_code]

    items = cfg["items"]
    default_item = defaults.get("item_name", items[0]) if defaults.get("item_name") in items else items[0]
    c1, c2, c3 = st.columns(3)
    item_name = c1.selectbox("Item", items, index=items.index(default_item), key=f"item_{prefix}")
    declared = c2.number_input(
        "Declared amount (₹)", min_value=0, step=1,
        value=int(defaults.get("declared_amount") or 0), key=f"amt_{prefix}",
    )
    expected = c3.text_input(
        "Expected proof", value=defaults.get("expected_proof") or cfg["expected_proof"],
        key=f"proof_{prefix}",
    )
    remarks = st.text_area("Remarks", value=defaults.get("remarks", ""), key=f"rem_{prefix}")

    payload: Dict[str, Any] = {
        "section_code": section_code,
        "section_group": cfg["group_name"],
        "item_name": item_name,
        "declared_amount": declared,
        "expected_proof": expected,
        "remarks": remarks,
    }

    if section_code in ("80D", "80DD", "80DDB", "80E", "24(b)", "CHILD_EDU"):
        opts = [""] + CLAIMANT_OPTIONS
        cur = defaults.get("claimant_for", "")
        payload["claimant_for"] = st.selectbox(
            "Claiming for", opts,
            index=opts.index(cur) if cur in opts else 0, key=f"claim_{prefix}",
        )

    if section_code in ("80DD", "80DDB"):
        opts = [""] + RELATION_OPTIONS
        cur = defaults.get("relation_to_employee", "")
        payload["relation_to_employee"] = st.selectbox(
            "Relation", opts,
            index=opts.index(cur) if cur in opts else 0, key=f"rel_{prefix}",
        )

    if section_code == "80DDB":
        payload["disease_name"] = st.text_input(
            "Disease name", value=defaults.get("disease_name", ""), key=f"dis_{prefix}",
        )

    if section_code == "HRA":
        c1, c2 = st.columns(2)
        payload["landlord_name"] = c1.text_input(
            "Landlord name", value=defaults.get("landlord_name", ""), key=f"lname_{prefix}",
        )
        rel_options = LANDLORD_RELATIONS
        cur_rel = defaults.get("landlord_relation", LANDLORD_RELATIONS[0])
        payload["landlord_relation"] = c2.selectbox(
            "Landlord relation", rel_options,
            index=rel_options.index(cur_rel) if cur_rel in rel_options else 0,
            key=f"lrel_{prefix}",
        )
        payload["landlord_pan"] = st.text_input(
            "Landlord PAN (mandatory if rent > ₹1L)",
            value=defaults.get("landlord_pan", ""), key=f"lpan_{prefix}",
        )
        payload["rental_property_address"] = st.text_area(
            "Rental property address",
            value=defaults.get("rental_property_address", ""), key=f"laddr_{prefix}",
        )
        payload["annual_rent"] = st.number_input(
            "Annual rent paid (₹)", min_value=0, step=1,
            value=int(defaults.get("annual_rent") or defaults.get("declared_amount") or 0),
            key=f"rent_{prefix}",
        )

    if section_code == "CHILD_EDU":
        payload["children_count"] = st.number_input(
            "Eligible children", min_value=0, max_value=4, step=1,
            value=int(defaults.get("children_count") or 0), key=f"kids_{prefix}",
        )

    return payload


def render_tax_regime_panel(employee_id: str) -> None:
    ensure_schema()
    header = get_or_create_header(employee_id)
    st.markdown("## 📋 Tax Regime Selection")
    st.caption(f"Financial Year: **{CURRENT_FY}** • Employee: **{employee_id}**")

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
            st.caption("Allowed once per financial year, subject to admin approval.")
            current = header.get("tax_regime") or ""
            other = "New Regime" if current == "Old Regime" else "Old Regime"
            reason = st.text_area("Reason for change", placeholder="Explain why you'd like to switch...")
            already_used = int(header.get("regime_change_used") or 0) >= 1
            if already_used:
                st.warning("⚠️ One-time regime change already used for this FY.")
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
    ensure_schema()
    header = get_or_create_header(employee_id)
    st.markdown("## 🧾 Investment Declaration")

    if header.get("tax_regime") != "Old Regime":
        st.warning(
            "Investment declaration is available only for **Old Regime** employees. "
            "Visit the **Tax Regime** panel first to select Old Regime."
        )
        return

    add_tab, manage_tab = st.tabs(["➕ Add Item", "✏️ Manage / Resubmit"])

    with add_tab:
        with st.form("add_decl_form"):
            payload = _render_item_form("add")
            if st.form_submit_button("Add declaration item", type="primary", use_container_width=True):
                errors = validate_declaration_payload(payload)
                if errors:
                    for err in errors:
                        st.error(err)
                else:
                    try:
                        add_declaration_item(employee_id, payload)
                        st.success("Item added.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

    items = list_declaration_items(employee_id)

    with manage_tab:
        editable_statuses = {"DRAFT", "RESUBMISSION_REQUIRED", "REJECTED", "RESUBMITTED"}
        editable = [x for x in items if x.get("status") in editable_statuses]
        if not editable:
            st.info("No editable items right now.")
        for item in editable:
            with st.expander(f"#{item['id']} • {item['section_code']} • {item['item_name']} "
                             f"• {_money(item.get('declared_amount'))} • {item.get('status')}"):
                with st.form(f"edit_decl_{item['id']}"):
                    payload = _render_item_form(f"edit_{item['id']}", item)
                    c1, c2 = st.columns(2)
                    save_clicked = c1.form_submit_button("💾 Update item", type="primary",
                                                          use_container_width=True)
                    del_clicked = c2.form_submit_button("🗑️ Delete item",
                                                         use_container_width=True)
                    if save_clicked:
                        errors = validate_declaration_payload(payload)
                        if errors:
                            for err in errors:
                                st.error(err)
                        else:
                            try:
                                update_declaration_item(item["id"], employee_id, payload)
                                st.success("Item updated.")
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))
                    if del_clicked:
                        try:
                            delete_declaration_item(item["id"], employee_id)
                            st.success("Item deleted.")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))

    if items:
        st.markdown("---")
        st.subheader("📋 Current declaration register")
        df = pd.DataFrame(items)
        display_cols = [c for c in [
            "id", "section_group", "section_code", "item_name", "declared_amount",
            "actual_amount", "approved_amount", "status", "proof_count", "reviewer_remarks",
        ] if c in df.columns]
        st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
        total = float(pd.to_numeric(df["declared_amount"], errors="coerce").fillna(0).sum())
        c1, c2 = st.columns(2)
        c1.metric("Total declared", _money(total))
        if c2.button("✅ Submit final declaration", type="primary", use_container_width=True):
            try:
                submit_declaration(employee_id)
                st.success("Declaration submitted. Upload proofs in the Proof Submission panel.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    else:
        st.info("No declaration items yet. Add one above to get started.")


def render_proof_submission_panel(employee_id: str) -> None:
    ensure_schema()
    header = get_or_create_header(employee_id)
    st.markdown("## 📎 Proof Submission")

    if header.get("tax_regime") != "Old Regime":
        st.warning("Proof submission is only required for Old Regime employees.")
        return

    items = list_declaration_items(employee_id)
    if not items:
        st.info("No declaration items found. Add items in the **Investment Declaration** panel first.")
        return

    allowed = {"SUBMITTED", "RESUBMITTED", "RESUBMISSION_REQUIRED", "UNDER REVIEW",
               "REJECTED", "PROOF_SUBMITTED"}
    for item in items:
        with st.container(border=True):
            st.markdown(f"### {item['section_code']} • {item['item_name']}")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Declared", _money(item.get("declared_amount")))
            c2.metric("Actual", _money(item.get("actual_amount")))
            c3.metric("Proofs", int(item.get("proof_count") or 0))
            c4.metric("Status", item.get("status") or "DRAFT")
            st.caption(f"Expected: {item.get('expected_proof') or '-'}")
            if item.get("reviewer_remarks"):
                st.warning(f"Reviewer remarks: {item.get('reviewer_remarks')}")

            if item.get("status") in allowed:
                actual = st.number_input(
                    f"Actual amount (₹)", min_value=0, step=1,
                    value=int(item.get("actual_amount") or item.get("declared_amount") or 0),
                    key=f"act_{item['id']}",
                )
                files = st.file_uploader(
                    "Upload proof (PDF / JPG / PNG, max 5MB each)",
                    type=["pdf", "jpg", "jpeg", "png"],
                    accept_multiple_files=True,
                    key=f"up_{item['id']}",
                )
                if st.button(f"💾 Save proof for item #{item['id']}", key=f"save_p_{item['id']}"):
                    if not files:
                        st.error("Please choose at least one file.")
                    else:
                        had_error = False
                        for f in files:
                            try:
                                save_proof(item["id"], employee_id, actual, f)
                            except Exception as exc:
                                st.error(f"{f.name}: {exc}")
                                had_error = True
                        if not had_error:
                            st.success(f"Uploaded {len(files)} file(s).")
                            st.rerun()
            else:
                st.info("Not currently open for proof upload.")

            existing = list_proofs_for_item(item["id"])
            if existing:
                st.caption(f"📁 {len(existing)} proof(s) on record:")
                for p in existing:
                    size_kb = (p.get("file_size") or 0) // 1024
                    st.markdown(f"  • {p.get('file_name')} ({size_kb} KB) — uploaded {p.get('uploaded_on')}")


def render_my_declaration_panel(employee_id: str) -> None:
    ensure_schema()
    header = get_or_create_header(employee_id)
    items = list_declaration_items(employee_id)
    st.markdown("## 📊 My Declaration")
    c1, c2, c3 = st.columns(3)
    c1.metric("Regime", header.get("tax_regime") or "Not selected")
    c2.metric("Items", len(items))
    c3.metric("Stage", header.get("workflow_stage") or "REGIME_SELECTION")

    if items:
        df = pd.DataFrame(items)
        display_cols = [c for c in [
            "id", "section_code", "item_name", "declared_amount", "actual_amount",
            "approved_amount", "status", "proof_count", "reviewer_remarks",
        ] if c in df.columns]
        st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download my declaration (CSV)",
            data=csv,
            file_name=f"{employee_id}_declaration_{CURRENT_FY.replace(' ','_')}.csv",
            mime="text/csv",
        )
    else:
        st.info("No declarations yet.")


# =====================================================
# UI PANELS — ADMIN
# =====================================================

def render_admin_review_queue() -> None:
    ensure_schema()
    st.markdown("## 🛡️ Compliance Review Queue")
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
                f"**{item.get('employee_id')}** — {item['section_code']} / {item['item_name']} "
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

            # Proof viewer
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
            actions = ["UNDER REVIEW", "RESUBMISSION_REQUIRED", "APPROVED", "REJECTED"]
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
                    review_declaration_item(item["id"], approved, action, remarks, reviewer_id)
                    st.success("Review saved.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def render_admin_regime_change_panel() -> None:
    ensure_schema()
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

    st.markdown("---")
    excel_bytes = export_compliance_excel()
    st.download_button(
        "⬇️ Download Tax-Team Excel export",
        data=excel_bytes,
        file_name=f"compliance_export_{CURRENT_FY.replace(' ','_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
