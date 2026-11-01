"""
Command Line Interface for the Multi-User AI Recruitment Platform.
Supports Justin, Işıl, and Lindsey independently via `--user <justin|isil|lindsey>`
(defaulting to `justin` so existing commands continue working without breaking).
"""

import argparse
import json
import os
import sys
from datetime import datetime

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from job_assistant.engine.db import (
    init_db,
    get_user_by_slug,
    list_jobs,
    get_job_by_id,
    update_job_status,
    get_dashboard_stats,
)
from job_assistant.engine.discovery.discovery_manager import run_discovery_for_user, load_profile
from job_assistant.engine.application.builder import (
    perform_gap_analysis,
    prepare_user_application_package,
)
from job_assistant.engine.backup import create_platform_backup
from job_assistant.engine.security import VerificationGateLockedError


def cmd_scan(args):
    target = None if args.user == "all" else args.user
    print(f"Initiating discovery sweep (target={args.user})...")
    summary = run_discovery_for_user(target_user_slug=target, include_slow_scrapers=not args.fast)
    print(json.dumps(summary, indent=2))


def cmd_list(args):
    init_db()
    jobs = list_jobs(
        status=args.status,
        min_score=args.min_score,
        location_filter=args.location,
        category=args.category,
        limit=args.limit,
        user_slug=args.user,
    )
    if not jobs:
        print(f"No matching jobs found for '{args.user}'.")
        return

    print(f"\n[{args.user.upper()}] Showing {len(jobs)} jobs:\n")
    print(f"{'ID':<6} {'SCORE':<8} {'STATUS':<16} {'COMPANY':<22} {'TITLE':<38} {'LOCATION'}")
    print("-" * 120)
    for j in jobs:
        status_disp = j["status"].upper()[:14]
        title_disp = (j["title"][:35] + "..") if len(j["title"]) > 37 else j["title"]
        comp_disp = (j["company"][:20] + "..") if len(j["company"]) > 22 else j["company"]
        loc_disp = (j["location"][:25] + "..") if len(j["location"]) > 27 else j["location"]
        print(f"{j['id']:<6} [{j['match_score']}/100] {status_disp:<16} {comp_disp:<22} {title_disp:<38} {loc_disp}")
    print("-" * 120)


def cmd_inspect(args):
    init_db()
    job = get_job_by_id(args.job_id, user_slug=args.user)
    if not job:
        print(f"Error: Match ID {args.job_id} not found in '{args.user}' workspace.")
        return

    profile = load_profile(user_slug=args.user)
    gap = perform_gap_analysis(job, profile)

    print("\n" + "=" * 85)
    print(f"[{args.user.upper()}] MATCH #{job['id']}: {job['title']}")
    print(f"Company:  {job['company']} | Source: {job['source']}")
    print(f"Location: {job['location']} ({job['remote_type']}) | URL: {job['job_url']}")
    print("-" * 85)
    print(f"MATCH SCORE: {job['match_score']} / 100")
    print(f"Explanation: {job['score_rationale']}")
    print("-" * 85)
    print("GAP ANALYSIS:")
    for m in gap["direct_matches"]:
        print(f"  [+] {m}")
    for g in gap["identified_gaps"]:
        print(f"  [!] {g}")
    print("=" * 85)


def cmd_prepare(args):
    init_db()
    user = get_user_by_slug(args.user)
    if not user:
        print(f"Unknown user '{args.user}'.")
        return
    try:
        pkg = prepare_user_application_package(user["id"], user["id"], args.job_id, enforce_verification_gate=True)
        print(f"\nPrepared application in private vault for {user['full_name']} (Match #{args.job_id}):")
        print(f"  CV Version Tracked: {pkg['cv_version_label']} (Vault Doc ID #{pkg['cv_document_id']})")
        print(f"  Cover Letter Doc ID: #{pkg['cover_letter_document_id']}")
        print("  Pipeline Status set to: awaiting_approval")
    except VerificationGateLockedError as ve:
        print(f"\n[VERIFICATION GATE BLOCKED] {ve}")


def cmd_update(args):
    init_db()
    ok = update_job_status(
        job_id=args.job_id,
        status=args.status,
        notes=args.notes,
        follow_up_date=args.follow_up,
        user_slug=args.user,
    )
    print(f"Updated #{args.job_id} -> {args.status}" if ok else "Match ID not found.")


def cmd_stats(args):
    init_db()
    for slug in ([args.user] if args.user != "all" else ["justin", "isil", "lindsey"]):
        stats = get_dashboard_stats(user_slug=slug)
        print(f"\n=== PIPELINE STATS: {slug.upper()} ===")
        for k, v in stats.items():
            print(f"  {k:<26}: {v}")


def cmd_backup(_args):
    path = create_platform_backup()
    print(f"Platform backup created at: {path}")


def main():
    parser = argparse.ArgumentParser(description="Multi-User AI Recruitment Platform CLI")
    parser.add_argument("--user", default="justin", choices=["justin", "isil", "lindsey", "all"], help="Target user workspace")
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="Run multi-platform job discovery")
    p_scan.add_argument("--fast", action="store_true")

    p_list = sub.add_parser("list", help="List user's matched vacancies")
    p_list.add_argument("--min-score", type=int, default=70)
    p_list.add_argument("--status", type=str, default="all")
    p_list.add_argument("--location", type=str, default=None)
    p_list.add_argument("--category", type=str, default="all")
    p_list.add_argument("--limit", type=int, default=25)

    p_ins = sub.add_parser("inspect", help="Inspect vacancy details and gap analysis")
    p_ins.add_argument("job_id", type=int)

    p_prep = sub.add_parser("prepare", help="Prepare tailored CV, cover letter, Q&A & interview prep")
    p_prep.add_argument("job_id", type=int)

    p_upd = sub.add_parser("update", help="Update match status")
    p_upd.add_argument("job_id", type=int)
    p_upd.add_argument("status", choices=["discovered", "saved", "awaiting_approval", "ready_to_apply", "applied", "interviewing", "rejected", "archived"])
    p_upd.add_argument("--notes", type=str, default=None)
    p_upd.add_argument("--follow-up", type=str, default=None)

    sub.add_parser("stats", help="View user pipeline statistics")
    sub.add_parser("backup", help="Create compressed backup of database and vaults")
    sub.add_parser("dashboard", help="Launch multi-user web portal")

    args = parser.parse_args()
    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "inspect":
        cmd_inspect(args)
    elif args.command == "prepare":
        cmd_prepare(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "backup":
        cmd_backup(args)
    elif args.command == "dashboard":
        from job_assistant.dashboard.app import run_dashboard
        run_dashboard()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
