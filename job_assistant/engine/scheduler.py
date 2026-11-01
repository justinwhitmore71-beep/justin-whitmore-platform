"""
Configurable Multi-User Recruitment Scheduler (Part 12).
Default user schedule (configurable per user in their own timezone):
- 08:00 -> morning_discovery: Search for new vacancies
- 08:30 -> morning_scoring: Evaluate and score discovered opportunities
- 09:00 -> morning_prep: Prepare application drafts ('awaiting_approval') for strongest matches (verified profiles only!)
- 09:30 -> morning_digest: Compile review digest notification for the user
- 16:00 -> afternoon_check: Afternoon check for new vacancies & due follow-ups

Works in two modes without requiring Antigravity to stay open:
1. Persistent Server / Local Daemon: APScheduler BackgroundScheduler
2. Serverless Cloud (Cloud Run): Stateless `run_scheduled_stage_for_user()` triggered via Google Cloud Scheduler OIDC/Secret webhook.
"""

import json
from typing import Dict, Any, Optional

from job_assistant.engine.db import (
    init_db,
    get_user_by_slug,
    get_user_profile,
    list_user_matches,
    log_scheduler_run,
    record_error_log,
    DB_PATH,
)
from job_assistant.engine.discovery.discovery_manager import (
    run_discovery_for_user,
    score_vacancies_for_user,
)
from job_assistant.engine.application.builder import prepare_user_application_package


def run_scheduled_stage_for_user(
    user_slug: str,
    stage: str,
    include_slow_scrapers: bool = False,
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    """Executes one scheduled recruitment stage strictly isolated to `user_slug`."""
    init_db(db_path=db_path)
    user = get_user_by_slug(user_slug, db_path=db_path)
    if not user:
        raise ValueError(f"Unknown user: {user_slug}")
    uid = user["id"]
    profile = get_user_profile(uid, uid, db_path=db_path)
    sched_cfg = profile.get("schedule", {})

    if not sched_cfg.get("enabled", True):
        log_scheduler_run(uid, stage, "skipped", "User schedule disabled", db_path=db_path)
        return {"user": user_slug, "stage": stage, "status": "skipped"}

    try:
        if stage in ("morning_discovery", "afternoon_check"):
            res = run_discovery_for_user(target_user_slug=user_slug, include_slow_scrapers=include_slow_scrapers, db_path=db_path)
            summary = f"Collected {res['raw_collected']} listings; {res['new_shared_vacancies']} new shared vacancies."
            log_scheduler_run(uid, stage, "success", summary, db_path=db_path)
            return {"user": user_slug, "stage": stage, "status": "success", "details": res}

        elif stage == "morning_scoring":
            res = score_vacancies_for_user(user_slug=user_slug, db_path=db_path)
            summary = f"Evaluated {res['evaluated']} vacancies; {res['strong_matches_75_plus']} strong matches (75+)."
            log_scheduler_run(uid, stage, "success", summary, db_path=db_path)
            return {"user": user_slug, "stage": stage, "status": "success", "details": res}

        elif stage == "morning_prep":
            if not user.get("profile_verified"):
                msg = "Skipped auto-drafting: User profile awaits verification confirmation."
                log_scheduler_run(uid, stage, "blocked_verification_gate", msg, db_path=db_path)
                return {"user": user_slug, "stage": stage, "status": "blocked_verification_gate", "summary": msg}

            min_score = int(sched_cfg.get("auto_prep_min_score", 82))
            max_daily = int(sched_cfg.get("auto_prep_max_daily", 3))
            candidates = list_user_matches(
                acting_user_id=uid,
                owner_user_id=uid,
                status="discovered",
                min_score=min_score,
                limit=max_daily,
                db_path=db_path,
            )
            prepared_ids = []
            for m in candidates:
                prepare_user_application_package(uid, uid, m["match_id"], enforce_verification_gate=True, db_path=db_path)
                prepared_ids.append(m["match_id"])

            summary = f"Prepared {len(prepared_ids)} application drafts awaiting user approval (match IDs: {prepared_ids})."
            log_scheduler_run(uid, stage, "success", summary, db_path=db_path)
            return {"user": user_slug, "stage": stage, "status": "success", "prepared_match_ids": prepared_ids}

        elif stage == "morning_digest":
            awaiting = list_user_matches(uid, uid, status="awaiting_approval", limit=20, db_path=db_path)
            top_new = list_user_matches(uid, uid, status="discovered", min_score=75, limit=10, db_path=db_path)
            summary = f"Review Digest ready: {len(awaiting)} drafts awaiting approval, {len(top_new)} new strong matches."
            log_scheduler_run(uid, stage, "success", summary, db_path=db_path)
            return {
                "user": user_slug,
                "stage": stage,
                "status": "success",
                "awaiting_approval_count": len(awaiting),
                "top_new_matches_count": len(top_new),
                "summary": summary,
            }

        else:
            raise ValueError(f"Unsupported schedule stage: {stage}")
    except Exception as e:
        record_error_log(f"scheduler:{stage}", str(e), user_id=uid, db_path=db_path)
        log_scheduler_run(uid, stage, "error", str(e), db_path=db_path)
        return {"user": user_slug, "stage": stage, "status": "error", "error": str(e)}


def start_background_scheduler(db_path: str = DB_PATH):
    """Starts an APScheduler BackgroundScheduler syncing per-user configured times."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    init_db(db_path=db_path)
    scheduler = BackgroundScheduler()

    for slug in ("justin", "isil", "lindsey"):
        u = get_user_by_slug(slug, db_path=db_path)
        if not u:
            continue
        prof = get_user_profile(u["id"], u["id"], db_path=db_path)
        sc = prof.get("schedule", {})
        if not sc.get("enabled", True):
            continue
        tz = sc.get("timezone", "Europe/Paris")
        jobs_map = sc.get("jobs", {})
        for stage_name, hhmm in jobs_map.items():
            try:
                hr, mn = [int(x) for x in str(hhmm).split(":")]
                scheduler.add_job(
                    run_scheduled_stage_for_user,
                    trigger=CronTrigger(hour=hr, minute=mn, timezone=tz),
                    kwargs={"user_slug": slug, "stage": stage_name, "include_slow_scrapers": True, "db_path": db_path},
                    id=f"{slug}_{stage_name}",
                    replace_existing=True,
                )
            except Exception as e:
                record_error_log("scheduler:init", f"Invalid time '{hhmm}' for {slug}.{stage_name}: {e}", user_id=u["id"], db_path=db_path)

    scheduler.start()
    return scheduler
