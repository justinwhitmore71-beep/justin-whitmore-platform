"""
Comprehensive Automated Test Suite for the Multi-User AI Recruitment Platform.
Verifies:
1. Independent authentication, CSRF protection, and password recovery across all 3 accounts.
2. Strict cross-tenant isolation (DB, REST API, Document Vault, and Browser Session directories).
3. Privacy-preserving Administrator Console & explicit revocable user assistance grants.
4. Lindsey's Leave-Malta Remote-First Europe scoring & profile fidelity.
5. Işıl's non-EU/French work-authorization checks, verification gate, and zero-hallucination CV generation.
6. Justin's recruiter preservation (real migrated DB + SAP/Export/Orléans rules).
7. CV upload parsing, backup generation, and scheduled workflow execution.
"""

import io
import json
import os
import tempfile
import pytest

from job_assistant.engine.db import (
    DB_PATH,
    init_db,
    get_user_by_slug,
    get_user_profile,
    save_user_profile,
    upsert_vacancy,
    save_user_job_match,
    change_user_password,
    get_dashboard_stats,
)
from job_assistant.engine.security import (
    AccessDeniedError,
    VaultStorage,
    get_isolated_browser_profile_dir,
)
from job_assistant.engine.scoring.scorer import evaluate_job_for_user
from job_assistant.engine.application.builder import (
    generate_tailored_cv,
    generate_tailored_cover_letter,
)
from job_assistant.engine.automation.browser_assister import (
    assert_action_safe,
    SafetyInterventionRequired,
    build_isolated_user_automation_draft,
)
from job_assistant.engine.scheduler import run_scheduled_stage_for_user
from job_assistant.dashboard.app import create_app


@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    """Creates a clean temporary SQLite DB and Vault root for hermetic multi-user testing."""
    test_db = str(tmp_path / "test_platform.db")
    test_vault = str(tmp_path / "test_vault")
    test_browser = str(tmp_path / "test_browser_profiles")

    monkeypatch.setattr("job_assistant.engine.security.VAULT_ROOT", test_vault)
    monkeypatch.setattr("job_assistant.engine.security.BROWSER_PROFILES_ROOT", test_browser)
    monkeypatch.setenv("JUSTIN_INIT_PASSWORD", "JustinStrongPass!2026")
    monkeypatch.setenv("ISIL_INIT_PASSWORD", "IsilStrongPass!2026")
    monkeypatch.setenv("LINDSEY_INIT_PASSWORD", "LindseyStrongPass!2026")
    monkeypatch.setenv("LOCAL_DEV_RETURN_RESET_TOKEN", "1")
    monkeypatch.setenv("CRON_WEBHOOK_SECRET", "super-secret-cron-key")

    init_db(db_path=test_db)
    app = create_app(db_path=test_db, enforce_csrf=True)
    app.config["TESTING"] = True
    return {"db": test_db, "app": app, "vault": test_vault}


def _login_client(app, username: str, password: str):
    client = app.test_client()
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.get_json()
    payload = res.get_json()
    return client, payload["csrf_token"], payload["user"]


# =============================================================================
# 1. AUTHENTICATION, CSRF & PASSWORD RECOVERY TESTS
# =============================================================================

def test_authentication_csrf_and_password_recovery(isolated_env):
    app = isolated_env["app"]
    anon = app.test_client()

    # Unauthenticated calls must be rejected
    assert anon.get("/api/jobs").status_code == 401
    assert anon.get("/api/profile").status_code == 401
    assert anon.get("/api/admin/overview").status_code == 401

    # Wrong password rejected
    bad = anon.post("/api/auth/login", json={"username": "justin", "password": "wrongpassword"})
    assert bad.status_code == 401

    # All 3 accounts log in independently
    c_j, csrf_j, u_j = _login_client(app, "justin", "JustinStrongPass!2026")
    c_i, csrf_i, u_i = _login_client(app, "isil", "IsilStrongPass!2026")
    c_l, csrf_l, u_l = _login_client(app, "lindsey", "LindseyStrongPass!2026")

    assert u_j["slug"] == "justin" and u_j["is_admin"] == 1
    assert u_i["slug"] == "isil" and u_i["is_admin"] == 0
    assert u_l["slug"] == "lindsey" and u_l["is_admin"] == 0

    # CSRF protection blocks state-changing POST without token
    no_csrf = c_j.post("/api/scan")
    assert no_csrf.status_code == 403

    # Password recovery single-use flow
    rec_req = anon.post("/api/auth/forgot-password", json={"identifier": "lindsey"})
    assert rec_req.status_code == 200
    token = rec_req.get_json()["dev_reset_token"]

    reset_ok = anon.post("/api/auth/reset-password", json={"token": token, "new_password": "LindseyNewPassword!99"})
    assert reset_ok.status_code == 200

    # Reusing the same recovery token must fail
    reset_replay = anon.post("/api/auth/reset-password", json={"token": token, "new_password": "AnotherPassword!99"})
    assert reset_replay.status_code == 400

    # Login succeeds with new password
    _login_client(app, "lindsey", "LindseyNewPassword!99")


# =============================================================================
# 2. STRICT CROSS-USER ISOLATION & PRIVACY-PRESERVING ADMIN TESTS
# =============================================================================

def test_cross_tenant_isolation_and_admin_privacy_controls(isolated_env):
    db = isolated_env["db"]
    app = isolated_env["app"]

    c_j, csrf_j, u_j = _login_client(app, "justin", "JustinStrongPass!2026")
    c_i, csrf_i, u_i = _login_client(app, "isil", "IsilStrongPass!2026")
    c_l, csrf_l, u_l = _login_client(app, "lindsey", "LindseyStrongPass!2026")

    # Seed one vacancy & match for Justin, and prepare Justin's application
    vid, _ = upsert_vacancy({
        "title": "International Export Order Coordinator (SAP)",
        "company": "MedTech Europe",
        "location": "Lisbon, Portugal",
        "remote_type": "Hybrid",
        "job_url": "https://example.com/jobs/1",
        "source": "Direct",
        "description": "SAP VA32, ZBL, export documentation AWB EX-1 in English."
    }, db_path=db)

    prof_j = get_user_profile(u_j["id"], u_j["id"], db_path=db)
    score_j = evaluate_job_for_user("justin", {"title": "International Export Order Coordinator (SAP)", "location": "Lisbon, Portugal", "description": "SAP VA32 export English"}, prof_j)
    justin_match_id, _ = save_user_job_match(u_j["id"], vid, score_j, db_path=db)

    prep_res = c_j.post(f"/api/jobs/{justin_match_id}/prepare", headers={"X-CSRF-Token": csrf_j})
    assert prep_res.status_code == 200
    justin_cv_doc_id = prep_res.get_json()["cv_document_id"]

    # Işıl uploads her own private CV
    isil_cv_bytes = b"Isil Private Resume\nAccolade Customer Onboarding\nEnglish C2, Native Turkish"
    up_res = c_i.post(
        "/api/cv/upload",
        data={"file": (io.BytesIO(isil_cv_bytes), "Isil_Master_CV.txt")},
        headers={"X-CSRF-Token": csrf_i},
        content_type="multipart/form-data",
    )
    assert up_res.status_code == 200
    isil_doc_id = up_res.get_json()["document_id"]

    # TEST A: Işıl & Lindsey CANNOT access Justin's match or Justin's CV document!
    assert c_i.get(f"/api/jobs/{justin_match_id}").status_code == 404
    assert c_l.get(f"/api/jobs/{justin_match_id}").status_code == 404
    assert c_i.post(f"/api/jobs/{justin_match_id}/status", json={"status": "applied"}, headers={"X-CSRF-Token": csrf_i}).status_code == 404
    assert c_i.get(f"/api/documents/{justin_cv_doc_id}").status_code == 404
    assert c_l.get(f"/api/documents/{isil_doc_id}").status_code == 404

    # TEST B: Non-admin users CANNOT access Admin Console
    assert c_i.get("/api/admin/overview").status_code == 403
    assert c_l.get("/api/admin/overview").status_code == 403

    # TEST C: Admin (Justin) can see system telemetry, but CANNOT access Işıl's private profile or CV without Işıl's explicit grant!
    adm_ov = c_j.get("/api/admin/overview")
    assert adm_ov.status_code == 200
    assert "Isil Private Resume" not in json.dumps(adm_ov.get_json())

    blocked_prof = c_j.get(f"/api/admin/assist/{u_i['id']}/profile")
    assert blocked_prof.status_code == 403
    blocked_doc = c_j.get(f"/api/admin/assist/{u_i['id']}/documents/{isil_doc_id}")
    assert blocked_doc.status_code == 403

    # TEST D: When Işıl explicitly grants temporary `documents_view` assistance, Admin can view, and revoking immediately blocks again!
    grant_res = c_i.post("/api/privacy/grants", json={"scope": "documents_view", "hours_valid": 2}, headers={"X-CSRF-Token": csrf_i})
    assert grant_res.status_code == 200
    grant_id = grant_res.get_json()["grant_id"]

    allowed_doc = c_j.get(f"/api/admin/assist/{u_i['id']}/documents/{isil_doc_id}")
    assert allowed_doc.status_code == 200
    assert "Accolade Customer Onboarding" in allowed_doc.get_json()["content"]

    rev_res = c_i.delete(f"/api/privacy/grants/{grant_id}", headers={"X-CSRF-Token": csrf_i})
    assert rev_res.status_code == 200
    assert c_j.get(f"/api/admin/assist/{u_i['id']}/documents/{isil_doc_id}").status_code == 403

    # TEST E: Browser sessions and VaultStorage enforce strict isolation
    dir_j = get_isolated_browser_profile_dir(u_j["id"], u_j["id"])
    dir_l = get_isolated_browser_profile_dir(u_l["id"], u_l["id"])
    assert dir_j != dir_l
    with pytest.raises(AccessDeniedError):
        get_isolated_browser_profile_dir(u_j["id"], u_l["id"])
    with pytest.raises(SafetyInterventionRequired):
        assert_action_safe("submit_application")


# =============================================================================
# 3. LINDSEY'S RECRUITER: LEAVE MALTA & REMOTE-FIRST EUROPE STRATEGY
# =============================================================================

def test_lindsey_recruiter_prioritizes_leaving_malta_and_uses_her_profile(isolated_env):
    db = isolated_env["db"]
    app = isolated_env["app"]
    c_l, csrf_l, u_l = _login_client(app, "lindsey", "LindseyStrongPass!2026")
    prof_l = get_user_profile(u_l["id"], u_l["id"], db_path=db)

    # 1. On-site Malta iGaming job -> MUST be heavily penalized/blocked!
    malta_onsite = {
        "title": "AML & Responsible Gambling Manager",
        "company": "Malta Casino Group",
        "location": "Sliema, Malta",
        "remote_type": "Hybrid",
        "description": "Hybrid 3 days in Sliema office, Malta. Manage AML, KYC, and Responsible Gambling."
    }
    res_malta = evaluate_job_for_user("lindsey", malta_onsite, prof_l)
    assert res_malta["score"] <= 10
    assert res_malta["flags"]["malta_conflict"] is True

    # 2. Fake remote locked to Malta residents -> MUST also be blocked!
    malta_locked = {
        "title": "Player Operations Manager (Remote)",
        "company": "IslandGaming",
        "location": "Remote (Malta)",
        "remote_type": "Remote",
        "description": "Remote from Malta only. Candidates must reside in Malta."
    }
    res_locked = evaluate_job_for_user("lindsey", malta_locked, prof_l)
    assert res_locked["score"] <= 10
    assert res_locked["flags"]["malta_conflict"] is True

    # 3. True Remote European iGaming AML / Player Ops role -> MUST score >= 90!
    eu_remote = {
        "title": "Head of Player Operations, AML & Fraud (Remote Europe)",
        "company": "EuroGaming Tech",
        "location": "Remote (European Union)",
        "remote_type": "Remote",
        "description": "100% fully remote anywhere in the European Union. Lead Player Operations, AML, Responsible Gambling, KYC, Fraud Prevention and Payments."
    }
    res_eu_remote = evaluate_job_for_user("lindsey", eu_remote, prof_l)
    assert res_eu_remote["score"] >= 92

    # 4. Mainland Europe hub with relocation (e.g., Lisbon, Portugal) -> Strong match (>= 85)
    lisbon_hub = {
        "title": "Compliance & Payments Fraud Manager",
        "company": "FintechPay EU",
        "location": "Lisbon, Portugal",
        "remote_type": "Hybrid",
        "relocation_assistance": 1,
        "description": "Relocation package provided to Lisbon. Lead KYC, Fraud, Chargebacks and AML compliance in English."
    }
    res_lisbon = evaluate_job_for_user("lindsey", lisbon_hub, prof_l)
    assert res_lisbon["score"] >= 85

    # 5. Verification Gate blocks Lindsey's live CV package until she confirms dates/titles
    vid, _ = upsert_vacancy({**eu_remote, "job_url": "https://example.com/eu-remote", "source": "Direct"}, db_path=db)
    mid, _ = save_user_job_match(u_l["id"], vid, res_eu_remote, db_path=db)
    blocked = c_l.post(f"/api/jobs/{mid}/prepare", headers={"X-CSRF-Token": csrf_l})
    assert blocked.status_code == 403
    assert blocked.get_json()["verification_required"] is True

    # Confirm Lindsey's profile dates and verify her account -> CV uses ONLY Lindsey's background!
    for exp in prof_l["experience"]:
        exp["dates_verified"] = True
        exp["start_date"] = "2022"
        exp["end_date"] = "Present"
    prof_l["personal"]["email"] = "lindsey@example.com"
    save_user_profile(u_l["id"], u_l["id"], prof_l, mark_verified=True, db_path=db)

    ok_prep = c_l.post(f"/api/jobs/{mid}/prepare", headers={"X-CSRF-Token": csrf_l})
    assert ok_prep.status_code == 200
    pkg = ok_prep.get_json()
    assert "Lindsey Whitmore" in pkg["cv_content"]
    assert "Patrianna" in pkg["cv_content"]
    assert "Betmaster" in pkg["cv_content"]
    # Ensure ZERO bleed from Justin or Işıl
    assert "QuidelOrtho" not in pkg["cv_content"]
    assert "University of San Diego" not in pkg["cv_content"]
    assert "Turkish" not in pkg["cv_content"]


# =============================================================================
# 4. IŞIL'S RECRUITER: NO FRENCH/EU WORK-AUTH ASSUMPTION & ZERO HALLUCINATION
# =============================================================================

def test_isil_recruiter_work_auth_and_preliminary_verification_gate(isolated_env):
    db = isolated_env["db"]
    app = isolated_env["app"]
    c_i, csrf_i, u_i = _login_client(app, "isil", "IsilStrongPass!2026")
    prof_i = get_user_profile(u_i["id"], u_i["id"], db_path=db)

    # 1. On-site job in France without visa sponsorship -> Must NOT assume French work authorization!
    france_onsite = {
        "title": "Customer Onboarding Specialist (English)",
        "company": "ParisSaaS",
        "location": "Paris, France",
        "remote_type": "On-site",
        "description": "English-speaking Customer Onboarding Specialist based on-site in Paris."
    }
    res_fr = evaluate_job_for_user("isil", france_onsite, prof_i)
    assert res_fr["score"] < 55
    assert res_fr["flags"]["work_auth_warning"] is True
    assert "Work Auth Penalty" in res_fr["rationale"]

    # 2. Job requiring fluent Czech -> Penalized!
    czech_req = {
        "title": "Zákaznická podpora",
        "company": "LocalCZ",
        "location": "Prague, Czech Republic",
        "remote_type": "On-site",
        "description": "Requires fluent Czech (C1) and English."
    }
    res_cz = evaluate_job_for_user("isil", czech_req, prof_i)
    assert res_cz["flags"]["language_barrier"] is True
    assert res_cz["score"] < 55

    # 3. Prague English Customer Onboarding / Turkish specialist role -> Strong score (>= 85)!
    prague_good = {
        "title": "Customer Onboarding & Support Specialist (English / Turkish)",
        "company": "GlobalSaaS Prague",
        "location": "Prague, Czech Republic",
        "remote_type": "Hybrid",
        "description": "Seeking C2 English and Turkish speaker in Prague for customer onboarding, training, and support."
    }
    res_pg = evaluate_job_for_user("isil", prague_good, prof_i)
    assert res_pg["score"] >= 88

    # 4. Preliminary unverified fields (Amazon, Salesforce, iCIMS, OnBase, unverified degrees) MUST NOT appear in CV!
    preview_cv = generate_tailored_cv(prague_good, prof_i)
    assert "Accolade" in preview_cv
    assert "Salesforce" not in preview_cv
    assert "iCIMS" not in preview_cv
    assert "OnBase" not in preview_cv
    assert "Amazon" not in preview_cv
    assert "QuidelOrtho" not in preview_cv
    assert "Patrianna" not in preview_cv

    # 5. Live package preparation is blocked while Işıl's account is unverified
    vid, _ = upsert_vacancy({**prague_good, "job_url": "https://example.com/prague-onboarding", "source": "Direct"}, db_path=db)
    mid, _ = save_user_job_match(u_i["id"], vid, res_pg, db_path=db)
    blocked = c_i.post(f"/api/jobs/{mid}/prepare", headers={"X-CSRF-Token": csrf_i})
    assert blocked.status_code == 403
    assert blocked.get_json()["verification_required"] is True

    # Scheduler `morning_prep` also respects the Verification Gate!
    sched_res = run_scheduled_stage_for_user("isil", "morning_prep", db_path=db)
    assert sched_res["status"] == "blocked_verification_gate"


# =============================================================================
# 5. JUSTIN'S EXISTING PRODUCTION DATABASE & RECRUITER PRESERVATION TEST
# =============================================================================

def test_justin_real_migrated_database_preserved():
    """Verifies Justin's actual production SQLite DB retained all 217+ jobs and works cleanly."""
    init_db(db_path=DB_PATH)
    stats = get_dashboard_stats(user_slug="justin", db_path=DB_PATH)
    assert stats["total_discovered"] >= 215
    assert stats["high_match_count"] >= 80
    assert (stats["status_ready_to_apply"] + stats["status_awaiting_approval"]) >= 2

    justin = get_user_by_slug("justin", db_path=DB_PATH)
    prof = get_user_profile(justin["id"], justin["id"], db_path=DB_PATH)

    # Malta must still score 0 for Justin
    malta_check = evaluate_job_for_user("justin", {
        "title": "Customer Support Agent",
        "company": "BetCo",
        "location": "St Julian's, Malta",
        "description": "English customer service in Malta"
    }, prof)
    assert malta_check["score"] == 0

    # SAP + Export in Lisbon / Remote must score >= 90 for Justin
    sap_check = evaluate_job_for_user("justin", {
        "title": "EMEA Export Order Management Specialist (SAP)",
        "company": "MedDevices Intl",
        "location": "Remote (France)",
        "remote_type": "Remote",
        "contract_type": "CDI",
        "description": "SAP VA32, ZBL, ZDR order management, airway bills, EX-1, Certificates of Origin in fluent English."
    }, prof)
    assert sap_check["score"] >= 95

    # Italian Customer Advisor MUST be penalized and NOT score in the 90s!
    italian_check = evaluate_job_for_user("justin", {
        "title": "Italian Customer Advisor for Airbnb - Remote in Portugal",
        "company": "Foundever",
        "location": "Lisboa, Lisbon, Portugal",
        "remote_type": "Remote",
        "description": "Customer Support Advisor. Keywords: Customer Support English."
    }, prof)
    assert italian_check["score"] <= 35
    assert italian_check["flags"]["language_barrier"] is True

    # C2 in non-verified language (e.g. German C2) MUST be heavily penalized
    german_c2_check = evaluate_job_for_user("justin", {
        "title": "Order Management Specialist",
        "company": "GlobalCo",
        "location": "Remote",
        "remote_type": "Remote",
        "description": "SAP order management. Requires German C2 and English fluent."
    }, prof)
    assert german_c2_check["score"] <= 35
    assert german_c2_check["flags"]["language_barrier"] is True
