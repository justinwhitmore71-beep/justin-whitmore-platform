"""
Custom Target Job Source & Company Career Board Scraper.
Allows Justin, Işıl, and Lindsey to point their AI recruiter at ANY target source:
- Direct Company ATS boards (Greenhouse, Lever, Ashby, Workday)
- Specific Job Board URLs or Regional Sites (e.g., Jobs.cz, Prace.cz, WTTJ, etc.)
- Custom Keywords & Location Search Queries
- RSS Feeds
"""

import json
import re
import urllib.parse
from typing import List, Dict, Any
import requests
from bs4 import BeautifulSoup

from job_assistant.engine.discovery.europe_specialist_boards import enrich_vacancy_metadata
from job_assistant.engine.discovery.linkedin_scraper import search_linkedin_jobs

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def scan_greenhouse_board(board_token: str, company_name: str, filter_kws: str = "", filter_loc: str = "") -> List[Dict[str, Any]]:
    """Fetches vacancies from a company's public Greenhouse board."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    results = []
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=12)
        if resp.status_code == 200:
            data = resp.json().get("jobs", [])
            kw_list = [k.strip().lower() for k in filter_kws.split(",") if k.strip()]
            loc_list = [l.strip().lower() for l in filter_loc.split(",") if l.strip()]

            for item in data:
                title = item.get("title", "")
                loc = (item.get("location") or {}).get("name", "")
                combined = f"{title} {loc}".lower()

                if kw_list and not any(k in combined for k in kw_list):
                    continue
                if loc_list and not any(l in combined for l in loc_list):
                    continue

                desc_raw = item.get("content", "")
                clean_desc = re.sub(r"<[^>]+>", " ", desc_raw)
                clean_desc = re.sub(r"\s+", " ", clean_desc).strip()[:3000]

                results.append(enrich_vacancy_metadata({
                    "title": title,
                    "company": company_name,
                    "location": loc or "Remote / Unspecified",
                    "remote_type": "Remote" if "remote" in loc.lower() else "Hybrid",
                    "job_url": item.get("absolute_url", ""),
                    "source": f"Company ({company_name})",
                    "description": clean_desc,
                    "published_at": (item.get("updated_at") or "")[:10]
                }))
    except Exception as e:
        print(f"[CustomSource:Greenhouse] Error for '{company_name}': {e}")
    return results


def scan_lever_board(company_slug: str, company_name: str, filter_kws: str = "", filter_loc: str = "") -> List[Dict[str, Any]]:
    """Fetches vacancies from a company's public Lever API."""
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    results = []
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            kw_list = [k.strip().lower() for k in filter_kws.split(",") if k.strip()]
            loc_list = [l.strip().lower() for l in filter_loc.split(",") if l.strip()]

            for item in data:
                title = item.get("text", "")
                categories = item.get("categories", {})
                loc = categories.get("location", "")
                workplace = item.get("workplaceType", "")
                combined = f"{title} {loc} {workplace}".lower()

                if kw_list and not any(k in combined for k in kw_list):
                    continue
                if loc_list and not any(l in combined for l in loc_list):
                    continue

                desc_raw = item.get("descriptionPlain", "") or item.get("description", "")
                clean_desc = re.sub(r"\s+", " ", desc_raw).strip()[:3000]

                remote_type = "Remote" if (workplace == "remote" or "remote" in loc.lower()) else "Hybrid"
                results.append(enrich_vacancy_metadata({
                    "title": title,
                    "company": company_name,
                    "location": loc or "Remote / Unspecified",
                    "remote_type": remote_type,
                    "job_url": item.get("hostedUrl", ""),
                    "source": f"Company ({company_name})",
                    "description": clean_desc,
                    "published_at": ""
                }))
    except Exception as e:
        print(f"[CustomSource:Lever] Error for '{company_name}': {e}")
    return results


def scan_custom_webpage_or_rss(source_name: str, target_url: str, filter_kws: str = "") -> List[Dict[str, Any]]:
    """Fetches a generic job board or company career page and parses job postings."""
    results = []
    if not target_url or not target_url.startswith(("http://", "https://")):
        return results

    try:
        resp = requests.get(target_url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if resp.status_code != 200:
            return results

        kw_list = [k.strip().lower() for k in filter_kws.split(",") if k.strip()]
        soup = BeautifulSoup(resp.text, "html.parser")

        # Check for RSS items
        items = soup.find_all("item")
        if items:
            for item in items[:25]:
                t = item.find("title")
                l = item.find("link")
                d = item.find("description")
                title = t.text.strip() if t else ""
                link = l.text.strip() if l else target_url
                desc = d.text.strip() if d else ""

                if kw_list and not any(k in f"{title} {desc}".lower() for k in kw_list):
                    continue

                results.append(enrich_vacancy_metadata({
                    "title": title,
                    "company": source_name,
                    "location": "See posting",
                    "job_url": link,
                    "source": f"Custom Feed ({source_name})",
                    "description": desc[:2500]
                }))
            return results

        # Otherwise parse HTML anchors that look like job postings
        links = soup.find_all("a", href=True)
        job_links_seen = set()
        for a in links:
            href = a["href"]
            text = a.get_text(" ").strip()
            if len(text) < 5 or len(text) > 90:
                continue

            low_href = href.lower()
            low_text = text.lower()
            is_job_link = any(k in low_href or k in low_text for k in ["/job/", "/jobs/", "/careers/", "/position/", "/opening/", "apply", "vacanc"])
            if not is_job_link:
                continue

            if kw_list and not any(k in low_text for k in kw_list):
                continue

            full_url = urllib.parse.urljoin(target_url, href)
            if full_url in job_links_seen:
                continue
            job_links_seen.add(full_url)

            results.append(enrich_vacancy_metadata({
                "title": text,
                "company": source_name,
                "location": "See posting",
                "job_url": full_url,
                "source": f"Site ({source_name})",
                "description": f"Position listed on {source_name} ({target_url})."
            }))
            if len(results) >= 20:
                break
    except Exception as e:
        print(f"[CustomSource:Web] Error scanning '{target_url}': {e}")
    return results


def execute_custom_source_scan(source_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Executes a scan for a specific custom source configuration."""
    stype = source_dict.get("source_type", "company_career_page")
    sname = source_dict.get("source_name", "Custom Source")
    turl = (source_dict.get("target_url") or "").strip()
    kws = source_dict.get("query_keywords", "")
    loc = source_dict.get("target_location", "")

    # Auto-detect ATS type from URL
    if "greenhouse.io" in turl:
        m = re.search(r"greenhouse\.io/(?:embed/job_board\?for=|v1/boards/|)([^/?#]+)", turl)
        token = m.group(1) if m else sname.lower().replace(" ", "")
        return scan_greenhouse_board(token, sname, filter_kws=kws, filter_loc=loc)

    if "lever.co" in turl:
        m = re.search(r"lever\.co/([^/?#]+)", turl)
        token = m.group(1) if m else sname.lower().replace(" ", "")
        return scan_lever_board(token, sname, filter_kws=kws, filter_loc=loc)

    if stype == "custom_search_query" or (not turl and (kws or loc)):
        search_kw = kws or sname
        search_loc = loc or "European Union"
        found = search_linkedin_jobs(search_kw, search_loc, max_results=12)
        return [enrich_vacancy_metadata(j) for j in found]

    # Standard webpage / RSS feed
    return scan_custom_webpage_or_rss(sname, turl, filter_kws=kws)
