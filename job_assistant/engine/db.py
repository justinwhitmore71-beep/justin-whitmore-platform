"""
Multi-Tenant Database & Repository Layer for the AI Recruitment Platform.
- Preserves and automatically migrates Justin's existing single-user jobs & generated CVs.
- Enforces strict server-side tenant isolation on every user query (preventing IDOR).
- Enforces permission-controlled, audited Administrator assistance grants (admin cannot view
  another user's private CVs, correspondence, or notes without explicit user-granted consent).
- Supports local SQLite (default) and optional Cloud Firestore synchronization adapter.
"""

import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from job_assistant.engine.security import (
    AccessDeniedError,
    VaultStorage,
    hash_password,
    verify_password,
    generate_recovery_token,
    hash_token,
)
from job_assistant.engine.profiles_seed import get_seed_users

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "jobs.db")
BOOTSTRAP_CREDS_PATH = os.path.join(BASE_DIR, "data", "bootstrap_credentials.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str = DB_PATH):
    """Initializes multi-tenant tables, seeds the 3 accounts, and migrates legacy jobs non-destructively."""
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.executescript("""
    -- Legacy tables kept intact for non-destructive safety
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dedup_hash TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        company TEXT NOT NULL,
        location TEXT NOT NULL,
        remote_type TEXT DEFAULT 'On-site',
        salary TEXT,
        job_url TEXT NOT NULL,
        source TEXT NOT NULL,
        description TEXT,
        date_discovered TEXT NOT NULL,
        deadline TEXT,
        match_score INTEGER DEFAULT 0,
        score_breakdown TEXT,
        score_rationale TEXT,
        english_required INTEGER DEFAULT 1,
        french_required INTEGER DEFAULT 0,
        transit_accessible INTEGER DEFAULT 1,
        is_practical_role INTEGER DEFAULT 0,
        status TEXT DEFAULT 'discovered',
        priority TEXT DEFAULT 'normal',
        cv_version TEXT,
        cover_letter_path TEXT,
        follow_up_date TEXT,
        interview_info TEXT,
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS scan_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        query TEXT,
        found_count INTEGER DEFAULT 0,
        new_count INTEGER DEFAULT 0,
        scanned_at TEXT NOT NULL,
        status TEXT,
        error_message TEXT
    );

    -- Multi-User Platform Schema
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        account_status TEXT DEFAULT 'active', -- active, pending_verification, suspended
        profile_verified INTEGER DEFAULT 0,
        firebase_uid TEXT UNIQUE,
        created_at TEXT NOT NULL,
        last_login_at TEXT
    );

    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash TEXT UNIQUE NOT NULL,
        expires_at TEXT NOT NULL,
        used_at TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        profile_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS vacancies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        canonical_hash TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        company TEXT NOT NULL,
        location TEXT NOT NULL,
        country TEXT DEFAULT '',
        remote_type TEXT DEFAULT 'On-site', -- Remote, Hybrid, On-site
        remote_country_restrictions TEXT DEFAULT '',
        salary TEXT DEFAULT '',
        contract_type TEXT DEFAULT '',
        seniority TEXT DEFAULT '',
        category TEXT DEFAULT '',
        required_languages TEXT DEFAULT '',
        required_experience TEXT DEFAULT '',
        required_qualifications TEXT DEFAULT '',
        work_auth_requirements TEXT DEFAULT '',
        relocation_assistance INTEGER DEFAULT 0,
        job_url TEXT NOT NULL,
        source TEXT NOT NULL,
        description TEXT DEFAULT '',
        published_at TEXT DEFAULT '',
        deadline TEXT DEFAULT '',
        quality_flags_json TEXT DEFAULT '{}',
        is_expired INTEGER DEFAULT 0,
        discovered_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS user_job_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        vacancy_id INTEGER NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
        match_score INTEGER DEFAULT 0,
        score_breakdown_json TEXT DEFAULT '{}',
        score_rationale TEXT DEFAULT '',
        gap_analysis_json TEXT DEFAULT '{}',
        status TEXT DEFAULT 'discovered', -- discovered, saved, awaiting_approval, ready_to_apply, applied, interviewing, rejected, archived
        priority TEXT DEFAULT 'normal',
        is_practical_role INTEGER DEFAULT 0,
        cv_document_id INTEGER,
        cv_version_label TEXT DEFAULT '',
        cover_letter_document_id INTEGER,
        app_answers_json TEXT DEFAULT '{}',
        interview_prep_json TEXT DEFAULT '{}',
        follow_up_date TEXT DEFAULT '',
        interview_info TEXT DEFAULT '',
        private_notes TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(user_id, vacancy_id)
    );

    CREATE TABLE IF NOT EXISTS user_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        vacancy_id INTEGER REFERENCES vacancies(id) ON DELETE SET NULL,
        doc_kind TEXT NOT NULL, -- master_cv, uploaded_cv, tailored_cv, cover_letter
        version_label TEXT NOT NULL,
        filename TEXT NOT NULL,
        storage_key TEXT NOT NULL,
        extracted_text TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS user_custom_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        source_name TEXT NOT NULL,
        source_type TEXT NOT NULL DEFAULT 'company_career_page', -- company_career_page, job_board_url, custom_search_query, rss_feed
        target_url TEXT DEFAULT '',
        query_keywords TEXT DEFAULT '',
        target_location TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        last_scanned_at TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS admin_access_grants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        grantee_admin_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        scope TEXT NOT NULL, -- profile_assist, matches_view, documents_view
        expires_at TEXT NOT NULL,
        revoked_at TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_user_id INTEGER,
        target_user_id INTEGER,
        action TEXT NOT NULL,
        details TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS scheduler_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        task_name TEXT NOT NULL,
        status TEXT NOT NULL,
        summary TEXT DEFAULT '',
        executed_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS error_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        component TEXT NOT NULL,
        user_id INTEGER,
        error_message TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_vacancies_source ON vacancies(source);
    CREATE INDEX IF NOT EXISTS idx_vacancies_remote ON vacancies(remote_type);
    CREATE INDEX IF NOT EXISTS idx_matches_user_score ON user_job_matches(user_id, match_score DESC);
    CREATE INDEX IF NOT EXISTS idx_matches_user_status ON user_job_matches(user_id, status);
    CREATE INDEX IF NOT EXISTS idx_docs_user ON user_documents(user_id, doc_kind);
    """)
    conn.commit()
    conn.close()

    _seed_users_and_migrate_legacy(db_path=db_path)


def _seed_users_and_migrate_legacy(db_path: str = DB_PATH):
    conn = get_connection(db_path)
    cur = conn.cursor()
    now = _now_iso()

    bootstrap_creds: Dict[str, Any] = {}
    if os.path.isfile(BOOTSTRAP_CREDS_PATH):
        try:
            with open(BOOTSTRAP_CREDS_PATH, "r", encoding="utf-8") as f:
                bootstrap_creds = json.load(f)
        except Exception:
            bootstrap_creds = {}

    DEFAULT_BOOTSTRAP_PASSWORDS = {
        "justin": "Chan.ho.park1",
        "isil": "Recruit-Isil-QvD5yg-6loM",
        "lindsey": "Recruit-Lindsey-3BqvlR4Y38E"
    }

    creds_changed = False
    for u in get_seed_users():
        slug = u["slug"]
        cur.execute("SELECT id FROM users WHERE slug = ?", (slug,))
        existing = cur.fetchone()
        if existing:
            user_id = existing["id"]
            cur.execute("SELECT user_id FROM user_profiles WHERE user_id = ?", (user_id,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO user_profiles (user_id, profile_json, updated_at) VALUES (?, ?, ?)",
                    (user_id, json.dumps(u["profile"], ensure_ascii=False), now),
                )
            # Synchronize initial bootstrap password if user has not logged in yet
            cur.execute("SELECT last_login_at FROM users WHERE id = ?", (user_id,))
            urow = cur.fetchone()
            if not urow or not urow["last_login_at"]:
                def_pw = os.environ.get(f"{slug.upper()}_INIT_PASSWORD") or DEFAULT_BOOTSTRAP_PASSWORDS.get(slug)
                if def_pw:
                    cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(def_pw), user_id))
            continue

        env_key = f"{slug.upper()}_INIT_PASSWORD"
        raw_pw = os.environ.get(env_key)
        if not raw_pw:
            raw_pw = bootstrap_creds.get(slug, {}).get("initial_password")
        if not raw_pw:
            raw_pw = DEFAULT_BOOTSTRAP_PASSWORDS.get(slug)
        if not raw_pw:
            raw_pw = f"Recruit-{slug.capitalize()}-{secrets.token_urlsafe(8)}"
            bootstrap_creds[slug] = {
                "username_or_slug": slug,
                "email": u["email"],
                "initial_password": raw_pw,
                "note": "Local bootstrap credential. Change via Profile/Security settings after first sign-in."
            }
            creds_changed = True

        pw_hash = hash_password(raw_pw)
        cur.execute("""
            INSERT INTO users (slug, full_name, email, password_hash, is_admin, account_status, profile_verified, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            slug,
            u["full_name"],
            u["email"],
            pw_hash,
            1 if u["is_admin"] else 0,
            u["account_status"],
            1 if u["profile_verified"] else 0,
            now
        ))
        user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO user_profiles (user_id, profile_json, updated_at) VALUES (?, ?, ?)",
            (user_id, json.dumps(u["profile"], ensure_ascii=False), now)
        )

    conn.commit()

    if creds_changed and db_path == DB_PATH:
        os.makedirs(os.path.dirname(BOOTSTRAP_CREDS_PATH), exist_ok=True)
        with open(BOOTSTRAP_CREDS_PATH, "w", encoding="utf-8") as f:
            json.dump(bootstrap_creds, f, indent=2, ensure_ascii=False)

    # Migrate legacy `jobs` rows into `vacancies` + `user_job_matches` for Justin (if not already migrated)
    cur.execute("SELECT id FROM users WHERE slug = 'justin'")
    justin_row = cur.fetchone()
    if justin_row:
        justin_id = justin_row["id"]
        cur.execute("SELECT COUNT(*) as cnt FROM user_job_matches WHERE user_id = ?", (justin_id,))
        already_migrated = cur.fetchone()["cnt"] > 0
        cur.execute("SELECT COUNT(*) as cnt FROM jobs")
        legacy_count = cur.fetchone()["cnt"]

        if legacy_count > 0 and not already_migrated:
            vault = VaultStorage()
            cur.execute("SELECT * FROM jobs ORDER BY id ASC")
            legacy_rows = cur.fetchall()
            for r in legacy_rows:
                # 1. Insert or locate vacancy
                cur.execute("SELECT id FROM vacancies WHERE canonical_hash = ?", (r["dedup_hash"],))
                v_row = cur.fetchone()
                if v_row:
                    vac_id = v_row["id"]
                else:
                    cur.execute("""
                        INSERT INTO vacancies (
                            canonical_hash, title, company, location, remote_type,
                            salary, job_url, source, description, published_at,
                            deadline, discovered_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        r["dedup_hash"],
                        r["title"],
                        r["company"],
                        r["location"],
                        r["remote_type"] or "On-site",
                        r["salary"] or "",
                        r["job_url"],
                        r["source"],
                        r["description"] or "",
                        r["date_discovered"] or now[:10],
                        r["deadline"] or "",
                        r["created_at"] or now,
                        r["updated_at"] or now,
                    ))
                    vac_id = cur.lastrowid

                # Check if legacy generated application files exist for this legacy job id
                cv_doc_id = None
                cl_doc_id = None
                qna_json_str = "{}"
                legacy_app_dir = os.path.join(BASE_DIR, "generated_applications", f"job_{r['id']}")
                if db_path == DB_PATH and os.path.isdir(legacy_app_dir):
                    for fname in os.listdir(legacy_app_dir):
                        fpath = os.path.join(legacy_app_dir, fname)
                        if not os.path.isfile(fpath):
                            continue
                        with open(fpath, "r", encoding="utf-8", errors="replace") as lf:
                            content_txt = lf.read()
                        if fname.startswith("CV_"):
                            skey = vault.save_text(justin_id, justin_id, fname, content_txt, subfolder="migrated_apps")
                            cur.execute("""
                                INSERT INTO user_documents (user_id, vacancy_id, doc_kind, version_label, filename, storage_key, extracted_text, created_at)
                                VALUES (?, ?, 'tailored_cv', ?, ?, ?, ?, ?)
                            """, (justin_id, vac_id, fname, fname, skey, content_txt, now))
                            cv_doc_id = cur.lastrowid
                        elif fname.startswith("Cover_Letter_"):
                            skey = vault.save_text(justin_id, justin_id, fname, content_txt, subfolder="migrated_apps")
                            cur.execute("""
                                INSERT INTO user_documents (user_id, vacancy_id, doc_kind, version_label, filename, storage_key, extracted_text, created_at)
                                VALUES (?, ?, 'cover_letter', ?, ?, ?, ?, ?)
                            """, (justin_id, vac_id, fname, fname, skey, content_txt, now))
                            cl_doc_id = cur.lastrowid
                        elif fname.startswith("Screening_QnA_"):
                            qna_json_str = content_txt

                status_mapped = r["status"] if r["status"] != "bookmarked" else "saved"
                cur.execute("""
                    INSERT OR IGNORE INTO user_job_matches (
                        user_id, vacancy_id, match_score, score_breakdown_json, score_rationale,
                        status, priority, is_practical_role, cv_document_id, cv_version_label,
                        cover_letter_document_id, app_answers_json, follow_up_date,
                        interview_info, private_notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    justin_id,
                    vac_id,
                    r["match_score"] or 0,
                    r["score_breakdown"] or "{}",
                    r["score_rationale"] or "",
                    status_mapped,
                    r["priority"] or "normal",
                    r["is_practical_role"] or 0,
                    cv_doc_id,
                    r["cv_version"] or "",
                    cl_doc_id,
                    qna_json_str,
                    r["follow_up_date"] or "",
                    r["interview_info"] or "",
                    r["notes"] or "",
                    r["created_at"] or now,
                    r["updated_at"] or now,
                ))
            conn.commit()
    conn.close()


# =============================================================================
# ACCESS CONTROL & AUDIT HELPERS
# =============================================================================

def record_audit_log(
    actor_user_id: Optional[int],
    target_user_id: Optional[int],
    action: str,
    details: str = "",
    db_path: str = DB_PATH
):
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO audit_logs (actor_user_id, target_user_id, action, details, created_at) VALUES (?, ?, ?, ?, ?)",
        (actor_user_id, target_user_id, action, details, _now_iso())
    )
    conn.commit()
    conn.close()


def record_error_log(component: str, error_message: str, user_id: Optional[int] = None, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO error_logs (component, user_id, error_message, created_at) VALUES (?, ?, ?, ?)",
        (component, user_id, error_message[:2000], _now_iso())
    )
    conn.commit()
    conn.close()


def has_active_assistance_grant(
    admin_user_id: int,
    owner_user_id: int,
    required_scope: str,
    db_path: str = DB_PATH
) -> bool:
    """Checks whether owner_user_id has granted an unexpired, unrevoked assistance permission to admin_user_id."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT is_admin FROM users WHERE id = ?", (admin_user_id,))
    admin_row = cur.fetchone()
    if not admin_row or not admin_row["is_admin"]:
        conn.close()
        return False

    now = _now_iso()
    cur.execute("""
        SELECT id FROM admin_access_grants
        WHERE owner_user_id = ?
          AND grantee_admin_id = ?
          AND (scope = ? OR scope = 'full_assist')
          AND revoked_at IS NULL
          AND expires_at > ?
        LIMIT 1
    """, (owner_user_id, admin_user_id, required_scope, now))
    found = cur.fetchone() is not None
    conn.close()
    return found


def assert_tenant_access(
    acting_user_id: int,
    owner_user_id: int,
    required_scope: str = "matches_view",
    allow_granted_admin: bool = False,
    db_path: str = DB_PATH
) -> bool:
    """
    Central Server-Side Authorization Gate.
    - Returns True if acting_user_id == owner_user_id.
    - If acting_user_id != owner_user_id:
      * Only succeeds when allow_granted_admin=True AND owner_user_id explicitly granted required_scope
        to acting_user_id; logs access to audit_logs.
      * Otherwise raises AccessDeniedError!
    """
    if not acting_user_id or not owner_user_id:
        raise AccessDeniedError("Authentication required.")
    if acting_user_id == owner_user_id:
        return False  # Direct owner access (not via grant)

    if allow_granted_admin and has_active_assistance_grant(acting_user_id, owner_user_id, required_scope, db_path=db_path):
        record_audit_log(
            acting_user_id,
            owner_user_id,
            f"admin_assisted_access:{required_scope}",
            f"Admin #{acting_user_id} accessed scope '{required_scope}' under active user grant.",
            db_path=db_path
        )
        return True

    record_audit_log(
        acting_user_id,
        owner_user_id,
        f"blocked_unauthorized_access:{required_scope}",
        f"Denied user #{acting_user_id} attempting to access user #{owner_user_id} ({required_scope}).",
        db_path=db_path
    )
    raise AccessDeniedError("Forbidden: You do not have permission to access another user's private workspace.")


def grant_admin_assistance(
    owner_user_id: int,
    grantee_admin_id: int,
    scope: str,
    hours_valid: int = 24,
    db_path: str = DB_PATH
) -> int:
    from datetime import timedelta
    expires = (datetime.now(timezone.utc) + timedelta(hours=max(1, min(hours_valid, 168)))).isoformat()
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT is_admin FROM users WHERE id = ?", (grantee_admin_id,))
    r = cur.fetchone()
    if not r or not r["is_admin"]:
        conn.close()
        raise ValueError("Target user is not an administrator.")
    cur.execute("""
        INSERT INTO admin_access_grants (owner_user_id, grantee_admin_id, scope, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (owner_user_id, grantee_admin_id, scope, expires, _now_iso()))
    grant_id = cur.lastrowid
    conn.commit()
    conn.close()
    record_audit_log(owner_user_id, grantee_admin_id, "grant_admin_assistance", f"Scope={scope}, expires={expires}", db_path=db_path)
    return grant_id


def revoke_admin_assistance(owner_user_id: int, grant_id: int, db_path: str = DB_PATH) -> bool:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "UPDATE admin_access_grants SET revoked_at = ? WHERE id = ? AND owner_user_id = ? AND revoked_at IS NULL",
        (_now_iso(), grant_id, owner_user_id)
    )
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    if ok:
        record_audit_log(owner_user_id, owner_user_id, "revoke_admin_assistance", f"Revoked grant #{grant_id}", db_path=db_path)
    return ok


def list_user_grants(acting_user_id: int, owner_user_id: int, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    assert_tenant_access(acting_user_id, owner_user_id, allow_granted_admin=False, db_path=db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT g.*, u.full_name as admin_name
        FROM admin_access_grants g
        JOIN users u ON u.id = g.grantee_admin_id
        WHERE g.owner_user_id = ?
        ORDER BY g.id DESC
    """, (owner_user_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# =============================================================================
# AUTHENTICATION & USER ACCOUNT REPOSITORY
# =============================================================================

def authenticate_user(identifier: str, password: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Authenticates by username slug or email."""
    ident = (identifier or "").strip().lower()
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE lower(slug) = ? OR lower(email) = ?", (ident, ident))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    if row["account_status"] == "suspended":
        conn.close()
        return None
    if not verify_password(password, row["password_hash"]):
        conn.close()
        record_audit_log(row["id"], row["id"], "login_failed", "Invalid password", db_path=db_path)
        return None

    now = _now_iso()
    cur.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, row["id"]))
    conn.commit()
    user_dict = dict(row)
    user_dict.pop("password_hash", None)
    conn.close()
    record_audit_log(user_dict["id"], user_dict["id"], "login_success", "", db_path=db_path)
    return user_dict


def get_user_by_id(user_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, slug, full_name, email, is_admin, account_status, profile_verified, created_at, last_login_at FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_slug(slug: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, slug, full_name, email, is_admin, account_status, profile_verified, created_at, last_login_at FROM users WHERE slug = ?", (slug.lower(),))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def create_password_reset(identifier: str, db_path: str = DB_PATH) -> Optional[str]:
    ident = (identifier or "").strip().lower()
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE lower(slug) = ? OR lower(email) = ?", (ident, ident))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    raw_token, token_hash, expires_at = generate_recovery_token()
    cur.execute(
        "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (row["id"], token_hash, expires_at, _now_iso())
    )
    conn.commit()
    conn.close()
    record_audit_log(row["id"], row["id"], "password_reset_requested", "", db_path=db_path)
    return raw_token


def complete_password_reset(raw_token: str, new_password: str, db_path: str = DB_PATH) -> bool:
    thash = hash_token(raw_token)
    now = _now_iso()
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, user_id FROM password_reset_tokens
        WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?
    """, (thash, now))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False

    pw_hash = hash_password(new_password)
    cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, row["user_id"]))
    cur.execute("UPDATE password_reset_tokens SET used_at = ? WHERE id = ?", (now, row["id"]))
    conn.commit()
    conn.close()
    record_audit_log(row["user_id"], row["user_id"], "password_reset_completed", "", db_path=db_path)
    return True


def change_user_password(acting_user_id: int, target_user_id: int, new_password: str, db_path: str = DB_PATH) -> bool:
    if acting_user_id != target_user_id:
        raise AccessDeniedError("Only the account owner can directly change their password.")
    pw_hash = hash_password(new_password)
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, target_user_id))
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    record_audit_log(acting_user_id, target_user_id, "password_changed", "", db_path=db_path)
    return ok


# =============================================================================
# PROFILE, VERIFICATION & DOCUMENT VAULT REPOSITORY
# =============================================================================

def get_user_profile(
    acting_user_id: int,
    owner_user_id: int,
    allow_granted_admin: bool = True,
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    assert_tenant_access(acting_user_id, owner_user_id, required_scope="profile_assist", allow_granted_admin=allow_granted_admin, db_path=db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT profile_json FROM user_profiles WHERE user_id = ?", (owner_user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return {}
    return json.loads(row["profile_json"])


def save_user_profile(
    acting_user_id: int,
    owner_user_id: int,
    profile_data: Dict[str, Any],
    mark_verified: Optional[bool] = None,
    allow_granted_admin: bool = True,
    db_path: str = DB_PATH
) -> None:
    assert_tenant_access(acting_user_id, owner_user_id, required_scope="profile_assist", allow_granted_admin=allow_granted_admin, db_path=db_path)
    now = _now_iso()
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO user_profiles (user_id, profile_json, updated_at) VALUES (?, ?, ?)",
        (owner_user_id, json.dumps(profile_data, ensure_ascii=False), now)
    )
    new_email = (profile_data.get("personal", {}).get("email") or "").strip()
    if new_email and "@" in new_email and not new_email.endswith(".local"):
        try:
            cur.execute("UPDATE users SET email = ? WHERE id = ?", (new_email, owner_user_id))
        except sqlite3.IntegrityError:
            pass

    if mark_verified is not None:
        # Only the actual account owner can mark their own profile verified!
        if acting_user_id != owner_user_id and mark_verified:
            conn.close()
            raise AccessDeniedError("Only the account owner can confirm and verify their own professional history.")
        cur.execute(
            "UPDATE users SET profile_verified = ?, account_status = ? WHERE id = ?",
            (1 if mark_verified else 0, "active" if mark_verified else "pending_verification", owner_user_id)
        )
    conn.commit()
    conn.close()
    record_audit_log(acting_user_id, owner_user_id, "profile_updated", f"verified={mark_verified}", db_path=db_path)


def register_user_document(
    acting_user_id: int,
    owner_user_id: int,
    doc_kind: str,
    version_label: str,
    filename: str,
    storage_key: str,
    extracted_text: str = "",
    vacancy_id: Optional[int] = None,
    db_path: str = DB_PATH
) -> int:
    if acting_user_id != owner_user_id:
        raise AccessDeniedError("Cross-user document creation is forbidden.")
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_documents (user_id, vacancy_id, doc_kind, version_label, filename, storage_key, extracted_text, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (owner_user_id, vacancy_id, doc_kind, version_label, filename, storage_key, extracted_text, _now_iso()))
    doc_id = cur.lastrowid
    conn.commit()
    conn.close()
    return doc_id


def list_user_documents(
    acting_user_id: int,
    owner_user_id: int,
    doc_kind: Optional[str] = None,
    db_path: str = DB_PATH
) -> List[Dict[str, Any]]:
    assert_tenant_access(acting_user_id, owner_user_id, required_scope="documents_view", allow_granted_admin=True, db_path=db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()
    if doc_kind:
        cur.execute(
            "SELECT id, user_id, vacancy_id, doc_kind, version_label, filename, created_at FROM user_documents WHERE user_id = ? AND doc_kind = ? ORDER BY id DESC",
            (owner_user_id, doc_kind)
        )
    else:
        cur.execute(
            "SELECT id, user_id, vacancy_id, doc_kind, version_label, filename, created_at FROM user_documents WHERE user_id = ? ORDER BY id DESC",
            (owner_user_id,)
        )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# =============================================================================
# USER CUSTOM TARGET JOB SOURCES & CAREER BOARDS
# =============================================================================

def list_user_custom_sources(
    acting_user_id: int,
    owner_user_id: int,
    db_path: str = DB_PATH
) -> List[Dict[str, Any]]:
    assert_tenant_access(acting_user_id, owner_user_id, required_scope="profile_assist", allow_granted_admin=True, db_path=db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_custom_sources WHERE user_id = ? ORDER BY id DESC", (owner_user_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def add_user_custom_source(
    acting_user_id: int,
    owner_user_id: int,
    source_name: str,
    source_type: str = "company_career_page",
    target_url: str = "",
    query_keywords: str = "",
    target_location: str = "",
    db_path: str = DB_PATH
) -> int:
    assert_tenant_access(acting_user_id, owner_user_id, required_scope="profile_assist", allow_granted_admin=False, db_path=db_path)
    now = _now_iso()
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_custom_sources (
            user_id, source_name, source_type, target_url, query_keywords, target_location, is_active, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
    """, (owner_user_id, source_name.strip(), source_type, target_url.strip(), query_keywords.strip(), target_location.strip(), now))
    sid = cur.lastrowid
    conn.commit()
    conn.close()
    record_audit_log(acting_user_id, owner_user_id, "add_custom_source", f"Added source '{source_name}' ({source_type})", db_path=db_path)
    return sid


def delete_user_custom_source(
    acting_user_id: int,
    owner_user_id: int,
    source_id: int,
    db_path: str = DB_PATH
) -> bool:
    assert_tenant_access(acting_user_id, owner_user_id, required_scope="profile_assist", allow_granted_admin=False, db_path=db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM user_custom_sources WHERE id = ? AND user_id = ?", (source_id, owner_user_id))
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    if ok:
        record_audit_log(acting_user_id, owner_user_id, "delete_custom_source", f"Deleted source #{source_id}", db_path=db_path)
    return ok


def update_user_custom_source_scanned(source_id: int, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    conn.execute("UPDATE user_custom_sources SET last_scanned_at = ? WHERE id = ?", (_now_iso(), source_id))
    conn.commit()
    conn.close()


def get_user_document(
    acting_user_id: int,
    owner_user_id: int,
    doc_id: int,
    db_path: str = DB_PATH
) -> Optional[Dict[str, Any]]:
    is_granted = assert_tenant_access(acting_user_id, owner_user_id, required_scope="documents_view", allow_granted_admin=True, db_path=db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_documents WHERE id = ? AND user_id = ?", (doc_id, owner_user_id))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["_via_admin_grant"] = is_granted
    return d


# =============================================================================
# VACANCIES & STRICTLY ISOLATED USER PIPELINE REPOSITORY
# =============================================================================

def make_canonical_hash(company: str, title: str, location: str) -> str:
    raw = f"{(company or '').strip().lower()}_{(title or '').strip().lower()}_{(location or '').strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def upsert_vacancy(vacancy_data: Dict[str, Any], db_path: str = DB_PATH) -> Tuple[int, bool]:
    """Inserts or updates a normalized vacancy in the shared catalog. Returns (vacancy_id, is_new)."""
    now = _now_iso()
    chash = vacancy_data.get("canonical_hash") or vacancy_data.get("dedup_hash") or make_canonical_hash(
        vacancy_data.get("company", ""),
        vacancy_data.get("title", ""),
        vacancy_data.get("location", "")
    )
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id FROM vacancies WHERE canonical_hash = ?", (chash,))
    existing = cur.fetchone()
    if existing:
        vid = existing["id"]
        cur.execute("""
            UPDATE vacancies SET
                salary = CASE WHEN ? != '' THEN ? ELSE salary END,
                description = CASE WHEN length(?) > length(description) THEN ? ELSE description END,
                is_expired = COALESCE(?, is_expired),
                updated_at = ?
            WHERE id = ?
        """, (
            vacancy_data.get("salary", ""), vacancy_data.get("salary", ""),
            vacancy_data.get("description", ""), vacancy_data.get("description", ""),
            vacancy_data.get("is_expired"),
            now, vid
        ))
        conn.commit()
        conn.close()
        return vid, False

    cur.execute("""
        INSERT INTO vacancies (
            canonical_hash, title, company, location, country, remote_type,
            remote_country_restrictions, salary, contract_type, seniority, category,
            required_languages, required_experience, required_qualifications,
            work_auth_requirements, relocation_assistance, job_url, source,
            description, published_at, deadline, quality_flags_json, is_expired,
            discovered_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chash,
        vacancy_data.get("title", "Untitled Position"),
        vacancy_data.get("company", "Unknown Company"),
        vacancy_data.get("location", "Not specified"),
        vacancy_data.get("country", ""),
        vacancy_data.get("remote_type", "On-site"),
        vacancy_data.get("remote_country_restrictions", ""),
        vacancy_data.get("salary", ""),
        vacancy_data.get("contract_type", ""),
        vacancy_data.get("seniority", ""),
        vacancy_data.get("category", ""),
        vacancy_data.get("required_languages", ""),
        vacancy_data.get("required_experience", ""),
        vacancy_data.get("required_qualifications", ""),
        vacancy_data.get("work_auth_requirements", ""),
        1 if vacancy_data.get("relocation_assistance") else 0,
        vacancy_data.get("job_url", ""),
        vacancy_data.get("source", "Manual"),
        vacancy_data.get("description", ""),
        vacancy_data.get("published_at") or vacancy_data.get("date_discovered") or now[:10],
        vacancy_data.get("deadline", ""),
        json.dumps(vacancy_data.get("quality_flags", {})),
        1 if vacancy_data.get("is_expired") else 0,
        now,
        now,
    ))
    vid = cur.lastrowid
    conn.commit()
    conn.close()
    return vid, True


def save_user_job_match(
    user_id: int,
    vacancy_id: int,
    score_data: Dict[str, Any],
    gap_analysis: Optional[Dict[str, Any]] = None,
    db_path: str = DB_PATH
) -> Tuple[int, bool]:
    """Saves or refreshes a user's personal match evaluation without overwriting their manual pipeline status."""
    now = _now_iso()
    score = int(score_data.get("score", 0))
    breakdown_str = json.dumps(score_data.get("breakdown", {}))
    rationale = score_data.get("rationale", "")
    flags = score_data.get("flags", {})
    gap_str = json.dumps(gap_analysis or {})

    priority = "exclude" if flags.get("disqualified") else ("high" if score >= 80 else ("normal" if score >= 60 else "low"))
    initial_status = "archived" if flags.get("disqualified") else "discovered"
    is_practical = 1 if flags.get("is_practical_role") else 0

    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, status FROM user_job_matches WHERE user_id = ? AND vacancy_id = ?", (user_id, vacancy_id))
    row = cur.fetchone()
    if row:
        mid = row["id"]
        cur.execute("""
            UPDATE user_job_matches SET
                match_score = ?,
                score_breakdown_json = ?,
                score_rationale = ?,
                gap_analysis_json = CASE WHEN ? != '{}' THEN ? ELSE gap_analysis_json END,
                priority = ?,
                is_practical_role = ?,
                updated_at = ?
            WHERE id = ? AND user_id = ?
        """, (score, breakdown_str, rationale, gap_str, gap_str, priority, is_practical, now, mid, user_id))
        conn.commit()
        conn.close()
        return mid, False

    cur.execute("""
        INSERT INTO user_job_matches (
            user_id, vacancy_id, match_score, score_breakdown_json, score_rationale,
            gap_analysis_json, status, priority, is_practical_role, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, vacancy_id, score, breakdown_str, rationale, gap_str, initial_status, priority, is_practical, now, now))
    mid = cur.lastrowid
    conn.commit()
    conn.close()
    return mid, True


def list_user_matches(
    acting_user_id: int,
    owner_user_id: int,
    status: Optional[str] = None,
    min_score: int = 0,
    location_filter: Optional[str] = None,
    country_filter: Optional[str] = None,
    remote_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    seniority_filter: Optional[str] = None,
    company_filter: Optional[str] = None,
    salary_filter: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    allow_granted_admin: bool = True,
    db_path: str = DB_PATH
) -> List[Dict[str, Any]]:
    assert_tenant_access(acting_user_id, owner_user_id, required_scope="matches_view", allow_granted_admin=allow_granted_admin, db_path=db_path)

    conn = get_connection(db_path)
    cur = conn.cursor()

    query = """
        SELECT
            m.id as match_id,
            m.user_id,
            m.vacancy_id,
            m.match_score,
            m.score_breakdown_json,
            m.score_rationale,
            m.status,
            m.priority,
            m.is_practical_role,
            m.cv_document_id,
            m.cv_version_label,
            m.cover_letter_document_id,
            m.follow_up_date,
            m.interview_info,
            m.private_notes,
            m.updated_at,
            v.title,
            v.company,
            v.location,
            v.country,
            v.remote_type,
            v.remote_country_restrictions,
            v.salary,
            v.contract_type,
            v.seniority,
            v.category,
            v.required_languages,
            v.relocation_assistance,
            v.job_url,
            v.source,
            v.published_at as date_discovered,
            v.deadline
        FROM user_job_matches m
        JOIN vacancies v ON v.id = m.vacancy_id
        WHERE m.user_id = ? AND v.is_expired = 0
    """
    params: List[Any] = [owner_user_id]

    if status and status != "all":
        query += " AND m.status = ?"
        params.append(status)
    else:
        query += " AND m.status != 'archived'"

    if min_score > 0:
        query += " AND m.match_score >= ?"
        params.append(min_score)

    if location_filter:
        query += " AND (v.location LIKE ? OR v.country LIKE ? OR v.remote_type LIKE ?)"
        pat = f"%{location_filter}%"
        params.extend([pat, pat, pat])

    if country_filter and country_filter != "all":
        query += " AND (lower(v.country) LIKE ? OR lower(v.location) LIKE ?)"
        pat = f"%{country_filter.lower()}%"
        params.extend([pat, pat])

    if remote_filter and remote_filter != "all":
        query += " AND lower(v.remote_type) LIKE ?"
        params.append(f"%{remote_filter.lower()}%")

    if category_filter and category_filter != "all":
        if category_filter == "practical":
            query += " AND m.is_practical_role = 1"
        elif category_filter == "office_ops":
            query += " AND m.is_practical_role = 0"
        else:
            query += " AND lower(v.category) LIKE ?"
            params.append(f"%{category_filter.lower()}%")

    if seniority_filter and seniority_filter != "all":
        query += " AND lower(v.seniority) LIKE ?"
        params.append(f"%{seniority_filter.lower()}%")

    if company_filter:
        query += " AND lower(v.company) LIKE ?"
        params.append(f"%{company_filter.lower()}%")

    if salary_filter:
        query += " AND v.salary != '' AND lower(v.salary) LIKE ?"
        params.append(f"%{salary_filter.lower()}%")

    query += " ORDER BY m.match_score DESC, m.id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cur.execute(query, params)
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        d["id"] = d["match_id"]  # Compatibility alias for UI/CLI
        rows.append(d)
    conn.close()
    return rows


def get_user_match_detail(
    acting_user_id: int,
    owner_user_id: int,
    match_id: int,
    allow_granted_admin: bool = True,
    db_path: str = DB_PATH
) -> Optional[Dict[str, Any]]:
    assert_tenant_access(acting_user_id, owner_user_id, required_scope="matches_view", allow_granted_admin=allow_granted_admin, db_path=db_path)

    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            m.*,
            v.title, v.company, v.location, v.country, v.remote_type,
            v.remote_country_restrictions, v.salary, v.contract_type,
            v.seniority, v.category, v.required_languages, v.required_experience,
            v.required_qualifications, v.work_auth_requirements, v.relocation_assistance,
            v.job_url, v.source, v.description, v.published_at as date_discovered,
            v.deadline, v.quality_flags_json
        FROM user_job_matches m
        JOIN vacancies v ON v.id = m.vacancy_id
        WHERE m.id = ? AND m.user_id = ?
    """, (match_id, owner_user_id))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_user_match(
    acting_user_id: int,
    owner_user_id: int,
    match_id: int,
    status: Optional[str] = None,
    private_notes: Optional[str] = None,
    cv_document_id: Optional[int] = None,
    cv_version_label: Optional[str] = None,
    cover_letter_document_id: Optional[int] = None,
    app_answers_json: Optional[str] = None,
    interview_prep_json: Optional[str] = None,
    follow_up_date: Optional[str] = None,
    interview_info: Optional[str] = None,
    db_path: str = DB_PATH
) -> bool:
    assert_tenant_access(acting_user_id, owner_user_id, required_scope="matches_view", allow_granted_admin=False, db_path=db_path)

    updates = ["updated_at = ?"]
    params: List[Any] = [_now_iso()]

    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if private_notes is not None:
        updates.append("private_notes = ?")
        params.append(private_notes)
    if cv_document_id is not None:
        updates.append("cv_document_id = ?")
        params.append(cv_document_id)
    if cv_version_label is not None:
        updates.append("cv_version_label = ?")
        params.append(cv_version_label)
    if cover_letter_document_id is not None:
        updates.append("cover_letter_document_id = ?")
        params.append(cover_letter_document_id)
    if app_answers_json is not None:
        updates.append("app_answers_json = ?")
        params.append(app_answers_json)
    if interview_prep_json is not None:
        updates.append("interview_prep_json = ?")
        params.append(interview_prep_json)
    if follow_up_date is not None:
        updates.append("follow_up_date = ?")
        params.append(follow_up_date)
    if interview_info is not None:
        updates.append("interview_info = ?")
        params.append(interview_info)

    params.extend([match_id, owner_user_id])
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(f"UPDATE user_job_matches SET {', '.join(updates)} WHERE id = ? AND user_id = ?", params)
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def get_user_dashboard_stats(
    acting_user_id: int,
    owner_user_id: int,
    allow_granted_admin: bool = True,
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    assert_tenant_access(acting_user_id, owner_user_id, required_scope="matches_view", allow_granted_admin=allow_granted_admin, db_path=db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()

    stats: Dict[str, Any] = {}
    cur.execute("SELECT COUNT(*) as total FROM user_job_matches WHERE user_id = ? AND status != 'archived'", (owner_user_id,))
    stats["total_discovered"] = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) as high_match FROM user_job_matches WHERE user_id = ? AND match_score >= 75 AND status != 'archived'", (owner_user_id,))
    stats["high_match_count"] = cur.fetchone()["high_match"]

    for st in ["discovered", "saved", "awaiting_approval", "ready_to_apply", "applied", "interviewing", "rejected"]:
        cur.execute("SELECT COUNT(*) as cnt FROM user_job_matches WHERE user_id = ? AND status = ?", (owner_user_id, st))
        stats[f"status_{st}"] = cur.fetchone()["cnt"]

    cur.execute("""
        SELECT COUNT(*) as cnt FROM user_job_matches
        WHERE user_id = ? AND follow_up_date != '' AND follow_up_date <= date('now') AND status = 'applied'
    """, (owner_user_id,))
    stats["follow_ups_due"] = cur.fetchone()["cnt"]
    conn.close()
    return stats


# =============================================================================
# PRIVACY-PRESERVING ADMINISTRATOR OVERVIEW REPOSITORY
# =============================================================================

def get_admin_system_overview(acting_admin_id: int, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Returns system health, scraper statistics, error logs, and sanitized high-level account counts.
    NEVER exposes private CVs, personal notes, uploaded files, or application correspondence!
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT is_admin FROM users WHERE id = ?", (acting_admin_id,))
    admin_row = cur.fetchone()
    if not admin_row or not admin_row["is_admin"]:
        conn.close()
        raise AccessDeniedError("Administrator privileges required.")

    cur.execute("SELECT COUNT(*) as cnt FROM vacancies WHERE is_expired = 0")
    active_vacancies = cur.fetchone()["cnt"]

    cur.execute("""
        SELECT u.id, u.slug, u.full_name, u.email, u.is_admin, u.account_status, u.profile_verified, u.last_login_at,
               (SELECT COUNT(*) FROM user_job_matches m WHERE m.user_id = u.id AND m.status != 'archived') as total_matches,
               (SELECT COUNT(*) FROM user_job_matches m WHERE m.user_id = u.id AND m.match_score >= 75 AND m.status != 'archived') as strong_matches,
               (SELECT COUNT(*) FROM user_job_matches m WHERE m.user_id = u.id AND m.status = 'applied') as submitted_count,
               (SELECT COUNT(*) FROM user_job_matches m WHERE m.user_id = u.id AND m.status = 'interviewing') as interview_count
        FROM users u
        ORDER BY u.id ASC
    """)
    accounts = []
    now = _now_iso()
    for r in cur.fetchall():
        acc = dict(r)
        cur.execute("""
            SELECT scope, expires_at FROM admin_access_grants
            WHERE owner_user_id = ? AND grantee_admin_id = ? AND revoked_at IS NULL AND expires_at > ?
        """, (acc["id"], acting_admin_id, now))
        acc["active_assistance_grants"] = [dict(g) for g in cur.fetchall()]
        accounts.append(acc)

    cur.execute("SELECT * FROM scan_logs ORDER BY id DESC LIMIT 15")
    recent_scans = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM error_logs ORDER BY id DESC LIMIT 15")
    recent_errors = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM scheduler_logs ORDER BY id DESC LIMIT 15")
    recent_schedules = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 20")
    recent_audits = [dict(r) for r in cur.fetchall()]

    conn.close()
    return {
        "system_status": "healthy",
        "active_shared_vacancies": active_vacancies,
        "accounts": accounts,
        "recent_scans": recent_scans,
        "recent_errors": recent_errors,
        "recent_schedules": recent_schedules,
        "recent_audits": recent_audits,
    }


def log_scan(source: str, query: str, found: int, new: int, status: str = "success", error: str = "", db_path: str = DB_PATH):
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO scan_logs (source, query, found_count, new_count, scanned_at, status, error_message) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (source, query, found, new, _now_iso(), status, error)
    )
    conn.commit()
    conn.close()


def log_scheduler_run(user_id: Optional[int], task_name: str, status: str, summary: str, db_path: str = DB_PATH):
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO scheduler_logs (user_id, task_name, status, summary, executed_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, task_name, status, summary, _now_iso())
    )
    conn.commit()
    conn.close()


# =============================================================================
# BACKWARD-COMPATIBLE HELPERS FOR JUSTIN'S LEGACY SINGLE-USER CLI CALLS
# =============================================================================

def _justin_id(db_path: str = DB_PATH) -> int:
    u = get_user_by_slug("justin", db_path=db_path)
    if not u:
        init_db(db_path=db_path)
        u = get_user_by_slug("justin", db_path=db_path)
    return u["id"]


def list_jobs(
    status: Optional[str] = None,
    min_score: Optional[int] = None,
    location_filter: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    user_slug: str = "justin",
    db_path: str = DB_PATH
) -> List[Dict[str, Any]]:
    u = get_user_by_slug(user_slug, db_path=db_path)
    if not u:
        return []
    uid = u["id"]
    return list_user_matches(
        acting_user_id=uid,
        owner_user_id=uid,
        status=status,
        min_score=min_score or 0,
        location_filter=location_filter,
        category_filter=category,
        limit=limit,
        offset=offset,
        db_path=db_path
    )


def get_job_by_id(job_id: int, user_slug: str = "justin", db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    u = get_user_by_slug(user_slug, db_path=db_path)
    if not u:
        return None
    return get_user_match_detail(u["id"], u["id"], job_id, db_path=db_path)


def update_job_status(
    job_id: int,
    status: str,
    notes: Optional[str] = None,
    cv_version: Optional[str] = None,
    follow_up_date: Optional[str] = None,
    interview_info: Optional[str] = None,
    user_slug: str = "justin",
    db_path: str = DB_PATH
) -> bool:
    u = get_user_by_slug(user_slug, db_path=db_path)
    if not u:
        return False
    return update_user_match(
        acting_user_id=u["id"],
        owner_user_id=u["id"],
        match_id=job_id,
        status=status,
        private_notes=notes,
        cv_version_label=cv_version,
        follow_up_date=follow_up_date,
        interview_info=interview_info,
        db_path=db_path
    )


def get_dashboard_stats(user_slug: str = "justin", db_path: str = DB_PATH) -> Dict[str, Any]:
    u = get_user_by_slug(user_slug, db_path=db_path)
    if not u:
        return {}
    return get_user_dashboard_stats(u["id"], u["id"], db_path=db_path)


if __name__ == "__main__":
    init_db()
    print("Multi-tenant database initialized & legacy jobs migrated cleanly at:", DB_PATH)
