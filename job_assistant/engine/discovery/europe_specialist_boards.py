"""
Specialist European, Prague/Czechia, iGaming/Fintech, and Direct Company ATS Discovery Connectors.
Covers:
- Prague & Czech Republic English-speaking Customer Support, Onboarding, Teaching, and Turkish roles (Işıl)
- Pan-European Remote & Mainland EU iGaming, Player Operations, AML, RG, KYC, Fraud & Payments (Lindsey)
- Direct Company Career Boards via Greenhouse Public Job Board JSON API (verified direct employers, zero scams)
- Rich Vacancy Metadata Normalizer (contract type, seniority, category, languages, remote country eligibility)
"""

import hashlib
import re
import time
from typing import List, Dict, Any
import requests

from job_assistant.engine.discovery.linkedin_scraper import search_linkedin_jobs


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Curated verified international employers with public Greenhouse boards hiring across Europe / Remote EMEA
VERIFIED_GREENHOUSE_COMPANIES = [
    ("wise", "Wise"),
    ("stripe", "Stripe"),
    ("adyen", "Adyen"),
    ("sumup", "SumUp"),
    ("remotecom", "Remote.com"),
    ("gitlab", "GitLab"),
    ("zendesk", "Zendesk"),
    ("cloudflare", "Cloudflare"),
]


def _make_hash(company: str, title: str, location: str) -> str:
    raw = f"{company.strip().lower()}_{title.strip().lower()}_{location.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def enrich_vacancy_metadata(raw_job: Dict[str, Any]) -> Dict[str, Any]:
    """Populates structured Part 5 & Part 9 fields (category, seniority, contract, languages, country, remote rules)."""
    title = (raw_job.get("title") or "").strip()
    desc = (raw_job.get("description") or "").strip()
    loc = (raw_job.get("location") or "").strip()
    combined = f"{title} {loc} {desc}".lower()

    # Country detection
    country = raw_job.get("country") or ""
    if not country:
        country_map = {
            "France": ["france", "orléans", "orleans", "paris", "lyon", "loiret", "45 -"],
            "Portugal": ["portugal", "lisbon", "lisboa", "porto"],
            "Czech Republic": ["czech", "czechia", "prague", "praha", "brno"],
            "Spain": ["spain", "madrid", "barcelona", "malaga", "valencia"],
            "Netherlands": ["netherlands", "amsterdam", "rotterdam"],
            "Germany": ["germany", "berlin", "munich", "frankfurt"],
            "Ireland": ["ireland", "dublin", "cork"],
            "Cyprus": ["cyprus", "limassol", "nicosia"],
            "Poland": ["poland", "warsaw", "krakow", "wroclaw"],
            "Estonia": ["estonia", "tallinn"],
            "Malta": ["malta", "sliema", "st julian", "gzira"],
        }
        for cname, kws in country_map.items():
            if any(kw in combined[:250] for kw in kws):
                country = cname
                break
        if not country and "remote" in loc.lower():
            country = "Remote / International"

    # Remote / Hybrid / On-site classification
    remote_type = raw_job.get("remote_type") or "On-site"
    if any(k in combined[:300] for k in ["100% remote", "fully remote", "remote -", "remote ("]):
        remote_type = "Remote"
    elif "hybrid" in combined[:300] or "hybride" in combined[:300]:
        remote_type = "Hybrid"

    # Remote country restrictions note
    restrictions = raw_job.get("remote_country_restrictions") or ""
    if not restrictions and remote_type == "Remote":
        m = re.search(r"remote\s*\(([^)]+)\)", loc, flags=re.IGNORECASE)
        if m:
            restrictions = m.group(1).strip()
        elif "emea" in combined:
            restrictions = "EMEA"
        elif "europe" in combined:
            restrictions = "Europe"

    # Seniority classification
    t_low = title.lower()
    if any(k in t_low for k in ["head of", "director", "vp ", "chief"]):
        seniority = "Director / Head"
    elif any(k in t_low for k in ["manager", "team lead", "shift lead", "lead"]):
        seniority = "Manager / Lead"
    elif any(k in t_low for k in ["senior", "sr.", "principal", "staff"]):
        seniority = "Senior"
    elif any(k in t_low for k in ["junior", "jr.", "associate", "entry", "intern"]):
        seniority = "Junior / Associate"
    else:
        seniority = "Mid-Level"

    # Category classification
    if any(k in combined for k in ["aml", "responsible gambling", "igaming", "player operations", "casino", "sportsbook"]):
        category = "iGaming, AML & Player Ops"
    elif any(k in combined for k in ["kyc", "fraud", "chargeback", "payment", "fintech"]):
        category = "Risk, Fraud & Payments"
    elif any(k in combined for k in ["sap", "export", "customs", "freight", "supply chain", "order management", "order desk"]):
        category = "Export, SAP & Order Management"
    elif any(k in combined for k in ["onboarding", "teacher", "instructor", "lecturer", "trainer", "translation", "turkish"]):
        category = "Onboarding, Teaching & Languages"
    elif any(k in combined for k in [
        "entretien", "nettoyage", "manutention", "préparateur", "preparateur", "restauration rapide", "équipier", "vendeur"
    ]):
        category = "Practical Immediate Income"
    else:
        category = "Customer Support & Operations"

    # Languages
    req_langs = []
    for lang_name, kw_list in [
        ("English", ["english", "anglais"]),
        ("Turkish", ["turkish"]),
        ("French", ["french", "français"]),
        ("Czech", ["czech", "čeština"]),
        ("Spanish", ["spanish"]),
        ("German", ["german"]),
    ]:
        if any(k in combined for k in kw_list):
            req_langs.append(lang_name)

    # Contract type
    if any(k in combined for k in ["cdi", "permanent", "full-time", "temps plein"]):
        contract_type = "Permanent / Full-Time"
    elif any(k in combined for k in ["cdd", "fixed-term", "1 year contract", "contract"]):
        contract_type = "Fixed-Term / Contract"
    elif any(k in combined for k in ["interim", "intérim", "temporary"]):
        contract_type = "Temporary / Interim"
    else:
        contract_type = raw_job.get("contract_type") or "Standard"

    reloc = 1 if any(k in combined for k in ["relocation package", "relocation assistance", "relocation support", "visa sponsorship"]) else 0

    enriched = dict(raw_job)
    enriched.update({
        "canonical_hash": raw_job.get("canonical_hash") or raw_job.get("dedup_hash") or _make_hash(
            raw_job.get("company", ""), title, loc
        ),
        "country": country,
        "remote_type": remote_type,
        "remote_country_restrictions": restrictions,
        "seniority": seniority,
        "category": category,
        "required_languages": ", ".join(req_langs) if req_langs else "English (assumed)",
        "contract_type": contract_type,
        "relocation_assistance": reloc,
    })
    return enriched


def fetch_greenhouse_europe_jobs(max_per_company: int = 8) -> List[Dict[str, Any]]:
    """Fetches direct verified employer vacancies from public Greenhouse career boards."""
    results: List[Dict[str, Any]] = []
    relevant_terms = [
        "customer", "support", "onboarding", "operations", "compliance", "aml",
        "fraud", "kyc", "risk", "payment", "dispute", "logistics", "order", "turkish", "enablement"
    ]
    eu_geo_terms = [
        "europe", "emea", "remote", "france", "paris", "portugal", "lisbon", "prague",
        "czech", "spain", "madrid", "barcelona", "dublin", "ireland", "amsterdam",
        "netherlands", "berlin", "germany", "tallinn", "estonia", "warsaw", "poland", "cyprus"
    ]

    for board_token, company_name in VERIFIED_GREENHOUSE_COMPANIES:
        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
            if resp.status_code != 200:
                continue
            jobs = resp.json().get("jobs", [])
            taken = 0
            for item in jobs:
                title = item.get("title", "")
                loc = (item.get("location") or {}).get("name", "")
                if not any(t in title.lower() for t in relevant_terms):
                    continue
                if not any(g in loc.lower() for g in eu_geo_terms):
                    continue
                # Exclude Malta on-site
                if "malta" in loc.lower() and "remote" not in loc.lower():
                    continue

                content_raw = item.get("content", "")
                clean_desc = re.sub(r"<[^>]+>", " ", content_raw)
                clean_desc = re.sub(r"\s+", " ", clean_desc).strip()[:3000]

                results.append(enrich_vacancy_metadata({
                    "title": title,
                    "company": company_name,
                    "location": loc,
                    "remote_type": "Remote" if "remote" in loc.lower() else "Hybrid",
                    "job_url": item.get("absolute_url", ""),
                    "source": f"Company Career ({company_name})",
                    "description": clean_desc,
                    "published_at": (item.get("updated_at") or "")[:10],
                }))
                taken += 1
                if taken >= max_per_company:
                    break
        except Exception:
            continue
    return results


def run_isil_targeted_searches() -> List[Dict[str, Any]]:
    """Targeted discovery for Işıl (Prague, Czechia, Remote EMEA, English C2 + Turkish)."""
    queries = [
        ("Customer Support English", "Prague, Czechia"),
        ("Customer Onboarding", "Prague, Czechia"),
        ("Customer Success English", "Prague, Czechia"),
        ("English Teacher", "Prague, Czechia"),
        ("Turkish", "Prague, Czechia"),
        ("Customer Onboarding", "European Union"),
    ]
    out: List[Dict[str, Any]] = []
    for kw, loc in queries:
        found = search_linkedin_jobs(kw, loc, max_results=8)
        out.extend(enrich_vacancy_metadata(j) for j in found)
        time.sleep(0.6)
    return out


def run_lindsey_targeted_searches() -> List[Dict[str, Any]]:
    """
    Targeted discovery for Lindsey across the European Union & wider Europe.
    Focuses on:
    - France, Portugal, Spain, Netherlands, Germany, Ireland, Cyprus, Czech Republic, Poland, Estonia
    - Fully Remote Europe positions (to leave Malta immediately)
    - iGaming, Fintech, Player Operations, AML, Responsible Gambling, KYC, Fraud & Payments
    """
    queries = [
        # True Remote across Europe / EU
        ("Player Operations Manager Remote", "European Union"),
        ("Head of Player Operations Remote", "Europe"),
        ("AML Responsible Gambling Manager Remote", "European Union"),
        ("KYC Fraud Manager Remote", "Europe"),
        ("Payments Risk Operations Remote", "European Union"),
        ("Compliance Manager iGaming Remote", "Europe"),
        
        # Cyprus (Limassol, Nicosia - major EU iGaming/Fintech hub)
        ("AML Compliance iGaming", "Cyprus"),
        ("Player Operations Payments", "Cyprus"),
        ("Risk Fraud KYC", "Limassol, Cyprus"),

        # Spain (Barcelona, Madrid, Malaga)
        ("AML Fraud Operations", "Spain"),
        ("Compliance Manager iGaming", "Barcelona, Spain"),
        ("Payments Risk Specialist", "Madrid, Spain"),

        # Portugal (Lisbon, Porto)
        ("Compliance Manager iGaming", "Lisbon, Portugal"),
        ("Risk Payments Fraud Analyst", "Lisbon, Portugal"),
        ("Customer Player Operations", "Portugal"),

        # Netherlands (Amsterdam)
        ("Risk Payments Operations", "Amsterdam, Netherlands"),
        ("AML Compliance Manager", "Netherlands"),
        ("Fintech Fraud Operations", "Amsterdam, Netherlands"),

        # Germany (Berlin, Frankfurt)
        ("AML Compliance Operations", "Germany"),
        ("Risk and Fraud Specialist", "Berlin, Germany"),

        # Ireland (Dublin)
        ("AML Compliance Operations", "Dublin, Ireland"),
        ("Fraud Payments Operations", "Ireland"),

        # Poland (Warsaw, Krakow - major EU compliance/fintech hub)
        ("AML Compliance Analyst", "Warsaw, Poland"),
        ("Fraud Investigations Specialist", "Krakow, Poland"),

        # Estonia (Tallinn - leading EU digital/fintech hub)
        ("Compliance Manager", "Tallinn, Estonia"),
        ("Risk and Fraud Operations", "Estonia"),

        # Czech Republic (Prague)
        ("AML Compliance Specialist", "Prague, Czechia"),
        ("Payments Fraud Analyst", "Prague, Czechia"),
    ]
    out: List[Dict[str, Any]] = []
    for kw, loc in queries:
        found = search_linkedin_jobs(kw, loc, max_results=8)
        out.extend(enrich_vacancy_metadata(j) for j in found)
        time.sleep(0.5)
    return out
