"""
France Travail (Pôle Emploi) Scraper.
Discovers local opportunities in Orléans / Loiret (45) across:
1. English-speaking customer service, export, ADV, logistics
2. Practical immediate-income opportunities (Warehouse, logistics preparation, order picking, production)
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


def search_france_travail(mots_cles: str, lieu: str = "45234", max_results: int = 20) -> List[Dict[str, Any]]:
    """
    Searches France Travail offers.
    lieu default '45234' = Orléans. Can also be '45' for Loiret.
    """
    results = []
    base_url = "https://candidat.francetravail.fr/offres/recherche"
    params = {
        "motsCles": mots_cles,
        "lieux": lieu,
        "offresPartenaires": "true",
        "tri": "0"  # Most recent
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if resp.status_code != 200:
            return results

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.find_all("li", class_="result")

        for item in items[:max_results]:
            # Extract detail link
            link_tag = item.find("a", href=True)
            if not link_tag:
                continue
            detail_path = link_tag["href"]
            job_url = f"https://candidat.francetravail.fr{detail_path}" if detail_path.startswith("/") else detail_path

            # Extract title and company
            spans = item.find_all("span")
            # Usually span[2] has the title text in FT
            title = ""
            for s in spans:
                text = s.text.strip()
                if len(text) > 5 and not text.startswith("(") and text != "Temps plein" and text != "Temps partiel":
                    title = text
                    break
            if not title:
                title = link_tag.text.strip().split("\n")[0]

            sub_title_p = item.find("p", class_="sub-title")
            company = sub_title_p.text.strip() if sub_title_p else "Entreprise anonyme"

            loc_p = item.find("p", class_="location") or item.find("span", class_="location")
            loc_text = loc_p.text.strip() if loc_p else "Orléans (45)"

            desc_p = item.find("p", class_="description")
            description = desc_p.text.strip() if desc_p else ""

            # Check if practical role
            is_practical = any(k in title.lower() or k in mots_cles.lower() for k in [
                "préparateur", "manutentionnaire", "magasinier", "conditionnement", "cariste", "production", "ouvrier"
            ])

            results.append({
                "dedup_hash": _make_dedup_hash(company, title, loc_text),
                "title": title,
                "company": company,
                "location": loc_text,
                "remote_type": "On-site",
                "salary": "",
                "job_url": job_url,
                "source": "France Travail",
                "description": description,
                "date_discovered": time.strftime("%Y-%m-%d"),
                "deadline": "",
                "is_practical_role": 1 if is_practical else 0
            })
    except Exception as e:
        print(f"[FranceTravail] Error searching '{mots_cles}': {e}")

    return results


def run_targeted_france_travail_searches() -> List[Dict[str, Any]]:
    """Runs targeted searches for Orléans (45234) and Loiret, including immediate income roles."""
    queries = [
        # Immediate Income & Practical Roles (Top Priority for France)
        ("restauration rapide", "45234"),
        ("équipier polyvalent", "45234"),
        ("agent d'entretien", "45234"),
        ("agent de nettoyage", "45234"),
        ("plongeur", "45234"),
        ("mise en rayon", "45234"),
        ("hôte de caisse", "45234"),
        ("préparateur de commandes", "45234"),
        ("manutentionnaire", "45234"),
        ("agent logistique", "45234"),
        
        # Professional / English-friendly / Operations
        ("anglais", "45234"),
        ("export", "45234"),
        ("gestionnaire commandes", "45234"),
        ("service client", "45234")
    ]

    all_jobs = []
    for kw, lieu in queries:
        found = search_france_travail(kw, lieu=lieu, max_results=12)
        all_jobs.extend(found)
        time.sleep(0.8)

    return all_jobs


if __name__ == "__main__":
    jobs = search_france_travail("anglais", lieu="45234", max_results=5)
    print(f"France Travail search returned {len(jobs)} jobs.")
    for j in jobs:
        print(f"- {j['title']} @ {j['company']} ({j['location']})")
