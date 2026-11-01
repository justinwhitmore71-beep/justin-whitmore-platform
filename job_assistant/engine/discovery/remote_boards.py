"""
Discovery module for European & Global Remote job boards:
- Remotive (Customer Support, Operations)
- Jobicy (Support, Logistics, Supply Chain, Admin)
- Arbeitnow (European English-friendly jobs)
"""

import hashlib
import requests
from typing import List, Dict, Any


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _make_dedup_hash(company: str, title: str, location: str) -> str:
    raw = f"{company.strip().lower()}_{title.strip().lower()}_{location.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def fetch_remotive_jobs(category: str = "customer-support", limit: int = 40) -> List[Dict[str, Any]]:
    """Fetches remote jobs from Remotive API."""
    url = f"https://remotive.com/api/remote-jobs?category={category}&limit={limit}"
    results = []
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("jobs", []):
                geo = item.get("candidate_required_location", "")
                # We want jobs open to France, Europe, EMEA, or Worldwide
                geo_lower = geo.lower()
                is_eligible = any(reg in geo_lower for reg in ["worldwide", "anywhere", "europe", "emea", "france", "eu", "utc"])
                if not is_eligible and geo:
                    # If explicitly locked to US-only or non-EU without EU option, skip
                    if any(locked in geo_lower for locked in ["usa only", "us only", "north america only", "canada only", "latam only"]):
                        continue

                title = item.get("title", "")
                company = item.get("company_name", "")
                loc = f"Remote ({geo or 'Worldwide'})"
                
                results.append({
                    "dedup_hash": _make_dedup_hash(company, title, loc),
                    "title": title,
                    "company": company,
                    "location": loc,
                    "remote_type": "Remote",
                    "salary": item.get("salary", ""),
                    "job_url": item.get("url", ""),
                    "source": "Remotive",
                    "description": item.get("description", ""),
                    "date_discovered": item.get("publication_date", "")[:10] if item.get("publication_date") else "",
                    "deadline": ""
                })
    except Exception as e:
        print(f"[Remotive] Error fetching jobs: {e}")
    return results


def fetch_jobicy_jobs(count: int = 50, tag: str = "support") -> List[Dict[str, Any]]:
    """Fetches remote jobs from Jobicy API."""
    url = f"https://jobicy.com/api/v2/remote-jobs?count={count}&geo=emea&tag={tag}"
    results = []
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("jobs", []):
                title = item.get("jobTitle", "")
                company = item.get("companyName", "")
                geo = item.get("jobGeo", "EMEA / Remote")
                loc = f"Remote ({geo})"
                
                results.append({
                    "dedup_hash": _make_dedup_hash(company, title, loc),
                    "title": title,
                    "company": company,
                    "location": loc,
                    "remote_type": "Remote",
                    "salary": item.get("annualSalaryMin", "") and f"{item.get('annualSalaryMin')}-{item.get('annualSalaryMax')} {item.get('salaryCurrency', 'EUR')}" or "",
                    "job_url": item.get("url", ""),
                    "source": "Jobicy",
                    "description": item.get("jobDescription", ""),
                    "date_discovered": item.get("pubDate", "")[:10] if item.get("pubDate") else "",
                    "deadline": ""
                })
    except Exception as e:
        print(f"[Jobicy] Error fetching jobs: {e}")
    return results


def fetch_arbeitnow_jobs(limit: int = 60) -> List[Dict[str, Any]]:
    """Fetches jobs from Arbeitnow (European focus, visa-friendly, English-speaking)."""
    url = "https://www.arbeitnow.com/api/job-board-api"
    results = []
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("data", [])[:limit]:
                title = item.get("title", "")
                company = item.get("company_name", "")
                loc = item.get("location", "")
                remote = "Remote" if item.get("remote") else "On-site"
                
                # Check relevance
                title_lower = title.lower()
                relevant_keywords = ["customer", "support", "operations", "logistics", "supply chain", "order", "export", "service", "specialist", "coordinator"]
                if not any(k in title_lower for k in relevant_keywords):
                    continue

                results.append({
                    "dedup_hash": _make_dedup_hash(company, title, loc),
                    "title": title,
                    "company": company,
                    "location": loc,
                    "remote_type": remote,
                    "salary": "",
                    "job_url": item.get("url", ""),
                    "source": "Arbeitnow",
                    "description": item.get("description", ""),
                    "date_discovered": "",
                    "deadline": ""
                })
    except Exception as e:
        print(f"[Arbeitnow] Error fetching jobs: {e}")
    return results


if __name__ == "__main__":
    jobs = fetch_remotive_jobs(limit=5)
    print(f"Fetched {len(jobs)} test jobs from Remotive.")
    if jobs:
        print("Sample:", jobs[0]["title"], "|", jobs[0]["company"], "|", jobs[0]["location"])
