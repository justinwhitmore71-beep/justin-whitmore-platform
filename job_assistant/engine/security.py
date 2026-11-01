"""
Authentication, Cryptography, Tenant Access Control, and Isolated Document Vault.
Supports:
- Local scrypt password hashing (Werkzeug) + signed session validation + CSRF tokens
- Single-use hashed password recovery tokens with expiration
- Optional Firebase Authentication JWT verification for Cloud Run / Firebase deployments
- Strict per-user isolated VaultStorage preventing cross-user file access or path traversal
"""

import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from werkzeug.security import generate_password_hash, check_password_hash


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT_ROOT = os.path.join(BASE_DIR, "data", "vault")
BROWSER_PROFILES_ROOT = os.path.join(BASE_DIR, "data", "browser_profiles")


class AccessDeniedError(PermissionError):
    """Raised when a user or administrator attempts unauthorized cross-tenant access."""
    pass


class VerificationGateLockedError(PermissionError):
    """Raised when trying to generate live applications for an unverified user profile."""
    pass


def hash_password(plain_password: str) -> str:
    if not plain_password or len(plain_password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    return generate_password_hash(plain_password, method="scrypt")


def verify_password(plain_password: str, password_hash: str) -> bool:
    if not plain_password or not password_hash:
        return False
    return check_password_hash(password_hash, plain_password)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf_token(session_token: Optional[str], provided_token: Optional[str]) -> bool:
    if not session_token or not provided_token:
        return False
    return hmac.compare_digest(session_token, provided_token)


def generate_recovery_token() -> tuple[str, str, str]:
    """
    Generates a password recovery token.
    Returns (raw_token_for_user, sha256_hash_for_db, expires_at_iso).
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    return raw_token, token_hash, expires_at


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def verify_firebase_id_token(id_token: str) -> Optional[Dict[str, Any]]:
    """
    Verifies a Firebase Authentication JWT when deployed with FIREBASE_AUTH_ENABLED=1.
    Requires firebase-admin initialized in the cloud environment.
    """
    if os.environ.get("FIREBASE_AUTH_ENABLED") != "1":
        return None
    try:
        from firebase_admin import auth as fb_auth  # type: ignore
        decoded = fb_auth.verify_id_token(id_token, check_revoked=True)
        return {
            "uid": decoded.get("uid"),
            "email": decoded.get("email"),
            "email_verified": decoded.get("email_verified", False),
        }
    except Exception:
        return None


class VaultStorage:
    """
    Strictly isolated per-user document vault.
    Local mode stores files under job_assistant/data/vault/user_<id>/ (outside Flask static/).
    Cloud mode (STORAGE_BACKEND=gcs) delegates to Google Cloud / Firebase Storage bucket with per-user prefixes.
    """

    def __init__(self, vault_root: str = VAULT_ROOT):
        self.vault_root = os.path.abspath(vault_root)
        os.makedirs(self.vault_root, exist_ok=True)
        self.backend = os.environ.get("STORAGE_BACKEND", "local").lower()
        self.gcs_bucket_name = os.environ.get("GCS_VAULT_BUCKET", "")

    def _user_dir(self, user_id: int) -> str:
        if not isinstance(user_id, int) or user_id <= 0:
            raise AccessDeniedError("Invalid user_id for vault access.")
        user_dir = os.path.abspath(os.path.join(self.vault_root, f"user_{user_id}"))
        if os.path.commonpath([self.vault_root, user_dir]) != self.vault_root:
            raise AccessDeniedError("Vault directory traversal blocked.")
        os.makedirs(user_dir, exist_ok=True)
        return user_dir

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        base = os.path.basename(filename or "document.txt")
        cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
        return cleaned[:120] or "document.txt"

    def save_bytes(self, acting_user_id: int, owner_user_id: int, filename: str, content: bytes, subfolder: str = "") -> str:
        """
        Saves bytes into owner_user_id's private vault.
        Enforces strict ownership: acting_user_id MUST equal owner_user_id.
        Returns relative storage_key within the vault.
        """
        if acting_user_id != owner_user_id:
            raise AccessDeniedError("Cross-user vault write denied.")

        safe_name = self.sanitize_filename(filename)
        safe_sub = re.sub(r"[^a-zA-Z0-9_-]", "_", subfolder) if subfolder else ""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        unique_name = f"{ts}_{secrets.token_hex(3)}_{safe_name}"

        user_root = self._user_dir(owner_user_id)
        target_dir = os.path.abspath(os.path.join(user_root, safe_sub)) if safe_sub else user_root
        if os.path.commonpath([user_root, target_dir]) != user_root:
            raise AccessDeniedError("Subfolder traversal blocked.")
        os.makedirs(target_dir, exist_ok=True)

        full_path = os.path.abspath(os.path.join(target_dir, unique_name))
        if os.path.commonpath([user_root, full_path]) != user_root:
            raise AccessDeniedError("File path traversal blocked.")

        storage_key = f"user_{owner_user_id}/" + (f"{safe_sub}/{unique_name}" if safe_sub else unique_name)

        if self.backend == "gcs" and self.gcs_bucket_name:
            from google.cloud import storage  # type: ignore
            client = storage.Client()
            bucket = client.bucket(self.gcs_bucket_name)
            blob = bucket.blob(storage_key)
            blob.upload_from_string(content)
            return storage_key

        with open(full_path, "wb") as f:
            f.write(content)
        return storage_key

    def save_text(self, acting_user_id: int, owner_user_id: int, filename: str, text: str, subfolder: str = "") -> str:
        return self.save_bytes(acting_user_id, owner_user_id, filename, text.encode("utf-8"), subfolder=subfolder)

    def read_bytes(
        self,
        acting_user_id: int,
        owner_user_id: int,
        storage_key: str,
        has_explicit_assistance_grant: bool = False
    ) -> bytes:
        """
        Reads bytes from owner_user_id's private vault.
        Strictly denies access unless acting_user_id == owner_user_id OR owner explicitly granted assistance permission.
        """
        if acting_user_id != owner_user_id and not has_explicit_assistance_grant:
            raise AccessDeniedError("Access denied to another user's private document vault.")

        expected_prefix = f"user_{owner_user_id}/"
        normalized_key = storage_key.replace("\\", "/")
        if not normalized_key.startswith(expected_prefix):
            raise AccessDeniedError("Storage key does not belong to target user.")

        if self.backend == "gcs" and self.gcs_bucket_name:
            from google.cloud import storage  # type: ignore
            client = storage.Client()
            bucket = client.bucket(self.gcs_bucket_name)
            blob = bucket.blob(normalized_key)
            return blob.download_as_bytes()

        user_root = self._user_dir(owner_user_id)
        rel_inside_user = normalized_key[len(expected_prefix):]
        full_path = os.path.abspath(os.path.join(user_root, rel_inside_user))
        if os.path.commonpath([user_root, full_path]) != user_root:
            raise AccessDeniedError("Vault read traversal blocked.")
        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"Vault document not found: {storage_key}")

        with open(full_path, "rb") as f:
            return f.read()

    def read_text(
        self,
        acting_user_id: int,
        owner_user_id: int,
        storage_key: str,
        has_explicit_assistance_grant: bool = False
    ) -> str:
        return self.read_bytes(acting_user_id, owner_user_id, storage_key, has_explicit_assistance_grant).decode("utf-8")

    def resolve_local_path_for_upload(self, acting_user_id: int, owner_user_id: int, storage_key: str) -> str:
        """Returns local filesystem path for isolated Playwright CV upload (owner only)."""
        if acting_user_id != owner_user_id:
            raise AccessDeniedError("Cannot resolve another user's CV file for browser upload.")
        expected_prefix = f"user_{owner_user_id}/"
        normalized_key = storage_key.replace("\\", "/")
        if not normalized_key.startswith(expected_prefix):
            raise AccessDeniedError("Storage key mismatch.")
        user_root = self._user_dir(owner_user_id)
        full_path = os.path.abspath(os.path.join(user_root, normalized_key[len(expected_prefix):]))
        if os.path.commonpath([user_root, full_path]) != user_root:
            raise AccessDeniedError("Path traversal blocked.")
        return full_path


def get_isolated_browser_profile_dir(acting_user_id: int, owner_user_id: int) -> str:
    """
    Returns a dedicated, isolated browser profile folder per user so cookies,
    localStorage, and ATS sessions are NEVER shared across accounts.
    """
    if acting_user_id != owner_user_id:
        raise AccessDeniedError("Cross-user browser session access is strictly prohibited.")
    root = os.path.abspath(BROWSER_PROFILES_ROOT)
    os.makedirs(root, exist_ok=True)
    profile_dir = os.path.abspath(os.path.join(root, f"user_{owner_user_id}_session"))
    if os.path.commonpath([root, profile_dir]) != root:
        raise AccessDeniedError("Invalid browser session directory.")
    os.makedirs(profile_dir, exist_ok=True)
    return profile_dir
