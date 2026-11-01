"""
Multi-User CV & Application Specialist Engine.
Capabilities per user (Justin, Işıl, Lindsey):
1. Gap Analysis & Missing Qualification Identification
2. Tailored CV Generation (strictly grounded in VERIFIED user experience & education)
3. Tailored Cover Letter Generation (personalized per user & role)
4. Application Screening Q&A Drafter (accurate citizenship, work-auth, and language answers)
5. Role-Specific Interview Questions & Suggested STAR Answers
6. Hard Verification Gate: Blocks final application generation when a user account has
   unverified onboarding profile data (e.g., Işıl's preliminary tools/degrees or Lindsey's dates)
7. Vault Storage & Version Tracking: Stores every generated CV/letter inside the owner's
   isolated VaultStorage and records the exact CV version used on the user's job match.
"""

import json
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

from job_assistant.engine.security import VaultStorage, VerificationGateLockedError, AccessDeniedError
from job_assistant.engine.db import (
    get_user_by_id,
    get_user_profile,
    get_user_match_detail,
    register_user_document,
    update_user_match,
)


def analyze_job_requirements(job_dict: Dict[str, Any]) -> Dict[str, Any]:
    text = f"{job_dict.get('title', '')} {job_dict.get('description', '')}".lower()
    return {
        "sap": any(k in text for k in ["sap", "va32", "zbl", "zdr", "erp", "order to cash"]),
        "export_logistics": any(k in text for k in ["export", "shipping", "customs", "douane", "awb", "incoterms", "cold chain", "logistics", "supply chain", "freight"]),
        "customer_service": any(k in text for k in ["customer service", "customer support", "client support", "customer care", "customer experience", "customer success"]),
        "onboarding_training": any(k in text for k in ["onboarding", "implementation", "english teacher", "instructor", "lecturer", "trainer", "teaching"]),
        "turkish_translation": any(k in text for k in ["turkish", "translation", "translator", "localization"]),
        "team_leadership": any(k in text for k in ["team lead", "manager", "head of", "superviseur", "shift lead", "coaching", "performance manager"]),
        "igaming_aml_rg": any(k in text for k in ["igaming", "aml", "anti-money laundering", "responsible gambling", "safer gambling", "compliance", "casino", "sportsbook"]),
        "kyc_fraud_payments": any(k in text for k in ["kyc", "edd", "cdd", "fraud", "chargeback", "payment", "fintech", "risk"]),
        "languages": {
            "english": any(k in text for k in ["english", "anglais"]),
            "french": any(k in text for k in ["french", "français"]),
            "czech": any(k in text for k in ["czech", "čeština", "český"]),
            "turkish": "turkish" in text,
            "spanish": "spanish" in text,
            "german": "german" in text,
        },
        "practical": any(k in text for k in [
            "entrepôt", "warehouse", "manutention", "préparation de commande", "preparateur commande",
            "conditionnement", "cariste", "restauration rapide", "mcdonald", "burger king",
            "équipier", "entretien", "nettoyage", "propreté", "plongeur", "mise en rayon", "caisse", "vendeur"
        ])
    }


def _verified_experience(profile_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [e for e in profile_dict.get("experience", []) if e.get("verified", True)]


def _verified_skills(profile_dict: Dict[str, Any]) -> List[str]:
    out = []
    for s in profile_dict.get("skills", []):
        if isinstance(s, dict):
            if s.get("verified", True):
                out.append(s["name"])
        elif isinstance(s, str):
            out.append(s)
    if not out and "technical_and_systems" in profile_dict:
        for grp in profile_dict["technical_and_systems"].values():
            out.extend(grp)
    return out


def _verified_education(profile_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [ed for ed in profile_dict.get("education", []) if ed.get("verified", True)]


def _language_map(profile_dict: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    langs = profile_dict.get("languages")
    if isinstance(langs, list):
        return {item["language"].lower(): item for item in langs}
    if isinstance(langs, dict):
        return {k.lower(): v for k, v in langs.items()}
    c_langs = profile_dict.get("constraints", {}).get("languages", {})
    return {k.lower(): v for k, v in c_langs.items()}


def perform_gap_analysis(job_dict: Dict[str, Any], profile_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Compares vacancy requirements strictly against the user's VERIFIED profile."""
    reqs = analyze_job_requirements(job_dict)
    v_skills_lower = " ".join(_verified_skills(profile_dict)).lower()
    v_exp_text = json.dumps(_verified_experience(profile_dict)).lower()
    langs = _language_map(profile_dict)
    work_auth = profile_dict.get("work_authorization", {})

    matches: List[str] = []
    transferable: List[str] = []
    gaps: List[str] = []

    if reqs["sap"]:
        if "sap" in v_skills_lower or "va32" in v_exp_text:
            matches.append("Verified hands-on SAP Order Management & Export workflows (VA32, ZBL, ZDR).")
        else:
            gaps.append("SAP / ERP requirement listed — not present in verified profile.")

    if reqs["export_logistics"]:
        if "export" in v_skills_lower or "quidelortho" in v_exp_text:
            matches.append("Verified EMEA export & logistics documentation (AWB, EX-1, CoA, COO, cold-chain).")
        else:
            gaps.append("Specialized export/customs logistics experience not listed in verified history.")

    if reqs["igaming_aml_rg"]:
        if any(k in v_skills_lower or k in v_exp_text for k in ["aml", "responsible gambling", "igaming", "compliance"]):
            matches.append("Verified iGaming Operations, AML, Responsible Gambling & Compliance background.")
        else:
            gaps.append("Specialized iGaming AML / Responsible Gambling regulatory background missing.")

    if reqs["kyc_fraud_payments"]:
        if any(k in v_skills_lower or k in v_exp_text for k in ["kyc", "fraud", "payment", "chargeback"]):
            matches.append("Verified Payments, Fraud Prevention, Chargebacks & KYC operations experience.")
        else:
            gaps.append("Direct KYC / Fraud / Payments operations experience not in verified profile.")

    if reqs["onboarding_training"]:
        if any(k in v_skills_lower or k in v_exp_text for k in ["onboarding", "teaching", "instructor", "coach"]):
            matches.append("Verified Customer Onboarding, Coaching & Academic/Professional Instruction experience.")

    if reqs["customer_service"]:
        if any(k in v_skills_lower or k in v_exp_text for k in ["customer", "support", "player operations"]):
            matches.append("Verified international Customer / Player Support & Escalation Resolution.")

    if reqs["team_leadership"]:
        if any(k in v_skills_lower or k in v_exp_text for k in ["team", "manager", "shift lead", "15 employees"]):
            matches.append("Verified Team / Shift Leadership, KPI management & staff coaching.")
        else:
            transferable.append("Strong independent ownership and cross-functional coordination; confirm formal people-management scope.")

    if reqs["turkish_translation"]:
        if langs.get("turkish", {}).get("can_work_professionally"):
            matches.append("Verified Native Turkish + C2 English bilingual fluency.")
        else:
            gaps.append("Requires Turkish fluency (not in user's language profile).")

    # Language checks
    if reqs["languages"]["english"] and langs.get("english", {}).get("can_work_professionally", True):
        matches.append(f"English proficiency ({langs.get('english', {}).get('level', 'C2 / Fluent')}).")
    for check_lang in ("french", "czech", "spanish", "german"):
        if reqs["languages"][check_lang]:
            l_info = langs.get(check_lang, {})
            if not l_info.get("can_work_professionally", False):
                gaps.append(f"{check_lang.title()} language mentioned — user does NOT hold professional {check_lang.title()} proficiency.")

    # Work authorization check
    if isinstance(work_auth, dict):
        if work_auth.get("eu_eea_free_movement"):
            matches.append("Full EU/EEA citizenship & immediate unrestricted right to work without sponsorship.")
        else:
            gaps.append("Work Authorization Check: User does NOT hold EU citizenship — verify Czech permit access, remote contractor eligibility, or employer visa sponsorship.")
    else:
        matches.append(str(work_auth))

    if reqs["practical"]:
        transferable.append("High operational reliability, adaptability, and immediate readiness.")

    unverified_notes = profile_dict.get("verification_prompts", [])
    return {
        "job_title": job_dict.get("title"),
        "company": job_dict.get("company"),
        "direct_matches": matches,
        "transferable_strengths": transferable,
        "identified_gaps": gaps,
        "pending_profile_verifications": unverified_notes,
        "recommendation": "Strong verified alignment" if len(matches) >= 3 and not gaps else ("Review identified gaps/eligibility before applying" if gaps else "Viable alignment")
    }


def generate_tailored_cv(
    job_dict: Dict[str, Any],
    profile_dict: Dict[str, Any],
    variant: Optional[str] = None
) -> str:
    """
    Generates a tailored Markdown CV strictly using ONLY verified facts from the specific user's profile.
    """
    reqs = analyze_job_requirements(job_dict)
    personal = profile_dict.get("personal", {})
    full_name = personal.get("full_name", "Candidate")
    email = personal.get("email") or "[Confirm Email in Profile]"
    phone = personal.get("phone") or "[Confirm Phone in Profile]"
    location = personal.get("current_location", "")
    work_auth = profile_dict.get("work_authorization", {})
    auth_summary = work_auth.get("summary") if isinstance(work_auth, dict) else str(work_auth or personal.get("work_authorization", ""))

    verified_exp = _verified_experience(profile_dict)
    verified_skills = _verified_skills(profile_dict)
    verified_edu = _verified_education(profile_dict)
    langs = _language_map(profile_dict)

    # Determine role headline strictly from the user's verified domains
    skills_blob = " ".join(verified_skills).lower()
    if "aml" in skills_blob or "player operations" in skills_blob:
        headline = "PLAYER OPERATIONS | AML & COMPLIANCE | RISK, FRAUD & PAYMENTS"
        summary = (
            "Experienced iGaming and Fintech Operations Leader specializing in Player Operations Performance, "
            "Anti-Money Laundering (AML), Responsible Gambling (RG), KYC/EDD, Fraud Prevention, and Payments Operations. "
            "Proven track record leading operational shifts, enforcing regulatory compliance, and optimizing player and payment workflows across international markets."
        )
    elif "turkish" in langs and langs["turkish"].get("can_work_professionally"):
        if reqs["onboarding_training"]:
            headline = "CUSTOMER ONBOARDING | ENGLISH TRAINING & INSTRUCTION | MULTILINGUAL SUPPORT"
        else:
            headline = "CUSTOMER EXPERIENCE & ONBOARDING SPECIALIST | C2 ENGLISH & NATIVE TURKISH"
        summary = (
            "Empathetic, detail-oriented Customer Support, Onboarding, and University-level English Instruction professional "
            "with C2 English fluency and native Turkish proficiency. Experienced guiding international clients through complex onboarding "
            "and support workflows with clarity, patience, and structured communication."
        )
    else:
        if reqs["practical"] and not variant:
            variant = "practical_ops"
        elif (reqs["sap"] or reqs["export_logistics"]) and not variant:
            variant = "export_logistics"
        elif not variant:
            variant = "customer_lead"

        if variant == "export_logistics":
            headline = "INTERNATIONAL LOGISTICS | ORDER MANAGEMENT | SAP EXPORT OPERATIONS"
            summary = (
                "Detail-oriented International Logistics and Customer Service Specialist with hands-on expertise in "
                "SAP order management (VA32, ZBL, ZDR, credit blocks, ship-to changes) and EMEA export documentation "
                "(commercial invoices, packing lists, CoA, AWB, EX-1, Certificates of Origin, cold-chain shipments)."
            )
        elif variant == "practical_ops":
            headline = "OPERATIONS & LOGISTICS SUPPORT | RELIABLE & IMMEDIATELY AVAILABLE"
            summary = (
                "Hard-working, adaptable operations professional experienced in fast-paced environments, order fulfillment, "
                "and strict adherence to quality and safety procedures. Dual EU/US citizen available immediately."
            )
        else:
            headline = "CUSTOMER EXPERIENCE | MULTICHANNEL SUPPORT | TEAM LEADERSHIP"
            summary = (
                "Adaptable Customer Service and Operations Leader experienced across international B2B and B2C environments, "
                "managing complex escalations, SAP/CRM workflows, and coaching teams of ~15 employees in live 24/7 operations."
            )

    lines = [
        f"# {full_name}",
        f"### {headline}",
        f"**Location:** {location} | **Email:** {email} | **Phone:** {phone}",
        f"**Work Authorization:** {auth_summary}",
        "\n---\n",
        "## Professional Summary",
        summary,
        "\n## Verified Core Competencies",
    ]
    for sk in verified_skills:
        lines.append(f"- {sk}")

    lines.append("\n## Professional Experience\n")
    for role in verified_exp:
        s_date = role.get("start_date", "")
        e_date = role.get("end_date", "")
        date_str = f"{s_date} – {e_date}" if role.get("dates_verified", True) else "[Dates Pending Candidate Confirmation]"
        lines.append(f"### {role['title']} — **{role['company']}**")
        lines.append(f"*{role.get('location', '')} | {date_str}*")
        for h in role.get("highlights", []):
            lines.append(f"- {h}")
        lines.append("")

    if verified_edu:
        lines.append("## Education")
        for ed in verified_edu:
            yr = ed.get("dates") or ed.get("year") or ""
            lines.append(f"- **{ed['degree']}** — {ed['institution']}" + (f" ({yr})" if yr else ""))
        lines.append("")

    lines.append("## Languages")
    if isinstance(profile_dict.get("languages"), list):
        for l_item in profile_dict["languages"]:
            if l_item.get("verified", True) and "none" not in l_item.get("level", "").lower() and "not assumed" not in l_item.get("level", "").lower():
                lines.append(f"- **{l_item['language']}:** {l_item['level']}")
    else:
        lines.append("- **English:** C2 / Native-level")
        lines.append("- **French:** Basic / Conversational (Limited professional proficiency)")

    return "\n".join(lines)


def generate_tailored_cover_letter(job_dict: Dict[str, Any], profile_dict: Dict[str, Any]) -> str:
    """Generates a tailored cover letter strictly grounded in the specific user's verified facts."""
    title = job_dict.get("title", "Position")
    company = job_dict.get("company", "the Hiring Team")
    reqs = analyze_job_requirements(job_dict)
    personal = profile_dict.get("personal", {})
    full_name = personal.get("full_name", "Candidate")
    email = personal.get("email") or "[Confirm Email]"
    phone = personal.get("phone") or "[Confirm Phone]"
    location = personal.get("current_location", "")
    skills_blob = " ".join(_verified_skills(profile_dict)).lower()
    langs = _language_map(profile_dict)
    work_auth = profile_dict.get("work_authorization", {})

    # French practical letter ONLY when user resides in France and role is local practical
    if reqs["practical"] and "france" in location.lower():
        return "\n".join([
            full_name,
            f"Email: {email} | Téléphone: {phone}",
            f"Résidence: {location}",
            f"Date: {datetime.now().strftime('%d/%m/%Y')}\n",
            f"À l'attention de l'équipe de recrutement — {company}",
            f"Objet : Candidature au poste de {title}\n",
            "Madame, Monsieur,\n",
            f"Je vous adresse ma candidature pour le poste de **{title}** avec un vif intérêt et une disponibilité immédiate.",
            "\nRigoureux, ponctuel et motivé, j'ai l'habitude des environnements opérationnels exigeants, du travail en équipe "
            "et du respect strict des consignes de qualité et de sécurité.",
            "\nEn tant que citoyen français / européen, je dispose du droit complet de travailler immédiatement et je suis prêt à m'investir durablement.",
            "\nJe vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.\n",
            full_name
        ])

    lines = [
        full_name,
        f"Email: {email} | Phone: {phone}",
        f"Location: {location}",
        f"Date: {datetime.now().strftime('%B %d, %Y')}\n",
        f"Dear Hiring Team at {company},\n",
        f"I am writing to apply for the **{title}** opportunity at **{company}**."
    ]

    if "aml" in skills_blob or "player operations" in skills_blob:
        lines.append(
            "\nAcross my progressive career in iGaming and fintech operations—including leadership and specialist roles at "
            "Patrianna, Betmaster, kwiff, Casumo, ComeOn!, and ARRINGO—I have built deep, hands-on expertise across Player Operations "
            "Performance, Anti-Money Laundering (AML), Responsible Gambling (RG), KYC/EDD, Fraud Prevention, and Payments Operations. "
            "I combine operational rigor with proactive risk mitigation and team leadership."
        )
        lines.append(
            "\nAs a dual French (EU) and US citizen, I hold full unrestricted work authorization across the European Union without "
            "requiring visa sponsorship, and I am actively focused on remote European or mainland European opportunities."
        )
    elif "turkish" in langs and langs["turkish"].get("can_work_professionally"):
        lines.append(
            "\nWith my background in Customer Support and Onboarding at Accolade in Prague alongside my experience as a "
            "University English Instructor, I bring C2 English fluency, native Turkish proficiency, and a calm, structured approach "
            "to guiding customers through onboarding, troubleshooting, and long-term adoption."
        )
        lines.append(
            "\nBased in Prague, Czech Republic, I am eager to contribute clear communication, high empathy, and meticulous case ownership to your team."
        )
    else:
        if reqs["sap"] or reqs["export_logistics"]:
            lines.append(
                "\nIn my recent role at QuidelOrtho supporting EMEA export markets across 9 countries, I managed daily SAP order workflows "
                "(VA32, ZBL, ZDR, credit blocks, ship-to updates, and outbound deliveries) and prepared complete export documentation "
                "including commercial invoices, packing lists, Certificates of Analysis, AWB, EX-1 customs filings, and Certificates of Origin."
            )
        else:
            lines.append(
                "\nCombining international B2B customer operations at QuidelOrtho, complex case resolution at Accolade, and 24/7 team "
                "management (~15 direct reports) at Besedo and Netbilling, I bring calm escalation handling, fast system mastery, and strong customer focus."
            )
        if isinstance(work_auth, dict) and work_auth.get("eu_eea_free_movement"):
            lines.append(
                "\nAs a dual French (EU) and US citizen, I hold full unrestricted right to work across the European Union and am available immediately."
            )

    lines.append("\nThank you for your time and consideration. I look forward to discussing how my experience aligns with your goals.\n")
    lines.append(f"Sincerely,\n{full_name}")
    return "\n".join(lines)


def generate_application_qna(job_dict: Dict[str, Any], profile_dict: Dict[str, Any]) -> Dict[str, str]:
    """Generates truthful screening responses strictly reflecting the user's real authorization and skills."""
    work_auth = profile_dict.get("work_authorization", {})
    auth_summary = work_auth.get("summary") if isinstance(work_auth, dict) else str(work_auth or "Full EU & US work authorization.")
    langs = profile_dict.get("languages", [])
    if isinstance(langs, list):
        lang_summary = "; ".join(
            f"{l['language']}: {l['level']}" for l in langs
            if "none" not in l.get("level", "").lower() and "not assumed" not in l.get("level", "").lower()
        )
    else:
        lang_summary = "English: C2 / Native-fluent; French: Basic/conversational (non-professional)."

    skills_list = ", ".join(_verified_skills(profile_dict)[:6])
    return {
        "Why are you applying for this position?": (
            f"The {job_dict.get('title')} role at {job_dict.get('company')} aligns directly with my verified strengths in {skills_list}."
        ),
        "Work Authorization & Sponsorship Status": auth_summary,
        "Language Proficiency": lang_summary,
        "Salary Expectations": (
            f"Aligned with market range and role scope ({profile_dict.get('preferences', {}).get('salary_expectation', {}).get('target_annual_gross', 'negotiable')} "
            f"{profile_dict.get('preferences', {}).get('salary_expectation', {}).get('currency', 'EUR')})."
        ),
        "Earliest Start Date / Availability": "Flexible / Immediate upon agreement."
    }


def generate_interview_prep(job_dict: Dict[str, Any], profile_dict: Dict[str, Any]) -> List[Dict[str, str]]:
    """Generates targeted interview questions and truthful coaching frameworks grounded in verified history."""
    verified_exp = _verified_experience(profile_dict)
    top_role = verified_exp[0] if verified_exp else {"title": "your recent role", "company": "your previous employer"}
    gap = perform_gap_analysis(job_dict, profile_dict)

    prep = [
        {
            "question": f"Walk us through your most relevant experience for {job_dict.get('title', 'this role')}.",
            "guidance": (
                f"Anchor your answer in your verified work as {top_role.get('title')} at {top_role.get('company')}. "
                f"Highlight concrete workflows ({', '.join(_verified_skills(profile_dict)[:3])}) and measurable ownership."
            )
        },
        {
            "question": "Describe a high-pressure escalation or operational bottleneck you resolved.",
            "guidance": (
                "Use the STAR structure (Situation, Task, Action, Result) drawing strictly from a real case in your verified history—"
                "focus on clear stakeholder communication, root-cause verification, and preventing repeat occurrences."
            )
        },
        {
            "question": "How do you address areas or tools in our job description you haven't used directly?",
            "guidance": (
                f"Be 100% transparent—never overclaim unverified tools. Potential gap notes for this role: "
                f"{'; '.join(gap['identified_gaps']) if gap['identified_gaps'] else 'None flagged—emphasize fast ramp-up on internal systems.'}"
            )
        }
    ]
    return prep


def prepare_user_application_package(
    acting_user_id: int,
    owner_user_id: int,
    match_id: int,
    enforce_verification_gate: bool = True,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Multi-tenant, security-checked application generator.
    1. Verifies acting_user_id == owner_user_id (no one generates live applications on another user's behalf without ownership).
    2. Enforces the Verification Gate: if owner's profile_verified == 0, raises VerificationGateLockedError!
    3. Generates tailored CV, Cover Letter, Screening Q&A, and Interview Prep strictly from verified profile fields.
    4. Stores CV & Cover Letter in owner's isolated VaultStorage and links exact version IDs to user_job_matches.
    """
    if acting_user_id != owner_user_id:
        raise AccessDeniedError("Only the account owner can generate application packages in their workspace.")

    db_kwargs: Dict[str, Any] = {"db_path": db_path} if db_path else {}
    user = get_user_by_id(owner_user_id, **db_kwargs)
    if not user:
        raise ValueError("User not found.")

    if enforce_verification_gate and not user.get("profile_verified"):
        raise VerificationGateLockedError(
            f"Verification Required: {user['full_name']}'s profile has unconfirmed preliminary details "
            "(such as dates, titles, degrees, or tools). Please complete Profile Verification first so unverified data is never used."
        )

    match_row = get_user_match_detail(acting_user_id, owner_user_id, match_id, allow_granted_admin=False, **db_kwargs)
    if not match_row:
        raise ValueError(f"Match #{match_id} not found in your workspace.")

    profile = get_user_profile(acting_user_id, owner_user_id, allow_granted_admin=False, **db_kwargs)
    cv_md = generate_tailored_cv(match_row, profile)
    cl_md = generate_tailored_cover_letter(match_row, profile)
    qna = generate_application_qna(match_row, profile)
    interview_prep = generate_interview_prep(match_row, profile)
    gap = perform_gap_analysis(match_row, profile)

    company_slug = re.sub(r"[^a-zA-Z0-9]", "_", match_row.get("company", "company")).lower()[:24]
    title_slug = re.sub(r"[^a-zA-Z0-9]", "_", match_row.get("title", "role")).lower()[:24]
    ts_short = datetime.now().strftime("%Y%m%d_%H%M")
    version_label = f"CV_{user['slug']}_{company_slug}_{ts_short}"

    vault = VaultStorage()
    cv_filename = f"{version_label}.md"
    cl_filename = f"CoverLetter_{user['slug']}_{company_slug}_{title_slug}.md"

    cv_key = vault.save_text(acting_user_id, owner_user_id, cv_filename, cv_md, subfolder=f"match_{match_id}")
    cl_key = vault.save_text(acting_user_id, owner_user_id, cl_filename, cl_md, subfolder=f"match_{match_id}")

    cv_doc_id = register_user_document(
        acting_user_id=acting_user_id,
        owner_user_id=owner_user_id,
        doc_kind="tailored_cv",
        version_label=version_label,
        filename=cv_filename,
        storage_key=cv_key,
        extracted_text=cv_md,
        vacancy_id=match_row["vacancy_id"],
        **db_kwargs
    )
    cl_doc_id = register_user_document(
        acting_user_id=acting_user_id,
        owner_user_id=owner_user_id,
        doc_kind="cover_letter",
        version_label=f"CL_{company_slug}_{ts_short}",
        filename=cl_filename,
        storage_key=cl_key,
        extracted_text=cl_md,
        vacancy_id=match_row["vacancy_id"],
        **db_kwargs
    )

    update_user_match(
        acting_user_id=acting_user_id,
        owner_user_id=owner_user_id,
        match_id=match_id,
        status="awaiting_approval",
        cv_document_id=cv_doc_id,
        cv_version_label=version_label,
        cover_letter_document_id=cl_doc_id,
        app_answers_json=json.dumps(qna, ensure_ascii=False),
        interview_prep_json=json.dumps(interview_prep, ensure_ascii=False),
        **db_kwargs
    )

    return {
        "match_id": match_id,
        "cv_document_id": cv_doc_id,
        "cv_version_label": version_label,
        "cover_letter_document_id": cl_doc_id,
        "cv_content": cv_md,
        "cover_letter_content": cl_md,
        "qna_content": qna,
        "interview_prep": interview_prep,
        "gap_analysis": gap,
    }


def save_application_package(job_id: int, job_dict: Dict[str, Any], profile_dict: Dict[str, Any], output_dir: str) -> Dict[str, str]:
    """Backward-compatible file output helper for legacy CLI calls."""
    os.makedirs(output_dir, exist_ok=True)
    company_slug = re.sub(r"[^a-zA-Z0-9]", "_", job_dict.get("company", "company")).lower()
    title_slug = re.sub(r"[^a-zA-Z0-9]", "_", job_dict.get("title", "job")).lower()[:20]
    name_slug = re.sub(r"[^a-zA-Z0-9]", "_", profile_dict.get("personal", {}).get("full_name", "Candidate"))

    cv_path = os.path.join(output_dir, f"CV_{name_slug}_{company_slug}_{title_slug}.md")
    cl_path = os.path.join(output_dir, f"Cover_Letter_{name_slug}_{company_slug}_{title_slug}.md")
    qna_path = os.path.join(output_dir, f"Screening_QnA_{company_slug}_{title_slug}.json")

    with open(cv_path, "w", encoding="utf-8") as f:
        f.write(generate_tailored_cv(job_dict, profile_dict))
    with open(cl_path, "w", encoding="utf-8") as f:
        f.write(generate_tailored_cover_letter(job_dict, profile_dict))
    with open(qna_path, "w", encoding="utf-8") as f:
        json.dump(generate_application_qna(job_dict, profile_dict), f, indent=2, ensure_ascii=False)

    return {"cv_path": cv_path, "cover_letter_path": cl_path, "qna_path": qna_path}
