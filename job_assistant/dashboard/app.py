"""
Multi-User AI Recruitment Platform Web Application & API Server.
- Independent authenticated sessions for Justin, Işıl, and Lindsey.
- Strict server-side authorization & tenant isolation on every endpoint.
- Onboarding & Verification Gate enforcement before live application generation.
- Full Part 9 filtering (location, salary, category, seniority, remote, company, status, score).
- Privacy-preserving Administrator Console with user-controlled opt-in assistance grants & audit logs.
- Cloud Scheduler & Firebase Auth ready for remote deployment.
"""

import hmac
import json
import os
import secrets
import sys
import threading
from functools import wraps
from typing import Dict, Any, Optional

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    session,
    redirect,
    url_for,
    Response,
)

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from job_assistant.engine.security import (
    AccessDeniedError,
    VerificationGateLockedError,
    VaultStorage,
    generate_csrf_token,
    verify_csrf_token,
    verify_firebase_id_token,
)
from job_assistant.engine.db import (
    DB_PATH,
    init_db,
    authenticate_user,
    get_user_by_id,
    get_user_by_slug,
    create_password_reset,
    complete_password_reset,
    change_user_password,
    get_user_profile,
    save_user_profile,
    list_user_matches,
    get_user_match_detail,
    update_user_match,
    get_user_dashboard_stats,
    list_user_documents,
    get_user_document,
    grant_admin_assistance,
    revoke_admin_assistance,
    list_user_grants,
    get_admin_system_overview,
    list_user_custom_sources,
    add_user_custom_source,
    delete_user_custom_source,
    update_user_custom_source_scanned,
    upsert_vacancy,
)
from job_assistant.engine.discovery.discovery_manager import (
    run_discovery_for_user,
    score_vacancies_for_user,
)
from job_assistant.engine.application.builder import (
    perform_gap_analysis,
    prepare_user_application_package,
    generate_interview_prep,
)
from job_assistant.engine.application.cv_parser import upload_and_parse_user_cv
from job_assistant.engine.automation.browser_assister import (
    build_isolated_user_automation_draft,
    SafetyInterventionRequired,
)
from job_assistant.engine.scheduler import run_scheduled_stage_for_user


def _load_or_create_secret_key() -> str:
    env_secret = os.environ.get("FLASK_SECRET_KEY")
    if env_secret:
        return env_secret
    secret_file = os.path.join(WORKSPACE_ROOT, "job_assistant", "data", ".flask_secret")
    os.makedirs(os.path.dirname(secret_file), exist_ok=True)
    if os.path.isfile(secret_file):
        with open(secret_file, "r", encoding="utf-8") as f:
            val = f.read().strip()
            if len(val) >= 32:
                return val
    new_secret = secrets.token_hex(32)
    with open(secret_file, "w", encoding="utf-8") as f:
        f.write(new_secret)
    return new_secret


def create_app(db_path: str = DB_PATH, enforce_csrf: bool = True) -> Flask:
    flask_app = Flask(__name__, template_folder="templates", static_folder="static")
    flask_app.config["SECRET_KEY"] = _load_or_create_secret_key()
    flask_app.config["DB_PATH"] = db_path
    flask_app.config["ENFORCE_CSRF"] = enforce_csrf
    flask_app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB max CV upload
    flask_app.config["SESSION_COOKIE_HTTPONLY"] = True
    flask_app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if os.environ.get("FORCE_HTTPS_COOKIES") == "1":
        flask_app.config["SESSION_COOKIE_SECURE"] = True

    scan_states: Dict[str, bool] = {}

    def _db() -> str:
        return flask_app.config["DB_PATH"]

    @flask_app.after_request
    def _security_headers(resp: Response) -> Response:
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        return resp

    def login_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            uid = session.get("user_id")
            if not uid:
                return jsonify({"error": "Authentication required"}), 401
            user = get_user_by_id(int(uid), db_path=_db())
            if not user or user.get("account_status") == "suspended":
                session.clear()
                return jsonify({"error": "Session invalid or account suspended"}), 401
            if flask_app.config["ENFORCE_CSRF"] and request.method in ("POST", "PUT", "DELETE", "PATCH"):
                provided = request.headers.get("X-CSRF-Token") or (request.form.get("csrf_token") if request.form else None)
                if not verify_csrf_token(session.get("csrf_token"), provided):
                    return jsonify({"error": "CSRF token missing or invalid"}), 403
            request.current_user = user  # type: ignore
            return fn(*args, **kwargs)
        return wrapper

    def admin_required(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            user = getattr(request, "current_user", None)
            if not user or not user.get("is_admin"):
                return jsonify({"error": "Administrator privileges required"}), 403
            return fn(*args, **kwargs)
        return wrapper

    # -------------------------------------------------------------------------
    # PAGES
    # -------------------------------------------------------------------------

    @flask_app.route("/login")
    def login_page():
        if session.get("user_id"):
            return redirect(url_for("index"))
        return render_template("login.html")

    @flask_app.route("/")
    def index():
        if not session.get("user_id"):
            return redirect(url_for("login_page"))
        return render_template("index.html")

    # -------------------------------------------------------------------------
    # AUTHENTICATION & PASSWORD RECOVERY
    # -------------------------------------------------------------------------

    @flask_app.route("/api/auth/login", methods=["POST"])
    def api_login():
        init_db(db_path=_db())
        data = request.get_json(silent=True) or {}

        # Optional Firebase ID token mode
        fb_token = data.get("firebase_id_token")
        if fb_token:
            decoded = verify_firebase_id_token(fb_token)
            if not decoded or not decoded.get("email"):
                return jsonify({"error": "Invalid Firebase authentication token"}), 401
            user = get_user_by_slug(decoded["email"].split("@")[0], db_path=_db())
            if not user:
                return jsonify({"error": "No authorized platform account matches this email"}), 403
        else:
            identifier = data.get("username") or data.get("email") or ""
            password = data.get("password") or ""
            user = authenticate_user(identifier, password, db_path=_db())
            if not user:
                return jsonify({"error": "Invalid username/email or password"}), 401

        session.clear()
        session["user_id"] = user["id"]
        session["user_slug"] = user["slug"]
        session["csrf_token"] = generate_csrf_token()
        return jsonify({
            "success": True,
            "user": user,
            "csrf_token": session["csrf_token"]
        })

    @flask_app.route("/api/auth/logout", methods=["POST"])
    def api_logout():
        session.clear()
        return jsonify({"success": True})

    @flask_app.route("/api/auth/me")
    @login_required
    def api_me():
        user = request.current_user  # type: ignore
        if "csrf_token" not in session:
            session["csrf_token"] = generate_csrf_token()
        return jsonify({
            "user": user,
            "csrf_token": session["csrf_token"],
        })

    @flask_app.route("/api/auth/forgot-password", methods=["POST"])
    def api_forgot_password():
        init_db(db_path=_db())
        data = request.get_json(silent=True) or {}
        identifier = data.get("identifier") or ""
        token = create_password_reset(identifier, db_path=_db())
        # In production SMTP/Firebase sends email; in local mode we log notice without leaking account existence
        resp: Dict[str, Any] = {
            "success": True,
            "message": "If the account exists, a single-use 30-minute recovery token has been issued."
        }
        if os.environ.get("LOCAL_DEV_RETURN_RESET_TOKEN") == "1" and token:
            resp["dev_reset_token"] = token
        return jsonify(resp)

    @flask_app.route("/api/auth/reset-password", methods=["POST"])
    def api_reset_password():
        init_db(db_path=_db())
        data = request.get_json(silent=True) or {}
        token = data.get("token") or ""
        new_pw = data.get("new_password") or ""
        try:
            ok = complete_password_reset(token, new_pw, db_path=_db())
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        if not ok:
            return jsonify({"error": "Invalid, expired, or already-used recovery token"}), 400
        return jsonify({"success": True})

    @flask_app.route("/api/auth/change-password", methods=["POST"])
    @login_required
    def api_change_password():
        user = request.current_user  # type: ignore
        data = request.get_json(silent=True) or {}
        new_pw = data.get("new_password") or ""
        try:
            change_user_password(user["id"], user["id"], new_pw, db_path=_db())
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"success": True})

    # -------------------------------------------------------------------------
    # STRICTLY TENANT-ISOLATED USER ENDPOINTS
    # -------------------------------------------------------------------------

    @flask_app.route("/api/stats")
    @login_required
    def api_stats():
        user = request.current_user  # type: ignore
        uid = user["id"]
        stats = get_user_dashboard_stats(uid, uid, db_path=_db())
        stats["scan_running"] = bool(scan_states.get(user["slug"], False))
        stats["profile_verified"] = bool(user["profile_verified"])
        stats["user_slug"] = user["slug"]
        stats["full_name"] = user["full_name"]
        stats["is_admin"] = bool(user["is_admin"])
        return jsonify(stats)

    @flask_app.route("/api/profile", methods=["GET", "PUT"])
    @login_required
    def api_profile():
        user = request.current_user  # type: ignore
        uid = user["id"]
        if request.method == "GET":
            prof = get_user_profile(uid, uid, allow_granted_admin=False, db_path=_db())
            return jsonify({
                "user": user,
                "profile": prof
            })

        data = request.get_json(silent=True) or {}
        new_profile = data.get("profile")
        if not isinstance(new_profile, dict):
            return jsonify({"error": "Valid profile object required"}), 400

        mark_verified = data.get("mark_verified")
        save_user_profile(
            acting_user_id=uid,
            owner_user_id=uid,
            profile_data=new_profile,
            mark_verified=bool(mark_verified) if mark_verified is not None else None,
            allow_granted_admin=False,
            db_path=_db()
        )
        # Immediately rescore user's matches with updated preferences & weights!
        rescore_summary = score_vacancies_for_user(user["slug"], db_path=_db())
        refreshed_user = get_user_by_id(uid, db_path=_db())
        return jsonify({
            "success": True,
            "user": refreshed_user,
            "rescore": rescore_summary
        })

    @flask_app.route("/api/cv/upload", methods=["POST"])
    @login_required
    def api_upload_cv():
        user = request.current_user  # type: ignore
        uid = user["id"]
        if "file" not in request.files:
            return jsonify({"error": "No CV file attached"}), 400
        f = request.files["file"]
        if not f.filename:
            return jsonify({"error": "Empty filename"}), 400
        content = f.read()
        try:
            res = upload_and_parse_user_cv(
                acting_user_id=uid,
                owner_user_id=uid,
                filename=f.filename,
                content=content,
                set_as_master=True,
                db_path=_db(),
            )
            return jsonify({"success": True, **res})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @flask_app.route("/api/documents")
    @login_required
    def api_list_docs():
        user = request.current_user  # type: ignore
        uid = user["id"]
        kind = request.args.get("kind")
        docs = list_user_documents(uid, uid, doc_kind=kind, db_path=_db())
        return jsonify({"documents": docs})

    @flask_app.route("/api/documents/<int:doc_id>")
    @login_required
    def api_get_doc(doc_id: int):
        user = request.current_user  # type: ignore
        uid = user["id"]
        doc = get_user_document(uid, uid, doc_id, db_path=_db())
        if not doc:
            return jsonify({"error": "Document not found"}), 404
        vault = VaultStorage()
        try:
            text = vault.read_text(uid, uid, doc["storage_key"])
        except UnicodeDecodeError:
            text = doc.get("extracted_text") or "[Binary PDF/DOCX stored securely in your private vault]"
        return jsonify({"document": doc, "content": text})

    @flask_app.route("/api/jobs")
    @login_required
    def api_jobs():
        user = request.current_user  # type: ignore
        uid = user["id"]
        jobs = list_user_matches(
            acting_user_id=uid,
            owner_user_id=uid,
            status=request.args.get("status", "all"),
            min_score=request.args.get("min_score", type=int, default=0),
            location_filter=request.args.get("location") or None,
            country_filter=request.args.get("country") or None,
            remote_filter=request.args.get("remote_type") or None,
            category_filter=request.args.get("category") or None,
            seniority_filter=request.args.get("seniority") or None,
            company_filter=request.args.get("company") or None,
            salary_filter=request.args.get("salary") or None,
            limit=request.args.get("limit", type=int, default=100),
            allow_granted_admin=False,
            db_path=_db()
        )
        return jsonify({"jobs": jobs, "count": len(jobs)})

    @flask_app.route("/api/jobs/<int:match_id>")
    @login_required
    def api_job_detail(match_id: int):
        user = request.current_user  # type: ignore
        uid = user["id"]
        match_row = get_user_match_detail(uid, uid, match_id, allow_granted_admin=False, db_path=_db())
        if not match_row:
            return jsonify({"error": "Opportunity not found in your workspace"}), 404

        prof = get_user_profile(uid, uid, allow_granted_admin=False, db_path=_db())
        gap = perform_gap_analysis(match_row, prof)
        interview_prep = generate_interview_prep(match_row, prof)

        breakdown = {}
        try:
            breakdown = json.loads(match_row.get("score_breakdown_json") or "{}")
        except Exception:
            breakdown = {}

        cv_text = ""
        cl_text = ""
        qna_data = {}
        vault = VaultStorage()
        if match_row.get("cv_document_id"):
            cv_doc = get_user_document(uid, uid, match_row["cv_document_id"], db_path=_db())
            if cv_doc:
                try:
                    cv_text = vault.read_text(uid, uid, cv_doc["storage_key"])
                except Exception:
                    cv_text = cv_doc.get("extracted_text", "")
        if match_row.get("cover_letter_document_id"):
            cl_doc = get_user_document(uid, uid, match_row["cover_letter_document_id"], db_path=_db())
            if cl_doc:
                try:
                    cl_text = vault.read_text(uid, uid, cl_doc["storage_key"])
                except Exception:
                    cl_text = cl_doc.get("extracted_text", "")
        try:
            qna_data = json.loads(match_row.get("app_answers_json") or "{}")
        except Exception:
            qna_data = {}

        return jsonify({
            "job": match_row,
            "gap_analysis": gap,
            "score_breakdown": breakdown,
            "interview_prep": interview_prep,
            "prepared_documents": {
                "has_package": bool(cv_text or cl_text),
                "cv_version_label": match_row.get("cv_version_label", ""),
                "cv_content": cv_text,
                "cover_letter_content": cl_text,
                "qna_content": qna_data,
            }
        })

    @flask_app.route("/api/jobs/<int:match_id>/prepare", methods=["POST"])
    @login_required
    def api_job_prepare(match_id: int):
        user = request.current_user  # type: ignore
        uid = user["id"]
        try:
            pkg = prepare_user_application_package(
                acting_user_id=uid,
                owner_user_id=uid,
                match_id=match_id,
                enforce_verification_gate=True,
                db_path=_db()
            )
            return jsonify({"success": True, **pkg})
        except VerificationGateLockedError as ve:
            return jsonify({"error": str(ve), "verification_required": True}), 403
        except AccessDeniedError as ae:
            return jsonify({"error": str(ae)}), 403
        except ValueError as e:
            return jsonify({"error": str(e)}), 404

    @flask_app.route("/api/jobs/<int:match_id>/automation-draft", methods=["POST"])
    @login_required
    def api_automation_draft(match_id: int):
        user = request.current_user  # type: ignore
        uid = user["id"]
        data = request.get_json(silent=True) or {}
        try:
            draft = build_isolated_user_automation_draft(
                acting_user_id=uid,
                owner_user_id=uid,
                match_id=match_id,
                inspect_live_url=bool(data.get("inspect_live_url", False)),
                db_path=_db()
            )
            return jsonify({"success": True, "draft": draft})
        except (AccessDeniedError, SafetyInterventionRequired) as se:
            return jsonify({"error": str(se)}), 403
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 404

    @flask_app.route("/api/jobs/<int:match_id>/status", methods=["POST"])
    @login_required
    def api_update_status(match_id: int):
        user = request.current_user  # type: ignore
        uid = user["id"]
        data = request.get_json(silent=True) or {}
        new_status = data.get("status")
        if not new_status:
            return jsonify({"error": "Status required"}), 400
        ok = update_user_match(
            acting_user_id=uid,
            owner_user_id=uid,
            match_id=match_id,
            status=new_status,
            private_notes=data.get("notes"),
            follow_up_date=data.get("follow_up_date"),
            interview_info=data.get("interview_info"),
            db_path=_db()
        )
        if not ok:
            return jsonify({"error": "Match not found in your workspace"}), 404
        return jsonify({"success": True})

    @flask_app.route("/api/scan", methods=["POST"])
    @login_required
    def api_trigger_scan():
        user = request.current_user  # type: ignore
        slug = user["slug"]
        if scan_states.get(slug):
            return jsonify({"status": "already_running"}), 409

        def _bg():
            scan_states[slug] = True
            try:
                run_discovery_for_user(target_user_slug=slug, include_slow_scrapers=True, db_path=_db())
            finally:
                scan_states[slug] = False

        threading.Thread(target=_bg, daemon=True).start()
        return jsonify({"status": "scan_started", "user": slug})

    # -------------------------------------------------------------------------
    # USER CUSTOM JOB SOURCES & TARGET COMPANY CAREER PAGES
    # -------------------------------------------------------------------------

    @flask_app.route("/api/custom-sources", methods=["GET", "POST"])
    @login_required
    def api_custom_sources():
        user = request.current_user  # type: ignore
        uid = user["id"]
        if request.method == "GET":
            sources = list_user_custom_sources(uid, uid, db_path=_db())
            return jsonify({"sources": sources})

        data = request.get_json(silent=True) or {}
        name = (data.get("source_name") or "").strip()
        if not name:
            return jsonify({"error": "Source or Company name is required"}), 400

        sid = add_user_custom_source(
            acting_user_id=uid,
            owner_user_id=uid,
            source_name=name,
            source_type=data.get("source_type", "company_career_page"),
            target_url=data.get("target_url", ""),
            query_keywords=data.get("query_keywords", ""),
            target_location=data.get("target_location", ""),
            db_path=_db()
        )
        return jsonify({"success": True, "source_id": sid})

    @flask_app.route("/api/custom-sources/<int:source_id>", methods=["DELETE"])
    @login_required
    def api_delete_custom_source(source_id: int):
        user = request.current_user  # type: ignore
        ok = delete_user_custom_source(user["id"], user["id"], source_id, db_path=_db())
        return jsonify({"success": ok})

    @flask_app.route("/api/custom-sources/<int:source_id>/scan-now", methods=["POST"])
    @login_required
    def api_scan_custom_source_now(source_id: int):
        from job_assistant.engine.discovery.custom_source_scraper import execute_custom_source_scan
        user = request.current_user  # type: ignore
        uid = user["id"]
        sources = list_user_custom_sources(uid, uid, db_path=_db())
        target_src = next((s for s in sources if s["id"] == source_id), None)
        if not target_src:
            return jsonify({"error": "Custom source not found in your workspace"}), 404

        found_jobs = execute_custom_source_scan(target_src)
        update_user_custom_source_scanned(source_id, db_path=_db())

        new_count = 0
        added_vac_ids = []
        for j in found_jobs:
            vid, is_new = upsert_vacancy(j, db_path=_db())
            added_vac_ids.append(vid)
            if is_new:
                new_count += 1

        rescore = score_vacancies_for_user(user["slug"], vacancy_ids=added_vac_ids if added_vac_ids else None, db_path=_db())
        return jsonify({
            "success": True,
            "jobs_found": len(found_jobs),
            "new_vacancies_added": new_count,
            "rescore_summary": rescore
        })

    # -------------------------------------------------------------------------
    # USER PRIVACY & TRANSPARENT ADMIN ASSISTANCE PERMISSIONS
    # -------------------------------------------------------------------------

    @flask_app.route("/api/privacy/grants", methods=["GET", "POST"])
    @login_required
    def api_privacy_grants():
        user = request.current_user  # type: ignore
        uid = user["id"]
        if request.method == "GET":
            return jsonify({"grants": list_user_grants(uid, uid, db_path=_db())})

        data = request.get_json(silent=True) or {}
        admin_user = get_user_by_slug("justin", db_path=_db())
        if not admin_user:
            return jsonify({"error": "Administrator account not configured"}), 400
        scope = data.get("scope", "profile_assist")
        if scope not in ("profile_assist", "matches_view", "documents_view", "full_assist"):
            return jsonify({"error": "Invalid scope"}), 400
        hours = int(data.get("hours_valid", 24))
        gid = grant_admin_assistance(uid, admin_user["id"], scope=scope, hours_valid=hours, db_path=_db())
        return jsonify({"success": True, "grant_id": gid})

    @flask_app.route("/api/privacy/grants/<int:grant_id>", methods=["DELETE"])
    @login_required
    def api_revoke_grant(grant_id: int):
        user = request.current_user  # type: ignore
        ok = revoke_admin_assistance(user["id"], grant_id, db_path=_db())
        return jsonify({"success": ok})

    # -------------------------------------------------------------------------
    # PRIVACY-PRESERVING ADMINISTRATOR CONSOLE ENDPOINTS
    # -------------------------------------------------------------------------

    @flask_app.route("/api/admin/overview")
    @admin_required
    def api_admin_overview():
        admin_user = request.current_user  # type: ignore
        overview = get_admin_system_overview(admin_user["id"], db_path=_db())
        return jsonify(overview)

    @flask_app.route("/api/admin/assist/<int:target_user_id>/profile")
    @admin_required
    def api_admin_assist_profile(target_user_id: int):
        admin_user = request.current_user  # type: ignore
        try:
            prof = get_user_profile(admin_user["id"], target_user_id, allow_granted_admin=True, db_path=_db())
            return jsonify({"profile": prof})
        except AccessDeniedError as ae:
            return jsonify({"error": str(ae)}), 403

    @flask_app.route("/api/admin/assist/<int:target_user_id>/matches")
    @admin_required
    def api_admin_assist_matches(target_user_id: int):
        admin_user = request.current_user  # type: ignore
        try:
            matches = list_user_matches(admin_user["id"], target_user_id, allow_granted_admin=True, db_path=_db())
            return jsonify({"matches": matches})
        except AccessDeniedError as ae:
            return jsonify({"error": str(ae)}), 403

    @flask_app.route("/api/admin/assist/<int:target_user_id>/documents/<int:doc_id>")
    @admin_required
    def api_admin_assist_doc(target_user_id: int, doc_id: int):
        admin_user = request.current_user  # type: ignore
        try:
            doc = get_user_document(admin_user["id"], target_user_id, doc_id, db_path=_db())
            if not doc:
                return jsonify({"error": "Document not found"}), 404
            vault = VaultStorage()
            txt = vault.read_text(
                admin_user["id"],
                target_user_id,
                doc["storage_key"],
                has_explicit_assistance_grant=bool(doc.get("_via_admin_grant"))
            )
            return jsonify({"document": doc, "content": txt})
        except AccessDeniedError as ae:
            return jsonify({"error": str(ae)}), 403

    @flask_app.route("/api/admin/scheduler/run", methods=["POST"])
    @admin_required
    def api_admin_run_schedule():
        data = request.get_json(silent=True) or {}
        slug = data.get("user_slug", "justin")
        stage = data.get("stage", "morning_scoring")
        res = run_scheduled_stage_for_user(slug, stage, include_slow_scrapers=bool(data.get("slow", False)), db_path=_db())
        return jsonify(res)

    @flask_app.route("/api/internal/cron/tick", methods=["POST"])
    def api_cloud_scheduler_tick():
        """Authenticated Cloud Scheduler webhook so schedules execute 24/7 without a desktop PC open."""
        expected = os.environ.get("CRON_WEBHOOK_SECRET", "")
        provided = request.headers.get("X-Cron-Secret", "")
        if not expected or not hmac.compare_digest(expected, provided):
            return jsonify({"error": "Unauthorized cron trigger"}), 401
        data = request.get_json(silent=True) or {}
        stage = data.get("stage", "morning_discovery")
        results = {}
        for slug in ("justin", "isil", "lindsey"):
            results[slug] = run_scheduled_stage_for_user(slug, stage, include_slow_scrapers=True, db_path=_db())
        return jsonify({"status": "ok", "results": results})

    return flask_app


app = create_app()


def run_dashboard(host: str = "127.0.0.1", port: int = 5000):
    init_db()
    print("\n========================================================")
    print("Multi-User AI Recruitment Platform Active!")
    print(f"Portal URL: http://{host}:{port}")
    print("Accounts: justin (Admin + User) | isil | lindsey")
    print("Bootstrap passwords stored locally in: job_assistant/data/bootstrap_credentials.json")
    print("========================================================\n")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_dashboard()
