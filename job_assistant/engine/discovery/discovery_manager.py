"""
Multi-User Job Discovery & Evaluation Orchestrator.
- Scrapes multi-platform sources (Remote Boards, Greenhouse Direct Career Pages,
  LinkedIn Guest Searches, France Travail, Prague/Czechia feeds, and Pan-EU iGaming/Fintech feeds).
- Enriches metadata, filters scam traps, and stores unique vacancies in `vacancies`.
- Evaluates vacancies independently per user (`justin`, `isil`, `lindsey`) using each person's
  private profile, work-authorization rules, and custom scoring weights.
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from job_assistant.engine.db import (
    init_db,
    get_connection,
    get_user_by_slug,
    get_user_profile,
    upsert_vacancy,
    save_user_job_match,
    log_scan,
    record_error_log,
    DB_PATH,
)
from job_assistant.engine.scoring.scorer import evaluate_job_for_user, detect_scam_and_remote_traps
from job_assistant.engine.application.builder import perform_gap_analysis
from job_assistant.engine.discovery.remote_boards import (
    fetch_remotive_jobs,
    fetch_jobicy_jobs,
    fetch_arbeitnow_jobs,
)
from job_assistant.engine.discovery.linkedin_scraper import run_targeted_linkedin_searches
from job_assistant.engine.discovery.france_travail import run_targeted_france_travail_searches
from job_assistant.engine.discovery.europe_specialist_boards import (
    enrich_vacancy_metadata,
    fetch_greenhouse_europe_jobs,
    run_isil_targeted_searches,
    run_lindsey_targeted_searches,
)
from job_assistant.engine.discovery.custom_source_scraper import execute_custom_source_scan
from job_assistant.engine.db import list_user_custom_sources, update_user_custom_source_scanned


def load_profile(user_slug: str = "justin", db_path: str = DB_PATH) -> Dict[str, Any]:
    init_db(db_path=db_path)
    u = get_user_by_slug(user_slug, db_path=db_path)
    if u:
        return get_user_profile(u["id"], u["id"], db_path=db_path)
    profile_path = os.path.join(WORKSPACE_ROOT, "job_assistant", "data", "master_profile.json")
    with open(profile_path, "r", encoding="utf-8") as f:
        return json.load(f)


def score_vacancies_for_user(
    user_slug: str,
    vacancy_ids: Optional[List[int]] = None,
    min_store_score: int = 35,
    db_path: str = DB_PATH
) -> Dict[str, int]:
    """
    Evaluates shared catalog vacancies against a single user's independent profile & weights.
    Only stores relevant matches (or updates existing matches) for that user.
    """
    init_db(db_path=db_path)
    user = get_user_by_slug(user_slug, db_path=db_path)
    if not user:
        raise ValueError(f"Unknown user slug: {user_slug}")
    uid = user["id"]
    profile = get_user_profile(uid, uid, db_path=db_path)

    conn = get_connection(db_path)
    cur = conn.cursor()
    if vacancy_ids:
        placeholders = ",".join("?" for _ in vacancy_ids)
        cur.execute(f"SELECT * FROM vacancies WHERE is_expired = 0 AND id IN ({placeholders})", vacancy_ids)
    else:
        cur.execute("SELECT * FROM vacancies WHERE is_expired = 0")
    vac_rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    evaluated = 0
    stored_new = 0
    high_matches = 0

    for v in vac_rows:
        # Enrich legacy rows if missing category/country
        if not v.get("category") or not v.get("country"):
            enriched = enrich_vacancy_metadata(v)
            conn2 = get_connection(db_path)
            conn2.execute(
                "UPDATE vacancies SET country=?, seniority=?, category=?, required_languages=?, contract_type=?, remote_country_restrictions=? WHERE id=?",
                (
                    enriched["country"],
                    enriched["seniority"],
                    enriched["category"],
                    enriched["required_languages"],
                    enriched["contract_type"],
                    enriched["remote_country_restrictions"],
                    v["id"],
                ),
            )
            conn2.commit()
            conn2.close()
            v.update(enriched)

        score_res = evaluate_job_for_user(user_slug=user_slug, job_data=v, profile_data=profile)
        evaluated += 1

        # Avoid cluttering Işıl or Lindsey's feed with French Orléans local janitor/warehouse posts
        if user_slug != "justin" and v.get("source") == "France Travail" and score_res["score"] < 55:
            continue

        # Always refresh existing matches with the new score; for new discoveries, store if score >= min_store_score or user is justin
        gap = perform_gap_analysis(v, profile)
        _, is_new = save_user_job_match(
            user_id=uid,
            vacancy_id=v["id"],
            score_data=score_res,
            gap_analysis=gap,
            db_path=db_path,
        )
        if is_new:
            stored_new += 1
        if score_res["score"] >= 75:
            high_matches += 1

    return {
        "user": user_slug,
        "evaluated": evaluated,
        "new_matches": stored_new,
        "strong_matches_75_plus": high_matches,
    }


def run_discovery_for_user(
    target_user_slug: Optional[str] = None,
    include_slow_scrapers: bool = True,
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    """
    Runs multi-platform discovery.
    If target_user_slug is specified ('justin', 'isil', 'lindsey'), runs shared + that user's
    targeted scrapers and scores for that user. If None, runs full platform discovery for all 3 users!
    """
    init_db(db_path=db_path)
    slugs = [target_user_slug.lower()] if target_user_slug else ["justin", "isil", "lindsey", "laurence"]
    collected: List[Dict[str, Any]] = []

    # 1. Shared Remote & Direct Company Career Boards (Benefits all 3 users)
    for label, fn in [
        ("Remotive", lambda: fetch_remotive_jobs(category="customer-support", limit=25)),
        ("Jobicy", lambda: fetch_jobicy_jobs(count=25, tag="support")),
        ("Arbeitnow", lambda: fetch_arbeitnow_jobs(limit=35)),
        ("Greenhouse Direct Careers", lambda: fetch_greenhouse_europe_jobs(max_per_company=6)),
    ]:
        try:
            batch = [enrich_vacancy_metadata(x) for x in fn()]
            collected.extend(batch)
            log_scan(label, "shared_europe_remote", len(batch), 0, db_path=db_path)
        except Exception as e:
            record_error_log(f"discovery:{label}", str(e), db_path=db_path)
            log_scan(label, "shared_europe_remote", 0, 0, status="error", error=str(e), db_path=db_path)

    # 2. User-Specific Targeted Connectors
    if include_slow_scrapers:
        if "justin" in slugs:
            try:
                li_j = [enrich_vacancy_metadata(x) for x in run_targeted_linkedin_searches()]
                collected.extend(li_j)
                log_scan("LinkedIn (Justin)", "orleans_lisbon_remote", len(li_j), 0, db_path=db_path)
            except Exception as e:
                record_error_log("discovery:linkedin_justin", str(e), db_path=db_path)

            try:
                ft_j = [enrich_vacancy_metadata(x) for x in run_targeted_france_travail_searches()]
                collected.extend(ft_j)
                log_scan("France Travail", "orleans_45", len(ft_j), 0, db_path=db_path)
            except Exception as e:
                record_error_log("discovery:france_travail", str(e), db_path=db_path)

        if "isil" in slugs:
            try:
                isil_jobs = run_isil_targeted_searches()
                collected.extend(isil_jobs)
                log_scan("Prague & Czechia (Işıl)", "prague_onboarding_english_turkish", len(isil_jobs), 0, db_path=db_path)
            except Exception as e:
                record_error_log("discovery:isil", str(e), db_path=db_path)

        if "lindsey" in slugs:
            try:
                lindsey_jobs = run_lindsey_targeted_searches()
                collected.extend(lindsey_jobs)
                log_scan("EU iGaming & Fintech (Lindsey)", "remote_eu_aml_ops_kyc", len(lindsey_jobs), 0, db_path=db_path)
            except Exception as e:
                record_error_log("discovery:lindsey", str(e), db_path=db_path)

        # Scan each user's custom added sources and career boards
        for s in slugs:
            u_obj = get_user_by_slug(s, db_path=db_path)
            if not u_obj:
                continue
            custom_sources = list_user_custom_sources(u_obj["id"], u_obj["id"], db_path=db_path)
            for cs in custom_sources:
                if not cs.get("is_active", 1):
                    continue
                try:
                    cs_jobs = execute_custom_source_scan(cs)
                    collected.extend(cs_jobs)
                    update_user_custom_source_scanned(cs["id"], db_path=db_path)
                    log_scan(f"Custom: {cs['source_name']}", cs.get("target_url") or cs.get("query_keywords", ""), len(cs_jobs), 0, db_path=db_path)
                except Exception as e:
                    record_error_log(f"discovery:custom_source:{cs['id']}", str(e), user_id=u_obj["id"], db_path=db_path)

    # 3. Filter scam suspects & upsert into shared `vacancies`
    touched_vacancy_ids: List[int] = []
    new_vacancies = 0
    for item in collected:
        traps = detect_scam_and_remote_traps(item)
        item["quality_flags"] = traps
        if traps["is_scam_suspect"]:
            continue  # Drop recruitment scams outright
        vid, is_new = upsert_vacancy(item, db_path=db_path)
        touched_vacancy_ids.append(vid)
        if is_new:
            new_vacancies += 1

    # 4. Score vacancies independently for each requested user
    per_user_results = {}
    for s in slugs:
        per_user_results[s] = score_vacancies_for_user(s, vacancy_ids=None, db_path=db_path)

    return {
        "timestamp": datetime.now().isoformat(),
        "raw_collected": len(collected),
        "new_shared_vacancies": new_vacancies,
        "per_user": per_user_results,
    }


def run_full_discovery_cycle(include_slow_scrapers: bool = True, user_slug: Optional[str] = None) -> Dict[str, Any]:
    """Backward-compatible entry point."""
    return run_discovery_for_user(target_user_slug=user_slug, include_slow_scrapers=include_slow_scrapers)


if __name__ == "__main__":
    summary = run_discovery_for_user(target_user_slug=None, include_slow_scrapers=True)
    print(json.dumps(summary, indent=2))
