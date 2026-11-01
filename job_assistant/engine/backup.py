"""
Automated Backup Procedure for Multi-User Recruitment Database & Private Vaults.
Creates timestamped compressed `.zip` snapshots of `jobs.db` and `vault/` safely using SQLite's online backup API.
"""

import os
import sqlite3
import zipfile
from datetime import datetime, timezone

from job_assistant.engine.db import DB_PATH, BASE_DIR
from job_assistant.engine.security import VAULT_ROOT


def create_platform_backup(db_path: str = DB_PATH, vault_root: str = VAULT_ROOT) -> str:
    backups_dir = os.path.join(BASE_DIR, "data", "backups")
    os.makedirs(backups_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tmp_db_snapshot = os.path.join(backups_dir, f"jobs_snapshot_{ts}.db")
    zip_path = os.path.join(backups_dir, f"platform_backup_{ts}.zip")

    if os.path.isfile(db_path):
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(tmp_db_snapshot)
        src.backup(dst)
        dst.close()
        src.close()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if os.path.isfile(tmp_db_snapshot):
            zf.write(tmp_db_snapshot, arcname="jobs.db")
        if os.path.isdir(vault_root):
            for root, _, files in os.walk(vault_root):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    rel = os.path.relpath(fpath, os.path.dirname(vault_root))
                    zf.write(fpath, arcname=rel)

    if os.path.isfile(tmp_db_snapshot):
        os.remove(tmp_db_snapshot)

    return zip_path
