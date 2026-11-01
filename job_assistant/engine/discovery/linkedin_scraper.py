"""
LinkedIn Guest Job Scraper.
Fetches public listings from LinkedIn without requiring authentication.
Targets:
- Customer Support / Customer Success / Customer Operations
- Order Management / SAP / Export Coordinator
- Logistics / Supply Chain
- Operations in Orléans, Lisbon, and Remote (France/EU).
"""

import hashlib
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _make_dedup_hash(company: str, title: str, location: str) -> str:
    raw = f"{company.strip().lower()}_{title.strip().lower()}_{location.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def search_linkedin_jobs(keywords: str, location: str, max_results: int = 25) -> List[Dict[str, Any]]:
    """
    Queries LinkedIn guest search API for a given keyword and location.
    """
    results = []
    base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    
    # LinkedIn guest pagination step is 10 or 25
    start = 0
    while len(results) < max_results:
        params = {
            "keywords": keywords,
            "location": location,
            "start": start
        }
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
            if resp.status_code != 200:
                break
                
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("li")
            if not cards:
                break

            for c in cards:
                title_elem = c.find("h3", class_="base-search-card__title")
                comp_elem = c.find("h4", class_="base-search-card__subtitle")
                loc_elem = c.find("span", class_="job-search-card__location")
                link_elem = c.find("a", class_="base-card__full-link")

                if not title_elem or not comp_elem:
                    continue

                title = title_elem.text.strip()
                company = comp_elem.text.strip()
                loc = loc_elem.text.strip() if loc_elem else location
                link = link_elem["href"].split("?")[0] if link_elem and link_elem.has_attr("href") else ""

                # Infer remote
                loc_lower = loc.lower()
                title_lower = title.lower()
                remote_type = "Remote" if ("remote" in loc_lower or "remote" in title_lower or "télétravail" in title_lower) else "On-site"

                results.append({
                    "dedup_hash": _make_dedup_hash(company, title, loc),
                    "title": title,
                    "company": company,
                    "location": loc,
                    "remote_type": remote_type,
                    "salary": "",
                    "job_url": link,
                    "source": "LinkedIn",
                    "description": f"Position: {title} at {company} in {loc}. Keywords: {keywords}.",
                    "date_discovered": time.strftime("%Y-%m-%d"),
                    "deadline": ""
                })
                if len(results) >= max_results:
                    break

            start += len(cards)
            time.sleep(1.0)  # Gentle rate limit
        except Exception as e:
            print(f"[LinkedIn] Error searching '{keywords}' in '{location}': {e}")
            break

    return results


def run_targeted_linkedin_searches() -> List[Dict[str, Any]]:
    """Runs high-yield targeted searches across France, Portugal, and wider Europe matching Justin's profile."""
    queries = [
        # Orléans (Public transit)
        ("Customer Service", "Orléans, Centre-Val de Loire, France"),
        ("Order Management", "Orléans, Centre-Val de Loire, France"),
        ("Logistics", "Orléans, Centre-Val de Loire, France"),
        ("Export", "Orléans, Centre-Val de Loire, France"),
        
        # Portugal (Lisbon, Porto)
        ("Customer Support English", "Lisbon, Portugal"),
        ("Customer Operations English", "Lisbon, Portugal"),
        ("Order Management English", "Lisbon, Portugal"),
        ("Export Operations English", "Portugal"),
        
        # Spain (Barcelona, Madrid)
        ("Customer Support English", "Barcelona, Spain"),
        ("Order Management Specialist", "Madrid, Spain"),

        # Netherlands (Amsterdam)
        ("Customer Operations English", "Amsterdam, Netherlands"),
        ("Order Management SAP", "Netherlands"),

        # Germany & Ireland
        ("Customer Operations English", "Berlin, Germany"),
        ("Customer Support Specialist", "Dublin, Ireland"),

        # Remote Europe / France
        ("Customer Support", "France (Remote)"),
        ("Order Management SAP", "France"),
        ("Customer Success English Remote", "European Union")
    ]

    all_jobs = []
    for kw, loc in queries:
        found = search_linkedin_jobs(kw, loc, max_results=8)
        all_jobs.extend(found)
        time.sleep(0.5)

    return all_jobs


if __name__ == "__main__":
    jobs = search_linkedin_jobs("Customer Support English", "Lisbon, Portugal", max_results=5)
    print(f"LinkedIn search returned {len(jobs)} jobs.")
    for j in jobs:
        print(f"- {j['title']} @ {j['company']} ({j['location']})")
