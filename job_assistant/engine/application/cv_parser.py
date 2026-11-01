"""
CV Upload Reader & Structured Skill/Profile Extractor.
Supports .pdf (via pypdf), .docx (via python-docx), .md, and .txt files.
Stores uploaded files inside the user's strictly isolated VaultStorage.
Never invents facts—extracted items are returned as structured candidates for user confirmation.
"""

import io
import os
import re
from typing import Dict, Any, List, Optional

from job_assistant.engine.security import VaultStorage
from job_assistant.engine.db import register_user_document


KNOWN_SKILL_PATTERNS = [
    "SAP", "VA32", "Salesforce", "Zendesk", "Jira", "Confluence", "Intercom",
    "iCIMS", "OnBase", "Workday", "HubSpot", "Freshdesk", "Microsoft Excel",
    "Order Management", "Export Documentation", "Supply Chain", "Cold Chain",
    "Customer Support", "Customer Success", "Customer Onboarding", "Customer Experience",
    "Player Operations", "AML", "Anti-Money Laundering", "Responsible Gambling",
    "KYC", "EDD", "CDD", "Fraud Prevention", "Fraud Investigation", "Chargebacks",
    "Payments Operations", "Risk Management", "Compliance", "Quality Assurance",
    "Team Leadership", "English Teaching", "Translation", "Localization"
]


def extract_text_from_bytes(filename: str, content: bytes) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    elif ext == ".docx":
        from docx import Document
        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()
    elif ext in (".txt", ".md"):
        return content.decode("utf-8", errors="replace").strip()
    else:
        raise ValueError(f"Unsupported CV format '{ext}'. Please upload PDF, DOCX, Markdown, or TXT.")


def parse_cv_insights(extracted_text: str) -> Dict[str, Any]:
    """Extracts contact info and detected skills/keywords present verbatim in the uploaded CV."""
    emails = list(dict.fromkeys(re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", extracted_text)))
    phones = list(dict.fromkeys(re.findall(r"\+?\d[\d\s().-]{7,}\d", extracted_text)))

    detected_skills: List[str] = []
    lower_text = extracted_text.lower()
    for skill in KNOWN_SKILL_PATTERNS:
        if skill.lower() in lower_text:
            detected_skills.append(skill)

    year_ranges = list(dict.fromkeys(re.findall(
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\s*[-–—to]+\s*(?:Present|Current|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|\d{4})\b",
        extracted_text,
        flags=re.IGNORECASE
    )))

    return {
        "emails_found": emails[:3],
        "phones_found": [p.strip() for p in phones[:3]],
        "detected_skills": detected_skills,
        "detected_date_ranges": year_ranges[:15],
        "character_count": len(extracted_text),
        "preview": extracted_text[:1200]
    }


def upload_and_parse_user_cv(
    acting_user_id: int,
    owner_user_id: int,
    filename: str,
    content: bytes,
    set_as_master: bool = True,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Saves an uploaded CV to the owner's private vault, extracts text & verbatim skills,
    and registers the document version in SQLite.
    """
    extracted = extract_text_from_bytes(filename, content)
    vault = VaultStorage()
    storage_key = vault.save_bytes(acting_user_id, owner_user_id, filename, content, subfolder="uploaded_cvs")
    doc_kind = "master_cv" if set_as_master else "uploaded_cv"
    version_label = f"Uploaded {'Master ' if set_as_master else ''}CV ({VaultStorage.sanitize_filename(filename)})"

    kwargs: Dict[str, Any] = {}
    if db_path:
        kwargs["db_path"] = db_path

    doc_id = register_user_document(
        acting_user_id=acting_user_id,
        owner_user_id=owner_user_id,
        doc_kind=doc_kind,
        version_label=version_label,
        filename=VaultStorage.sanitize_filename(filename),
        storage_key=storage_key,
        extracted_text=extracted,
        **kwargs
    )
    insights = parse_cv_insights(extracted)
    return {
        "document_id": doc_id,
        "version_label": version_label,
        "insights": insights
    }
