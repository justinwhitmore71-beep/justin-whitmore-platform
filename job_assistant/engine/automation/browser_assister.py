"""
Multi-User Isolated Browser Automation & Application Draft Assister.

STRICT SECURITY & SAFETY GUARANTEES (PART 8):
1. NEVER submit an application without the relevant user's explicit manual action (AUTOSUBMIT_FORBIDDEN = True).
2. NEVER accept contractual terms, create commitments, or expose sensitive PII automatically.
3. Uses strictly isolated browser profile directories per user (`user_<id>_session`) — cookies,
   localStorage, and authentication sessions are NEVER shared across Justin, Işıl, and Lindsey.
4. Stops immediately and requests human assistance on CAPTCHA, Cloudflare, 2FA, or identity checks.
"""

import json
import os
import re
from typing import Dict, Any, Optional
import requests
from bs4 import BeautifulSoup

from job_assistant.engine.security import (
    AccessDeniedError,
    VaultStorage,
    get_isolated_browser_profile_dir,
)
from job_assistant.engine.db import (
    get_user_by_id,
    get_user_profile,
    get_user_match_detail,
    get_user_document,
)

AUTOSUBMIT_FORBIDDEN = True
FORBIDDEN_SUBMIT_SELECTORS = [
    "button[type='submit']",
    "input[type='submit']",
    "button:has-text('Submit Application')",
    "button:has-text('Send Application')",
    "button:has-text('Agree and Submit')",
]


class SafetyInterventionRequired(Exception):
    """Raised when CAPTCHA, identity verification, contractual consent, or final submission requires the human user."""
    pass


def assert_action_safe(action_name: str):
    lowered = (action_name or "").lower()
    if AUTOSUBMIT_FORBIDDEN and any(w in lowered for w in ["submit", "accept_terms", "sign_contract", "confirm_apply"]):
        raise SafetyInterventionRequired(
            "Blocked by Safety Guardrail: Automated submission or contractual agreement is strictly prohibited. "
            "Draft has been prepared for explicit user review and manual submission."
        )


def check_for_captcha_or_security(html_content: str) -> Optional[str]:
    """Detects CAPTCHA, Cloudflare Turnstile, or identity verification walls."""
    html_lower = (html_content or "").lower()
    checks = {
        "reCAPTCHA": ["g-recaptcha", "recaptcha/api.js"],
        "hCaptcha": ["hcaptcha.com", "h-captcha"],
        "Cloudflare Challenge": ["cf-turnstile", "challenge-running", "just a moment..."],
        "Identity / 2FA Verification": ["two-factor authentication", "verify your identity", "enter verification code"],
    }
    for name, markers in checks.items():
        if any(m in html_lower for m in markers):
            return name
    return None


def fetch_and_inspect_job_page(url: str, timeout: int = 12) -> Dict[str, Any]:
    """Reads a live vacancy page respectfully, checks for CAPTCHA/blocks, and extracts description & ATS type."""
    if not url or not url.startswith(("http://", "https://")):
        return {"reachable": False, "error": "Invalid URL"}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        challenge = check_for_captcha_or_security(resp.text)
        if challenge:
            return {
                "reachable": False,
                "manual_intervention_required": True,
                "reason": f"{challenge} detected — manual user browser review required.",
                "status_code": resp.status_code,
            }

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()

        ats_platform = "Direct / Custom Portal"
        for ats_key, ats_label in [
            ("greenhouse.io", "Greenhouse"),
            ("lever.co", "Lever"),
            ("myworkdayjobs.com", "Workday"),
            ("smartrecruiters.com", "SmartRecruiters"),
            ("ashbyhq.com", "Ashby"),
            ("francetravail.fr", "France Travail"),
            ("linkedin.com", "LinkedIn"),
        ]:
            if ats_key in url.lower() or ats_key in resp.text.lower():
                ats_platform = ats_label
                break

        return {
            "reachable": resp.status_code == 200,
            "manual_intervention_required": False,
            "ats_platform": ats_platform,
            "status_code": resp.status_code,
            "extracted_text_preview": text[:1500],
        }
    except Exception as e:
        return {"reachable": False, "error": str(e)}


def build_isolated_user_automation_draft(
    acting_user_id: int,
    owner_user_id: int,
    match_id: int,
    inspect_live_url: bool = False,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Builds a strictly user-scoped browser pre-fill & draft configuration:
    - Enforces acting_user_id == owner_user_id (zero cross-user session or CV sharing).
    - Allocates an isolated browser profile directory (`user_<id>_session`).
    - Maps ONLY that specific user's verified contact, citizenship, language, and CV version.
    """
    if acting_user_id != owner_user_id:
        raise AccessDeniedError("Cross-user browser automation access is strictly prohibited.")

    db_kwargs = {"db_path": db_path} if db_path else {}
    user = get_user_by_id(owner_user_id, **db_kwargs)
    if not user:
        raise ValueError("User not found.")

    profile = get_user_profile(acting_user_id, owner_user_id, allow_granted_admin=False, **db_kwargs)
    match_row = get_user_match_detail(acting_user_id, owner_user_id, match_id, allow_granted_admin=False, **db_kwargs)
    if not match_row:
        raise ValueError("Match not found in user's workspace.")

    isolated_session_dir = get_isolated_browser_profile_dir(acting_user_id, owner_user_id)

    cv_info = None
    if match_row.get("cv_document_id"):
        doc = get_user_document(acting_user_id, owner_user_id, match_row["cv_document_id"], **db_kwargs)
        if doc:
            vault = VaultStorage()
            cv_info = {
                "document_id": doc["id"],
                "version_label": doc["version_label"],
                "filename": doc["filename"],
                "isolated_vault_path": vault.resolve_local_path_for_upload(acting_user_id, owner_user_id, doc["storage_key"])
            }

    personal = profile.get("personal", {})
    work_auth = profile.get("work_authorization", {})
    citizenships = profile.get("citizenships", [])
    langs = profile.get("languages", [])
    full_name = personal.get("full_name", user["full_name"])
    parts = full_name.split()
    first_name = parts[0] if parts else full_name
    last_name = parts[-1] if len(parts) > 1 else ""

    live_page = fetch_and_inspect_job_page(match_row.get("job_url", "")) if inspect_live_url else None

    return {
        "user_id": owner_user_id,
        "user_slug": user["slug"],
        "isolated_browser_session_dir": isolated_session_dir,
        "cookies_isolated": True,
        "autosubmit_allowed": not AUTOSUBMIT_FORBIDDEN,
        "requires_explicit_user_approval": True,
        "vacancy": {
            "match_id": match_id,
            "title": match_row.get("title"),
            "company": match_row.get("company"),
            "job_url": match_row.get("job_url"),
        },
        "cv_to_upload": cv_info,
        "form_prefill_fields": {
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "email": personal.get("email") or "[Requires User Verification]",
            "phone": personal.get("phone") or "[Requires User Verification]",
            "current_location": personal.get("current_location", ""),
            "citizenships": citizenships,
            "eu_work_authorized": bool(work_auth.get("eu_eea_free_movement")) if isinstance(work_auth, dict) else True,
            "requires_visa_sponsorship": bool(work_auth.get("requires_eu_sponsorship")) if isinstance(work_auth, dict) else False,
            "languages": [f"{l['language']} ({l['level']})" for l in langs if isinstance(l, dict) and "none" not in l.get("level", "").lower()],
        },
        "live_page_check": live_page,
        "safety_notice": (
            "Application draft prepared in isolated user session. The agent will NEVER click Submit, "
            "accept terms, or bypass CAPTCHA/identity checks without your explicit manual action."
        )
    }


def generate_form_fill_guide(job_dict: Dict[str, Any], profile_dict: Dict[str, Any], cv_path: Optional[str] = None) -> Dict[str, Any]:
    """Backward-compatible helper."""
    p = profile_dict.get("personal", {})
    return {
        "job_title": job_dict.get("title"),
        "company": job_dict.get("company"),
        "job_url": job_dict.get("job_url"),
        "recommended_cv_file": cv_path or "Tailored CV",
        "prefill_data": {
            "Full Name": p.get("full_name", ""),
            "Email": p.get("email", ""),
            "Phone": p.get("phone", ""),
            "Location": p.get("current_location", ""),
        },
        "safety_status": {
            "auto_submit_allowed": False,
            "requires_user_final_click": True,
        }
    }
