"""
Intelligent Multi-User Job Scoring Engine (0 to 100).
Provides distinct, customizable scoring models for:
1. Justin Murrel Whitmore (CX, Support, Operations, SAP/Export, Logistics, Remote/EU + France stability option)
2. Işıl (Prague/Remote, English C2 & Native Turkish, Support/Onboarding/Teaching/Translation, non-EU work-auth checks)
3. Lindsey Whitmore (Leave-Malta Remote-First Europe Strategy, iGaming/Fintech Ops, AML, RG, KYC, Fraud, Payments)

Note: Every score measures alignment with verified profile, constraints, and user-customizable weights—
never an arbitrary claim of hiring probability.
"""

import json
import re
from typing import Dict, Any, List, Optional


SCORE_DISCLAIMER = (
    "Alignment index (0–100) based on verified profile, work authorization, and preferences "
    "(not an objective probability of hiring)."
)


EU_COUNTRIES = [
    "france", "portugal", "spain", "netherlands", "germany", "ireland", "cyprus",
    "czech republic", "czechia", "prague", "poland", "estonia", "italy", "belgium",
    "austria", "sweden", "denmark", "finland", "greece", "luxembourg", "romania",
    "bulgaria", "croatia", "slovakia", "slovenia", "lithuania", "latvia", "hungary"
]


def detect_scam_and_remote_traps(job_data: Dict[str, Any]) -> Dict[str, Any]:
    title = (job_data.get("title") or "").lower()
    desc = (job_data.get("description") or "").lower()
    loc = (job_data.get("location") or "").lower()
    remote_type = (job_data.get("remote_type") or "").lower()
    restrictions = (job_data.get("remote_country_restrictions") or "").lower()
    combined = f"{title} {loc} {restrictions} {desc}"

    scam_signals = []
    if any(s in combined for s in [
        "contact on telegram", "whatsapp only", "registration fee", "pay for training",
        "purchase equipment upfront", "usdt daily payout", "guaranteed $500/day"
    ]):
        scam_signals.append("Suspicious recruitment scam language detected")

    # Detect country-locked remote traps
    us_uk_locked = any(s in combined for s in [
        "us residents only", "usa only", "must reside in the us", "must be based in the uk",
        "uk residents only", "canada only", "australia only", "latam only"
    ])
    malta_locked_remote = any(s in combined for s in [
        "remote from malta", "must reside in malta", "based in malta only", "remote (malta)"
    ])
    misleading_remote = ("remote" in remote_type or "remote" in title) and any(s in desc for s in [
        "5 days in office", "100% on-site", "strictly office based", "no remote work"
    ])

    return {
        "is_scam_suspect": len(scam_signals) > 0,
        "scam_reasons": scam_signals,
        "us_uk_locked_remote": us_uk_locked,
        "malta_locked_remote": malta_locked_remote,
        "misleading_remote": misleading_remote
    }


def _scale_weighted_total(
    raw_parts: Dict[str, float],
    max_parts: Dict[str, float],
    weights: Dict[str, float],
    penalties: float
) -> int:
    """Computes custom-weighted 0–100 score from normalized category ratios minus penalties."""
    weight_sum = sum(max(0.0, float(v)) for v in weights.values())
    if weight_sum <= 0:
        weight_sum = 100.0

    weighted_points = 0.0
    for key, w in weights.items():
        max_val = max_parts.get(key, 1.0)
        got_val = max(0.0, min(max_val, float(raw_parts.get(key, 0.0))))
        ratio = got_val / max_val if max_val > 0 else 0.0
        weighted_points += ratio * (float(w) / weight_sum) * 100.0

    final = round(weighted_points - penalties)
    return max(0, min(100, int(final)))


# =============================================================================
# FOREIGN LANGUAGE REQUIREMENT GATE
# =============================================================================

FOREIGN_LANGUAGE_MAP = {
    "italian": "Italian", "italiano": "Italian",
    "german": "German", "deutsch": "German",
    "dutch": "Dutch", "nederlands": "Dutch",
    "spanish": "Spanish", "español": "Spanish",
    "portuguese": "Portuguese", "português": "Portuguese",
    "czech": "Czech", "český": "Czech", "čeština": "Czech",
    "polish": "Polish", "polski": "Polish",
    "swedish": "Swedish", "svenska": "Swedish",
    "danish": "Danish", "dansk": "Danish",
    "norwegian": "Norwegian", "norsk": "Norwegian",
    "finnish": "Finnish", "suomi": "Finnish",
    "greek": "Greek", "russian": "Russian",
    "hungarian": "Hungarian", "turkish": "Turkish", "türkçe": "Turkish",
    "french": "French", "français": "French",
    "english": "English"
}


def detect_foreign_language_barrier(
    title: str,
    desc: str,
    allowed_languages: List[str]
) -> Optional[Dict[str, str]]:
    """
    Detects when a job specifically demands a language outside candidate's verified proficiencies.
    Checks:
    1. Title language designations (e.g., 'Italian Customer Advisor', 'German AML Analyst').
    2. C2 / C1 / Fluent / Native / Speaker specifications in title or description.
    """
    title_low = title.lower()
    desc_low = desc.lower()
    combined = f"{title_low} {desc_low}"

    # 1. Title language keyword check (strongest indicator of a mandatory working language)
    for kw, lang in FOREIGN_LANGUAGE_MAP.items():
        if re.search(r"\b" + re.escape(kw) + r"\b", title_low):
            if lang not in allowed_languages:
                return {"language": lang, "reason": f"Title explicitly designates role for {lang} speakers"}

    # 2. C2 / C1 / Native / Fluent / Speaker patterns in description or combined text
    patterns = [
        r"\b([a-zA-Z\u00C0-\u017F]+)\s*[:\-–]?\s*(?:c2|c1|fluent|native|mother\s*tongue)\b",
        r"\b(?:c2|c1|fluent|native|proficient)\s+(?:in\s+|level\s+)?([a-zA-Z\u00C0-\u017F]+)\b",
        r"\b([a-zA-Z\u00C0-\u017F]+)\s+(?:speaker|speaking)\b",
        r"\b([a-zA-Z\u00C0-\u017F]+)\s+(?:language\s+)?skills?\s*[:\-–]?\s*(?:c2|c1|fluent|native)\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, combined):
            word = m.group(1).lower()
            if word in FOREIGN_LANGUAGE_MAP:
                lang = FOREIGN_LANGUAGE_MAP[word]
                if lang not in allowed_languages:
                    return {"language": lang, "reason": f"Requires {lang} (C2/C1/fluent/speaker)"}

    return None


# =============================================================================
# 1. JUSTIN WHITMORE SCORER
# =============================================================================

def _score_for_justin(job_data: Dict[str, Any], profile: Dict[str, Any], traps: Dict[str, Any]) -> Dict[str, Any]:
    title = (job_data.get("title") or "").lower()
    desc = (job_data.get("description") or "").lower()
    location = (job_data.get("location") or "").lower()
    remote_type = (job_data.get("remote_type") or "").lower()
    contract = (job_data.get("contract_type") or job_data.get("contract") or "").lower()
    combined = f"{title} {location} {desc}"

    prefs = profile.get("preferences", {})
    weights_cfg = profile.get("scoring_weights", {})
    practical_enabled = bool(
        weights_cfg.get("france_practical_stability_enabled", prefs.get("france_immediate_stability_boost", True))
    )
    excluded = [c.lower() for c in prefs.get("excluded_countries", ["Malta"])]

    flags = {
        "disqualified": False,
        "french_risk": False,
        "language_barrier": False,
        "transit_risk": False,
        "is_practical_role": False,
        "scam_risk": traps["is_scam_suspect"]
    }

    for ex in excluded:
        if ex and (ex in location or f"in {ex}" in combined[:250]):
            flags["disqualified"] = True
            return {
                "score": 0,
                "breakdown": {"experience_skills": 0, "language_compatibility": 0, "location_remote_transit": 0, "work_auth_and_contract": 0, "penalties": 100},
                "rationale": f"EXCLUDED: Location matches excluded destination '{ex.title()}'. ({SCORE_DISCLAIMER})",
                "flags": flags
            }

    in_orleans = any(k in location or k in combined for k in [
        "orléans", "orleans", "fleury-les-aubrais", "olivet", "saint-jean-de-braye", "saran", "loiret", "45000", "45400", "45140"
    ])
    in_france = in_orleans or "france" in location or "france" in combined[:350]

    practical_keywords = [
        "mcdonald", "burger king", "kfc", "restauration rapide", "équipier", "équipier polyvalent",
        "plongeur", "aide de cuisine", "agent d'entretien", "agent de nettoyage", "agent de propreté",
        "nettoyage", "technicien de surface", "mise en rayon", "employé libre service", "hôte de caisse",
        "caissier", "vendeur", "entrepôt", "warehouse", "manutentionnaire", "préparateur de commandes",
        "preparateur commande", "agent logistique", "conditionnement", "cariste", "order picker",
        "opérateur de production", "ouvrier polyvalent", "manoeuvre"
    ]
    is_practical = any(k in combined for k in practical_keywords)
    if is_practical:
        flags["is_practical_role"] = True

    reasons: List[str] = []
    penalty = 0.0

    # A. Experience & Skills (out of 35)
    exp_pts = 5.0
    matched = []
    if is_practical and in_france and practical_enabled:
        exp_pts = 35.0
        matched.append("France Immediate Stability Track (Local accessible employment)")
    else:
        sap_hit = any(k in combined for k in ["sap", "va32", "zbl", "zdr", "order management", "order to cash", "order desk", "gestion des commandes", "adv"])
        export_hit = any(k in combined for k in ["export", "customs", "douane", "awb", "airway bill", "incoterms", "ex-1", "certificate of origin", "cold chain", "logistics", "supply chain", "freight"])
        cs_hit = any(k in combined for k in ["customer service", "customer support", "customer experience", "customer operations", "customer success", "client support", "customer care", "service client"])
        lead_hit = any(k in combined for k in ["team lead", "team manager", "manager", "shift lead", "escalation", "coaching"])
        gaming_pay_hit = any(k in combined for k in ["igaming", "sports trading", "payment", "billing"])
        admin_hit = any(k in combined for k in ["administrative", "back office", "office coordinator", "order administrator"])

        if sap_hit and export_hit:
            exp_pts = 35.0
            matched.append("Direct SAP + EMEA Export/Logistics match (QuidelOrtho)")
        elif export_hit:
            exp_pts = max(exp_pts, 31.0)
            matched.append("Export, Logistics & Supply Chain match")
        elif sap_hit:
            exp_pts = max(exp_pts, 29.0)
            matched.append("SAP & Order Management match")

        if cs_hit and lead_hit:
            exp_pts = max(exp_pts, 33.0)
            matched.append("Customer Operations & Team Leadership (~15 staff at Besedo)")
        elif cs_hit:
            exp_pts = max(exp_pts, 28.0)
            matched.append("Customer Support / CX / Operations match")

        if gaming_pay_hit:
            exp_pts = max(exp_pts, 28.0)
            matched.append("iGaming Sports Trading / Payments operations")
        if admin_hit:
            exp_pts = max(exp_pts, 22.0)
            matched.append("English Administrative / Back-office operations")
        if is_practical and exp_pts < 22.0:
            exp_pts = 22.0
            matched.append("Practical warehouse/logistics operations")

    reasons.append(
        f"Experience ({int(exp_pts)}/35): {', '.join(matched) if matched else 'Low direct overlap with core experience'}."
    )

    # B. Language Compatibility (out of 25)
    barrier = detect_foreign_language_barrier(
        job_data.get("title") or "",
        job_data.get("description") or "",
        allowed_languages=["English", "French"]
    )

    english_ok = any(k in combined for k in ["english", "anglais"])
    french_native_strict = any(k in combined for k in [
        "français langue maternelle", "french native", "native french"
    ])
    french_workplace = any(k in combined for k in [
        "français", "french", "bilingue", "courant", "b2", "b1", "french speaker"
    ])

    if barrier:
        lang_pts = 0.0
        penalty += 65.0
        flags["language_barrier"] = True
        reasons.append(f"Language Barrier (-65): Role requires {barrier['language']} ({barrier['reason']}), outside verified languages (English C2, French B2).")
    elif is_practical and in_france and practical_enabled:
        lang_pts = 25.0
        reasons.append("Language (25/25): Practical local role viable with conversational B1-B2 French.")
    elif english_ok and not french_native_strict:
        lang_pts = 25.0
        reasons.append("Language (25/25): English-accessible role compatible with verified profile.")
    elif french_workplace and not french_native_strict:
        lang_pts = 24.0
        reasons.append("Language (24/25): Professional French workplace accessible with verified B2 French.")
    elif french_native_strict:
        lang_pts = 14.0
        penalty += 10.0
        flags["french_risk"] = True
        reasons.append("Language Caution (-10): Strict native/mother-tongue French requested; profile has professional B2 French.")
    else:
        lang_pts = 5.0
        penalty += 20.0
        flags["french_risk"] = True
        reasons.append("Language Penalty (-20): No English or B2 French working language indicated.")

    # C. Location, Remote & Transit (out of 25)
    is_remote = ("remote" in remote_type or any(k in combined for k in ["remote", "télétravail", "work from home"])) and not traps["misleading_remote"]
    car_req = any(k in combined for k in ["permis b obligatoire", "véhicule obligatoire", "véhicule exigé", "own car required"])
    if car_req:
        flags["transit_risk"] = True
        penalty += 35.0
        reasons.append("Transit Penalty (-35): Requires personal car / driver's license.")

    if traps["us_uk_locked_remote"] and "us" not in location:
        # Note: Justin is a US citizen, though physically in France; flag timezone/tax lock
        penalty += 10.0
        reasons.append("Remote Restriction (-10): Role may require physical US/UK tax residency.")

    in_portugal = any(k in location or k in combined for k in ["lisbon", "lisboa", "porto", "portugal"])
    has_reloc = bool(job_data.get("relocation_assistance")) or any(k in combined for k in ["relocation package", "relocation assistance", "relocation support"])
    in_eu = any(c in location for c in EU_COUNTRIES)

    if is_remote:
        loc_pts = 25.0
        reasons.append("Location (25/25): Remote accessible from France.")
    elif in_orleans and not car_req:
        loc_pts = 25.0
        reasons.append("Location (25/25): Orléans area (transit accessible).")
    elif in_portugal:
        loc_pts = 23.0
        reasons.append("Location (23/25): Portugal (top European relocation target).")
    elif has_reloc or in_france:
        loc_pts = 19.0
        reasons.append("Location (19/25): France nationwide or includes relocation support.")
    elif in_eu:
        loc_pts = 16.0
        reasons.append("Location (16/25): European Union hub (open to relocation).")
    else:
        loc_pts = 6.0
        reasons.append("Location (6/25): Outside target European/remote zones.")

    # D. Work Authorization & Contract (out of 15)
    auth_pts = 15.0 if any(k in contract or k in combined for k in ["cdi", "permanent", "full-time", "temps plein", "cdii"]) else 12.0
    reasons.append(f"Auth & Contract ({int(auth_pts)}/15): Dual French (EU) + US citizen — immediate work eligibility.")

    if traps["is_scam_suspect"]:
        penalty += 60.0
        reasons.append("Scam Filter (-60): Suspicious listing indicators detected.")

    raw_parts = {
        "experience_skills": exp_pts,
        "language_compatibility": lang_pts,
        "location_remote_transit": loc_pts,
        "work_auth_and_contract": auth_pts,
    }
    max_parts = {
        "experience_skills": 35.0,
        "language_compatibility": 25.0,
        "location_remote_transit": 25.0,
        "work_auth_and_contract": 15.0,
    }
    active_weights = {
        "experience_skills": float(weights_cfg.get("experience_skills", 35)),
        "language_compatibility": float(weights_cfg.get("language_compatibility", 25)),
        "location_remote_transit": float(weights_cfg.get("location_remote_transit", 25)),
        "work_auth_and_contract": float(weights_cfg.get("work_auth_and_contract", 15)),
    }
    total = _scale_weighted_total(raw_parts, max_parts, active_weights, penalty)
    reasons.append(SCORE_DISCLAIMER)

    return {
        "score": total,
        "breakdown": {**{k: int(v) for k, v in raw_parts.items()}, "penalties": int(penalty)},
        "rationale": " | ".join(reasons),
        "flags": flags
    }


# =============================================================================
# 2. IŞIL SCORER (PRAGUE / CZECHIA / REMOTE | C2 ENGLISH + TURKISH | VISA CHECK)
# =============================================================================

def _score_for_isil(job_data: Dict[str, Any], profile: Dict[str, Any], traps: Dict[str, Any]) -> Dict[str, Any]:
    title = (job_data.get("title") or "").lower()
    desc = (job_data.get("description") or "").lower()
    location = (job_data.get("location") or "").lower()
    remote_type = (job_data.get("remote_type") or "").lower()
    combined = f"{title} {location} {desc}"

    prefs = profile.get("preferences", {})
    weights_cfg = profile.get("scoring_weights", {})
    excluded = [c.lower() for c in prefs.get("excluded_countries", [])]

    flags = {
        "disqualified": False,
        "work_auth_warning": False,
        "language_barrier": False,
        "is_practical_role": False,
        "scam_risk": traps["is_scam_suspect"]
    }

    for ex in excluded:
        if ex and ex in location:
            flags["disqualified"] = True
            return {
                "score": 0,
                "breakdown": {"experience_skills": 0, "language_compatibility": 0, "location_remote_transit": 0, "work_auth_and_contract": 0, "penalties": 100},
                "rationale": f"EXCLUDED: Destination '{ex.title()}' excluded in preferences. ({SCORE_DISCLAIMER})",
                "flags": flags
            }

    reasons: List[str] = []
    penalty = 0.0

    # A. Experience & Skills (out of 30) — ONLY score against VERIFIED background!
    exp_pts = 5.0
    matched = []
    onboarding_hit = any(k in combined for k in ["onboarding", "implementation specialist", "client activation", "customer success"])
    cs_hit = any(k in combined for k in ["customer support", "customer service", "customer experience", "customer care", "member support", "customer operations", "helpdesk"])
    teaching_hit = any(k in combined for k in ["english teacher", "english instructor", "esl", "efl", "lecturer", "language trainer", "corporate trainer", "learning specialist", "turkish teacher"])
    translation_hit = any(k in combined for k in ["turkish", "translator", "translation", "localization", "linguist", "content reviewer"])

    if onboarding_hit and cs_hit:
        exp_pts = 30.0
        matched.append("Direct Customer Support & Onboarding match (Accolade)")
    elif onboarding_hit:
        exp_pts = max(exp_pts, 28.0)
        matched.append("Customer Onboarding & Success alignment")
    elif teaching_hit:
        exp_pts = max(exp_pts, 29.0)
        matched.append("University English Teaching & Training background")
    elif translation_hit:
        exp_pts = max(exp_pts, 28.0)
        matched.append("Native Turkish & C2 English Language/Localization match")
    elif cs_hit:
        exp_pts = max(exp_pts, 26.0)
        matched.append("English Customer Support & Operations match (Accolade)")

    reasons.append(f"Experience ({int(exp_pts)}/30): {', '.join(matched) if matched else 'Limited overlap with verified background'}.")

    # B. Language Compatibility (out of 30)
    barrier = detect_foreign_language_barrier(
        job_data.get("title") or "",
        job_data.get("description") or "",
        allowed_languages=["English", "Turkish"]
    )
    turkish_bonus = "turkish" in combined
    requires_czech = any(k in combined for k in ["fluent czech", "native czech", "czech c1", "czech c2", "czech required", "český jazyk na úrovni", "znalost češtiny", "rodilý mluvčí"])
    english_ok = any(k in combined for k in ["english", "c1", "c2", "fluent english"]) or not any(
        fl in combined for fl in ["česky", "czech fluent", "native czech", "français obligatoire"]
    )

    if barrier:
        lang_pts = 0.0
        penalty += 65.0
        flags["language_barrier"] = True
        reasons.append(f"Language Barrier (-65): Role requires {barrier['language']} ({barrier['reason']}), outside verified languages (English C2, Turkish Native).")
    elif requires_czech:
        lang_pts = 4.0
        penalty += 45.0
        flags["language_barrier"] = True
        reasons.append("Language Penalty (-45): Requires fluent/native Czech, outside verified profile.")
    elif turkish_bonus:
        lang_pts = 30.0
        reasons.append("Language (30/30): High-value Native Turkish + C2 English match!")
    elif english_ok:
        lang_pts = 27.0
        reasons.append("Language (27/30): C2 English accessible; no non-verified language barrier.")
    else:
        lang_pts = 6.0
        penalty += 28.0
        flags["language_barrier"] = True
        reasons.append("Language Penalty (-28): Working language requirements outside verified profile.")

    # C. Location & Remote Accessibility from Czechia (out of 20)
    in_prague_cz = any(k in location or k in combined for k in ["prague", "praha", "czech", "czechia", "brno"])
    is_remote = ("remote" in remote_type or "remote" in combined) and not traps["misleading_remote"]
    has_reloc_visa = bool(job_data.get("relocation_assistance")) or any(k in combined for k in [
        "visa sponsorship", "work permit sponsorship", "relocation package", "relocation support", "employee card"
    ])
    in_france_or_other_eu_onsite = (not in_prague_cz) and (not is_remote) and any(c in location for c in EU_COUNTRIES + ["malta", "uk", "united kingdom"])

    if in_prague_cz:
        loc_pts = 20.0
        reasons.append("Location (20/20): Prague / Czech Republic.")
    elif is_remote and not traps["us_uk_locked_remote"]:
        loc_pts = 19.0
        reasons.append("Location (19/20): Remote position accessible from Czechia/EMEA.")
    elif has_reloc_visa:
        loc_pts = 17.0
        reasons.append("Location (17/20): International role offering relocation/visa support.")
    else:
        loc_pts = 3.0
        reasons.append("Location (3/20): On-site outside Czech Republic without explicit relocation support.")

    # D. Work Authorization Realism (out of 20) — CRITICAL GUARDRAIL FOR IŞIL
    eu_citizens_only = any(k in combined for k in [
        "eu citizenship required", "eu citizens only", "must have eu passport",
        "no visa sponsorship", "cannot sponsor", "right to work in france", "french work permit required"
    ])
    if eu_citizens_only:
        auth_pts = 2.0
        penalty += 35.0
        flags["work_auth_warning"] = True
        reasons.append("Work Auth Penalty (-35): Explicitly requires EU citizenship / denies visa sponsorship (Turkish national).")
    elif in_france_or_other_eu_onsite and not has_reloc_visa:
        auth_pts = 4.0
        penalty += 30.0
        flags["work_auth_warning"] = True
        reasons.append("Work Auth Penalty (-30): On-site outside Czechia with no visa sponsorship stated (cannot assume French/EU work authorization).")
    elif in_prague_cz:
        auth_pts = 16.0
        flags["work_auth_warning"] = True
        reasons.append("Work Auth (16/20): Located in Czechia — verify Czech labor market permit / employer support.")
    elif is_remote and not traps["us_uk_locked_remote"]:
        auth_pts = 17.0
        reasons.append("Work Auth (17/20): Remote EMEA/Global role (verify Czech B2B/EOR contractor eligibility).")
    elif has_reloc_visa:
        auth_pts = 18.0
        reasons.append("Work Auth (18/20): Employer advertises relocation / visa sponsorship.")
    else:
        auth_pts = 6.0
        penalty += 15.0
        reasons.append("Work Auth (6/20): Unclear work-permit eligibility.")

    if traps["is_scam_suspect"]:
        penalty += 60.0
        reasons.append("Scam Filter (-60): Suspicious listing indicators detected.")

    raw_parts = {
        "experience_skills": exp_pts,
        "language_compatibility": lang_pts,
        "location_remote_transit": loc_pts,
        "work_auth_and_contract": auth_pts,
    }
    max_parts = {
        "experience_skills": 30.0,
        "language_compatibility": 30.0,
        "location_remote_transit": 20.0,
        "work_auth_and_contract": 20.0,
    }
    active_weights = {
        "experience_skills": float(weights_cfg.get("experience_skills", 30)),
        "language_compatibility": float(weights_cfg.get("language_compatibility", 30)),
        "location_remote_transit": float(weights_cfg.get("location_remote_transit", 20)),
        "work_auth_and_contract": float(weights_cfg.get("work_auth_and_contract", 20)),
    }
    total = _scale_weighted_total(raw_parts, max_parts, active_weights, penalty)
    reasons.append(SCORE_DISCLAIMER)

    return {
        "score": total,
        "breakdown": {**{k: int(v) for k, v in raw_parts.items()}, "penalties": int(penalty)},
        "rationale": " | ".join(reasons),
        "flags": flags
    }


# =============================================================================
# 3. LINDSEY WHITMORE SCORER (LEAVE MALTA | REMOTE-FIRST EUROPE | iGAMING/FINTECH)
# =============================================================================

def _score_for_lindsey(job_data: Dict[str, Any], profile: Dict[str, Any], traps: Dict[str, Any]) -> Dict[str, Any]:
    title = (job_data.get("title") or "").lower()
    desc = (job_data.get("description") or "").lower()
    location = (job_data.get("location") or "").lower()
    remote_type = (job_data.get("remote_type") or "").lower()
    combined = f"{title} {location} {desc}"

    prefs = profile.get("preferences", {})
    weights_cfg = profile.get("scoring_weights", {})
    ranked_dests = [d.lower() for d in prefs.get("ranked_destinations", [])]
    excluded = [c.lower() for c in prefs.get("excluded_countries", [])]

    flags = {
        "disqualified": False,
        "malta_conflict": False,
        "remote_country_warning": False,
        "is_practical_role": False,
        "scam_risk": traps["is_scam_suspect"]
    }

    is_remote = ("remote" in remote_type or "remote" in title or "100% remote" in desc or "fully remote" in desc) and not traps["misleading_remote"]
    mentions_malta_loc = any(m in location for m in ["malta", "sliema", "st julian", "gzira", "ta' xbiex", "birkirkara", "valletta"])

    # CRITICAL RULE: Lindsey wants to LEAVE Malta! Never prioritize Malta on-site/hybrid or Malta-locked remote!
    if (mentions_malta_loc and not is_remote) or traps["malta_locked_remote"]:
        flags["malta_conflict"] = True
        flags["disqualified"] = True
        return {
            "score": 5,
            "breakdown": {"experience_skills": 0, "location_remote_leave_malta": 0, "language_compatibility": 0, "work_auth_and_contract": 0, "penalties": 95},
            "rationale": f"DEMOTED (5/100): Role requires staying in Malta (on-site/hybrid or Malta-resident remote), directly conflicting with Lindsey's goal to leave Malta. ({SCORE_DISCLAIMER})",
            "flags": flags
        }

    for ex in excluded:
        clean_ex = ex.replace("(on-site / hybrid)", "").strip()
        if clean_ex and clean_ex != "malta" and clean_ex in location and not is_remote:
            flags["disqualified"] = True
            return {
                "score": 0,
                "breakdown": {"experience_skills": 0, "location_remote_leave_malta": 0, "language_compatibility": 0, "work_auth_and_contract": 0, "penalties": 100},
                "rationale": f"EXCLUDED: Destination '{clean_ex.title()}' excluded in Lindsey's destination settings. ({SCORE_DISCLAIMER})",
                "flags": flags
            }

    reasons: List[str] = []
    penalty = 0.0

    # A. iGaming / Fintech / Compliance / Risk / Player Ops Experience (out of 35)
    exp_pts = 5.0
    matched = []
    igaming_fintech = any(k in combined for k in ["igaming", "gaming", "casino", "sportsbook", "betting", "fintech", "payments", "financial crime", "fincrime"])
    aml_rg_comp = any(k in combined for k in ["aml", "anti-money laundering", "responsible gambling", "safer gambling", "compliance", "mlro", "edd", "cdd"])
    kyc_fraud_pay = any(k in combined for k in ["kyc", "fraud", "risk", "chargeback", "payment operations", "payments analyst", "transaction monitoring"])
    player_ops_mgmt = any(k in combined for k in ["player operations", "operations manager", "head of operations", "performance manager", "vip operations", "customer operations manager", "shift lead", "quality assurance"])

    if (aml_rg_comp or kyc_fraud_pay or player_ops_mgmt) and igaming_fintech:
        exp_pts = 35.0
        matched.append("Direct iGaming/Fintech Management match (Player Ops, AML/RG, KYC, Fraud & Payments)")
    elif aml_rg_comp:
        exp_pts = 33.0
        matched.append("AML, Responsible Gambling & Compliance leadership (Betmaster / kwiff)")
    elif kyc_fraud_pay:
        exp_pts = 32.0
        matched.append("KYC, Fraud Prevention, Risk & Payments Operations (Casumo / ComeOn! / ARRINGO)")
    elif player_ops_mgmt:
        exp_pts = 31.0
        matched.append("Operations & Performance Management (Patrianna)")
    elif any(k in combined for k in ["operations", "compliance", "trust and safety", "onboarding", "escalation manager"]):
        exp_pts = 24.0
        matched.append("Transferable Operations / Escalations / Trust & Safety leadership")

    reasons.append(f"Experience ({int(exp_pts)}/35): {', '.join(matched) if matched else 'Low alignment with iGaming/Fintech/Compliance leadership'}.")

    # B. Leave-Malta, True EU Remote & European Hub Score (out of 35)
    loc_pts = 8.0
    has_reloc = bool(job_data.get("relocation_assistance")) or any(k in combined for k in ["relocation package", "relocation support", "relocation assistance"])
    eu_remote_ok = is_remote and any(k in combined for k in ["europe", "emea", "eu", "anywhere", "worldwide", "france", "portugal", "spain", "germany", "netherlands", "ireland", "poland", "estonia", "cyprus", "czech"])

    matched_hub = None
    for idx, dest in enumerate(ranked_dests):
        for country_kw in EU_COUNTRIES:
            if country_kw in dest and country_kw in location:
                matched_hub = (country_kw.title(), idx)
                break
        if matched_hub:
            break

    if is_remote and traps["us_uk_locked_remote"]:
        # Lindsey has US citizenship, though Europe is her primary focus
        loc_pts = 18.0
        flags["remote_country_warning"] = True
        reasons.append("Remote Check (18/35): Remote role appears UK/US geo-restricted — verify European remote work eligibility.")
    elif eu_remote_ok and not mentions_malta_loc:
        loc_pts = 35.0
        reasons.append("Location & Mobility (35/35): Fully Remote across Europe — enables immediate relocation out of Malta to any EU country!")
    elif is_remote and mentions_malta_loc:
        loc_pts = 24.0
        flags["remote_country_warning"] = True
        reasons.append("Remote Check (24/35): Marked Remote by Malta employer — verify contract allows residing outside Malta in mainland EU.")
    elif is_remote:
        loc_pts = 31.0
        reasons.append("Location & Mobility (31/35): Remote role — verify tax/country freedom across target EU destinations.")
    elif matched_hub and has_reloc:
        loc_pts = 32.0
        reasons.append(f"Location & Mobility (32/35): European hub ({matched_hub[0]}) with relocation assistance to leave Malta.")
    elif matched_hub:
        rank_bonus = max(22.0, 29.0 - matched_hub[1])
        loc_pts = rank_bonus
        reasons.append(f"Location & Mobility ({int(loc_pts)}/35): Located in target European destination ({matched_hub[0]}) outside Malta.")
    elif any(c in location for c in EU_COUNTRIES):
        loc_pts = 22.0
        reasons.append("Location & Mobility (22/35): Mainland European opportunity outside Malta.")
    else:
        loc_pts = 8.0
        reasons.append("Location & Mobility (8/35): Outside prioritized European remote/relocation markets.")

    # C. Language Compatibility (out of 15)
    barrier = detect_foreign_language_barrier(
        job_data.get("title") or "",
        job_data.get("description") or "",
        allowed_languages=["English"]
    )
    if barrier:
        lang_pts = 0.0
        penalty += 65.0
        flags["language_barrier"] = True
        reasons.append(f"Language Barrier (-65): Role requires {barrier['language']} ({barrier['reason']}), outside verified language (English C2).")
    else:
        lang_pts = 15.0
        reasons.append("Language (15/15): English-speaking international operations.")

    # D. EU + US Work Authorization & Contract (out of 15)
    auth_pts = 15.0
    reasons.append("Work Auth (15/15): Dual French (EU) + US citizen — immediate unrestricted EU employment rights anywhere in Europe.")

    if traps["is_scam_suspect"]:
        penalty += 60.0
        reasons.append("Scam Filter (-60): Suspicious listing indicators detected.")

    raw_parts = {
        "experience_skills": exp_pts,
        "location_remote_leave_malta": loc_pts,
        "language_compatibility": lang_pts,
        "work_auth_and_contract": auth_pts,
    }
    max_parts = {
        "experience_skills": 35.0,
        "location_remote_leave_malta": 35.0,
        "language_compatibility": 15.0,
        "work_auth_and_contract": 15.0,
    }
    active_weights = {
        "experience_skills": float(weights_cfg.get("experience_skills", 35)),
        "location_remote_leave_malta": float(weights_cfg.get("location_remote_leave_malta", 35)),
        "language_compatibility": float(weights_cfg.get("language_compatibility", 15)),
        "work_auth_and_contract": float(weights_cfg.get("work_auth_and_contract", 15)),
    }
    total = _scale_weighted_total(raw_parts, max_parts, active_weights, penalty)
    reasons.append(SCORE_DISCLAIMER)

    return {
        "score": total,
        "breakdown": {**{k: int(v) for k, v in raw_parts.items()}, "penalties": int(penalty)},
        "rationale": " | ".join(reasons),
        "flags": flags
    }


def evaluate_job_for_user(user_slug: str, job_data: Dict[str, Any], profile_data: Dict[str, Any]) -> Dict[str, Any]:
    """Routes evaluation to the user's personalized AI recruiter model."""
    traps = detect_scam_and_remote_traps(job_data)
    slug = (user_slug or "justin").strip().lower()
    if slug == "isil":
        return _score_for_isil(job_data, profile_data, traps)
    elif slug == "lindsey":
        return _score_for_lindsey(job_data, profile_data, traps)
    else:
        return _score_for_justin(job_data, profile_data, traps)


def evaluate_job(job_data: Dict[str, Any], profile_data: Dict[str, Any], user_slug: str = "justin") -> Dict[str, Any]:
    """Backward-compatible entry point."""
    return evaluate_job_for_user(user_slug=user_slug, job_data=job_data, profile_data=profile_data)
