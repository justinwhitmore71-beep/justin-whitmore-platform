"""
Seed definitions for the three independent user accounts and personalized AI recruiters:
1. Justin Murrel Whitmore (User + Administrator)
2. Işıl (Independent User — Verification Gate active until she confirms preliminary items)
3. Lindsey Whitmore (Independent User — Leave-Malta Remote-First Europe Strategy + Date/Title Verification Gate)
"""

from typing import Dict, Any, List


DEFAULT_SCHEDULE_CONFIG = {
    "enabled": True,
    "timezone": "Europe/Paris",
    "jobs": {
        "morning_discovery": "08:00",
        "morning_scoring": "08:30",
        "morning_prep": "09:00",
        "morning_digest": "09:30",
        "afternoon_check": "16:00"
    },
    "auto_prep_min_score": 82,
    "auto_prep_max_daily": 3
}


def get_seed_users() -> List[Dict[str, Any]]:
    return [
        # =====================================================================
        # USER 1: JUSTIN MURREL WHITMORE
        # =====================================================================
        {
            "slug": "justin",
            "full_name": "Justin Murrel Whitmore",
            "email": "justinwhitmore71@gmail.com",
            "is_admin": True,
            "account_status": "active",
            "profile_verified": True,
            "profile": {
                "personal": {
                    "full_name": "Justin Murrel Whitmore",
                    "email": "justinwhitmore71@gmail.com",
                    "phone": "+33 6 04 50 25 42",
                    "current_location": "Near Orléans, France",
                    "current_country": "France",
                    "open_to_relocation_europe": True,
                    "car_available": False
                },
                "citizenships": ["French", "American"],
                "work_authorization": {
                    "eu_eea_free_movement": True,
                    "us_authorized": True,
                    "france_authorized": True,
                    "requires_eu_sponsorship": False,
                    "summary": "Dual French (EU) & US citizen — full unrestricted right to live and work across France, the European Union/EEA, and the United States without sponsorship."
                },
                "languages": [
                    {"language": "English", "level": "C2 / Native-level", "can_work_professionally": True, "verified": True},
                    {"language": "French", "level": "Professional working proficiency (B2 / solid B1-B2)", "can_work_professionally": True, "verified": True, "note": "Comfortable with professional workplace communication and day-to-day operations in French."}
                ],
                "experience": [
                    {
                        "id": "quidelortho",
                        "title": "Customer Service Representative / International Logistics & Export Coordinator (EMEA)",
                        "company": "QuidelOrtho",
                        "location": "Prague, Czech Republic",
                        "start_date": "Feb 2025",
                        "end_date": "Jun 2026",
                        "verified": True,
                        "highlights": [
                            "Managed EMEA export customer service and B2B order coordination across 9 international markets.",
                            "Executed daily SAP order management including VA32, ZBL, and ZDR workflows, credit block resolution, and ship-to modifications.",
                            "Prepared and verified complete export shipping documentation: commercial invoices, packing lists, Certificates of Analysis (CoA), airway bills (AWB), EX-1 customs declarations, Certificates of Origin, and outbound deliveries.",
                            "Coordinated urgent and cold-chain shipments across Sales, Finance, Supply Chain, and Logistics teams."
                        ]
                    },
                    {
                        "id": "captain_words",
                        "title": "Freelance Content Writer",
                        "company": "Captain Words",
                        "location": "Remote",
                        "start_date": "2024",
                        "end_date": "Present",
                        "verified": True,
                        "highlights": [
                            "Produce clear, researched English-language articles to strict briefs and deadlines with minimal supervision."
                        ]
                    },
                    {
                        "id": "accolade",
                        "title": "Claims & Benefits Specialist",
                        "company": "Accolade",
                        "location": "Prague / Hybrid",
                        "start_date": "May 2023",
                        "end_date": "Sep 2024",
                        "verified": True,
                        "highlights": [
                            "Supported customers on complex, high-volume cases across phone and digital channels with clear explanations.",
                            "Investigated non-standard escalations across internal teams and external providers through full resolution.",
                            "Maintained strict data confidentiality and accurate CRM case documentation."
                        ]
                    },
                    {
                        "id": "netbilling",
                        "title": "Sales and Customer Service Agent / Manager",
                        "company": "Netbilling",
                        "location": "Remote",
                        "start_date": "Mar 2022",
                        "end_date": "Dec 2022",
                        "verified": True,
                        "highlights": [
                            "Handled sales, billing inquiries, account management, and customer complaint resolution for an online payment platform.",
                            "Coached team members, set operational priorities, and acted as escalation point for complex cases."
                        ]
                    },
                    {
                        "id": "besedo",
                        "title": "Customer Service & Team Manager / Sports Trading Manager",
                        "company": "Besedo",
                        "location": "Malta",
                        "start_date": "Jun 2018",
                        "end_date": "Oct 2021",
                        "verified": True,
                        "highlights": [
                            "Progressed from customer service into managing an operational team of approximately 15 employees in a live 24/7 international operation.",
                            "Directed iGaming sports trading and customer service operations, coaching staff on quality KPIs and resolving high-priority escalations."
                        ]
                    }
                ],
                "education": [
                    {
                        "degree": "BA in Physics",
                        "institution": "University of San Diego",
                        "dates": "2012",
                        "verified": True
                    }
                ],
                "skills": [
                    {"name": "SAP (VA32, ZBL, ZDR, Credit Blocks, Ship-to, Deliveries)", "verified": True},
                    {"name": "EMEA Export Documentation (EX-1, AWB, CoA, COO, Invoices, Packing Lists)", "verified": True},
                    {"name": "Order Management & Supply Chain Coordination", "verified": True},
                    {"name": "Customer Experience, Support & Complaint Resolution", "verified": True},
                    {"name": "Team Leadership & Coaching (~15 direct reports)", "verified": True},
                    {"name": "iGaming Sports Trading & Payment Operations", "verified": True},
                    {"name": "CRM Platforms, Microsoft Excel, Word, Outlook & AI Workflow Tools", "verified": True}
                ],
                "verification_prompts": [],
                "preferences": {
                    "target_roles": [
                        "Sports Trading / Sportsbook Specialist",
                        "Sports Trader (Pre-match & In-play Operations)",
                        "Sportsbook Risk & Odds Trading Analyst",
                        "iGaming Operations & Trading Team Manager",
                        "Order Management & EMEA Export Logistics",
                        "Customer Operations & Team Leadership",
                        "English-speaking Administrative & Remote Operations"
                    ],
                    "ranked_destinations": ["France (Orléans & Nationwide)", "Portugal (Lisbon)", "Remote (Accessible from France)", "Spain", "Netherlands", "Ireland", "Germany"],
                    "excluded_countries": ["Malta"],
                    "remote_preference": "remote_or_accessible_onsite",
                    "relocation_open": True,
                    "car_available": False,
                    "france_immediate_stability_boost": True,
                    "salary_expectation": {
                        "currency": "EUR",
                        "min_annual_gross": 24000,
                        "target_annual_gross": 36000,
                        "flexible_for_stability": True
                    }
                },
                "scoring_weights": {
                    "experience_skills": 35,
                    "language_compatibility": 25,
                    "location_remote_transit": 25,
                    "work_auth_and_contract": 15,
                    "france_practical_stability_enabled": True
                },
                "schedule": {
                    **DEFAULT_SCHEDULE_CONFIG,
                    "timezone": "Europe/Paris"
                }
            }
        },

        # =====================================================================
        # USER 2: IŞIL
        # =====================================================================
        {
            "slug": "isil",
            "full_name": "Işıl",
            "email": "isil@pending-verification.local",
            "is_admin": False,
            "account_status": "pending_verification",
            "profile_verified": False,
            "profile": {
                "personal": {
                    "full_name": "Işıl",
                    "email": "",
                    "phone": "",
                    "nationality": "Turkish",
                    "current_location": "Prague, Czech Republic",
                    "current_country": "Czech Republic",
                    "career_note": "Currently returning from a planned career break following maternity leave.",
                    "open_to_relocation_with_sponsorship": True
                },
                "citizenships": ["Turkish"],
                "work_authorization": {
                    "eu_eea_free_movement": False,
                    "france_authorized": False,
                    "czech_resident_verify_permit_type": True,
                    "requires_eu_sponsorship": True,
                    "summary": "Turkish national currently residing in Prague, Czech Republic. Does NOT currently hold French work authorization or automatic EU-wide freedom of movement. Verify Czech labor market access / permit status per vacancy and require visa/relocation sponsorship for moves to other EU countries."
                },
                "languages": [
                    {"language": "Turkish", "level": "Native", "can_work_professionally": True, "verified": True},
                    {"language": "English", "level": "C2 (Fluent / Academic & Professional)", "can_work_professionally": True, "verified": True},
                    {"language": "Czech", "level": "Not assumed / None", "can_work_professionally": False, "verified": True},
                    {"language": "French", "level": "None", "can_work_professionally": False, "verified": True}
                ],
                "experience": [
                    {
                        "id": "isil_accolade",
                        "title": "Customer Support / Onboarding Specialist (Confirm Exact Title)",
                        "company": "Accolade",
                        "location": "Prague, Czech Republic",
                        "start_date": "Nov 2023",
                        "end_date": "Mar 2025",
                        "verified": True,
                        "dates_verified": True,
                        "highlights": [
                            "Delivered high-empathy English-language customer support and member onboarding assistance.",
                            "Guided customers through complex processes, documentation, and issue resolution."
                        ]
                    },
                    {
                        "id": "isil_teaching",
                        "title": "University English Instructor / Lecturer",
                        "company": "University (Please confirm institution name)",
                        "location": "Turkey (Please confirm location)",
                        "start_date": "Confirm start date",
                        "end_date": "Confirm end date",
                        "verified": True,
                        "dates_verified": False,
                        "highlights": [
                            "Taught university-level English courses, developing curriculum materials, assessments, and student communication fluency.",
                            "Strong foundation in structured onboarding, training delivery, and cross-cultural communication."
                        ]
                    },
                    {
                        "id": "isil_amazon_prelim",
                        "title": "Onboarding Specialist (Preliminary — Please Confirm)",
                        "company": "Amazon",
                        "location": "Confirm location",
                        "start_date": "Confirm dates",
                        "end_date": "Confirm dates",
                        "verified": False,
                        "dates_verified": False,
                        "highlights": [
                            "[PRELIMINARY - Excluded from CVs until confirmed by Işıl] Customer / employee onboarding workflows."
                        ]
                    }
                ],
                "education": [
                    {
                        "degree": "Master's Degree (Please provide exact title)",
                        "institution": "Please provide university name",
                        "dates": "Please provide graduation year",
                        "verified": False
                    },
                    {
                        "degree": "Bachelor's Degree (Please provide exact title)",
                        "institution": "Please provide university name",
                        "dates": "Please provide graduation year",
                        "verified": False
                    }
                ],
                "skills": [
                    {"name": "English C2 & Native Turkish Communication", "verified": True},
                    {"name": "Customer Support & Customer Onboarding", "verified": True},
                    {"name": "University-Level English Teaching & Training", "verified": True},
                    {"name": "Salesforce", "verified": False},
                    {"name": "iCIMS", "verified": False},
                    {"name": "OnBase", "verified": False},
                    {"name": "Amazon Onboarding Workflows", "verified": False}
                ],
                "verification_prompts": [
                    "Confirm your preferred contact email and phone number.",
                    "Confirm your exact Czech residence/work permit status in Prague (e.g., free access to Czech labor market vs. employer sponsorship needed).",
                    "Verify whether you worked with Amazon onboarding, Salesforce, iCIMS, and OnBase (and in which roles).",
                    "Provide exact degree titles, university names, and graduation dates for your Bachelor's and Master's degrees.",
                    "Confirm exact university name and dates for your University English teaching role."
                ],
                "preferences": {
                    "target_roles": [
                        "English-speaking Customer Support",
                        "Customer Experience",
                        "Customer Success",
                        "Customer Onboarding",
                        "English Teaching / Corporate Trainer",
                        "Turkish Teaching / Turkish Language Specialist",
                        "Translation & Localization (English <-> Turkish)",
                        "Customer Operations",
                        "Remote International Support / Onboarding"
                    ],
                    "ranked_destinations": [
                        "Prague, Czech Republic",
                        "Remote (Accessible from Czechia)",
                        "Czech Republic Nationwide",
                        "European Union (Only with Visa & Relocation Sponsorship)"
                    ],
                    "excluded_countries": [],
                    "remote_preference": "prague_hybrid_or_remote",
                    "relocation_open": True,
                    "requires_visa_for_other_eu": True,
                    "salary_expectation": {
                        "currency": "CZK / EUR",
                        "min_annual_gross": 26000,
                        "target_annual_gross": 38000,
                        "flexible_for_stability": True
                    }
                },
                "scoring_weights": {
                    "experience_skills": 30,
                    "language_compatibility": 30,
                    "location_remote_transit": 20,
                    "work_auth_and_contract": 20
                },
                "schedule": {
                    **DEFAULT_SCHEDULE_CONFIG,
                    "timezone": "Europe/Prague"
                }
            }
        },

        # =====================================================================
        # USER 3: LINDSEY WHITMORE
        # =====================================================================
        {
            "slug": "lindsey",
            "full_name": "Lindsey Whitmore",
            "email": "lindsey@pending-verification.local",
            "is_admin": False,
            "account_status": "pending_verification",
            "profile_verified": False,
            "profile": {
                "personal": {
                    "full_name": "Lindsey Whitmore",
                    "email": "",
                    "phone": "",
                    "current_location": "Malta (Actively Relocating to Mainland Europe / Remote EU)",
                    "current_country": "Malta",
                    "leave_current_country_mandatory": True,
                    "open_to_relocation_europe": True
                },
                "citizenships": ["French", "American"],
                "work_authorization": {
                    "eu_eea_free_movement": True,
                    "us_authorized": True,
                    "france_authorized": True,
                    "requires_eu_sponsorship": False,
                    "summary": "Dual French (EU) & US citizen — full right to live and work in any EU/EEA country immediately without visa sponsorship. Primary objective: Leave Malta via fully remote European employment or relocation to another European hub."
                },
                "languages": [
                    {"language": "English", "level": "C2 / Native-level", "can_work_professionally": True, "verified": True}
                ],
                "experience": [
                    {
                        "id": "lindsey_patrianna",
                        "title": "Player Operations Performance Manager",
                        "company": "Patrianna",
                        "location": "iGaming / Remote / Malta",
                        "start_date": "Verify start date",
                        "end_date": "Verify end date",
                        "verified": True,
                        "dates_verified": False,
                        "highlights": [
                            "Lead player operations performance, operational KPIs, quality assurance, and team workflows."
                        ]
                    },
                    {
                        "id": "lindsey_betmaster",
                        "title": "AML & Responsible Gambling Manager",
                        "company": "Betmaster",
                        "location": "iGaming",
                        "start_date": "Verify start date",
                        "end_date": "Verify end date",
                        "verified": True,
                        "dates_verified": False,
                        "highlights": [
                            "Managed Anti-Money Laundering (AML) controls, Responsible Gambling (RG) frameworks, regulatory escalations, and operational compliance."
                        ]
                    },
                    {
                        "id": "lindsey_kwiff_comp",
                        "title": "Compliance Executive",
                        "company": "kwiff",
                        "location": "iGaming",
                        "start_date": "Verify start date",
                        "end_date": "Verify end date",
                        "verified": True,
                        "dates_verified": False,
                        "highlights": [
                            "Executed regulatory compliance monitoring, AML/RG policy enforcement, and audit readiness."
                        ]
                    },
                    {
                        "id": "lindsey_kwiff_risk",
                        "title": "Risk, Payments & Fraud Agent",
                        "company": "kwiff",
                        "location": "iGaming",
                        "start_date": "Verify start date",
                        "end_date": "Verify end date",
                        "verified": True,
                        "dates_verified": False,
                        "highlights": [
                            "Conducted payment processing reviews, fraud detection, risk profiling, and chargeback mitigation."
                        ]
                    },
                    {
                        "id": "lindsey_casumo",
                        "title": "KYC & Fraud Analyst",
                        "company": "Casumo",
                        "location": "iGaming",
                        "start_date": "Verify start date",
                        "end_date": "Verify end date",
                        "verified": True,
                        "dates_verified": False,
                        "highlights": [
                            "Performed customer due diligence (CDD/EDD), KYC verification, and fraud investigations."
                        ]
                    },
                    {
                        "id": "lindsey_comeon",
                        "title": "Payments & Fraud Analyst / Shift Lead",
                        "company": "ComeOn!",
                        "location": "iGaming",
                        "start_date": "Verify start date",
                        "end_date": "Verify end date",
                        "verified": True,
                        "dates_verified": False,
                        "highlights": [
                            "Supervised shift operations while managing payment queues, fraud screening, and escalations."
                        ]
                    },
                    {
                        "id": "lindsey_arringo",
                        "title": "Payments & Fraud Analyst",
                        "company": "ARRINGO",
                        "location": "Fintech / Operations",
                        "start_date": "Verify start date",
                        "end_date": "Verify end date",
                        "verified": True,
                        "dates_verified": False,
                        "highlights": [
                            "Monitored payment transactions, chargebacks, and fraud indicators."
                        ]
                    }
                ],
                "education": [],
                "skills": [
                    {"name": "Player Operations & Performance Management", "verified": True},
                    {"name": "Anti-Money Laundering (AML) & Responsible Gambling (RG)", "verified": True},
                    {"name": "KYC, CDD/EDD & Regulatory Compliance", "verified": True},
                    {"name": "Fraud Prevention, Fraud Investigations & Risk Management", "verified": True},
                    {"name": "Payments Operations & Chargebacks", "verified": True},
                    {"name": "Quality Assurance & Team / Shift Leadership", "verified": True}
                ],
                "verification_prompts": [
                    "Confirm exact employment start/end dates and exact titles for Patrianna, Betmaster, kwiff, Casumo, ComeOn!, and ARRINGO (or upload your current CV to auto-fill).",
                    "Add any education, AML/Compliance certifications (e.g., ICA / ACAMS if held), and tools you want highlighted.",
                    "Rank your preferred European countries to relocate to or work remotely from, and add any countries you wish to exclude."
                ],
                "preferences": {
                    "strategy": "remote_first_leave_malta_europe",
                    "target_roles": [
                        "Player Operations Manager / Head of Player Operations",
                        "Operations Manager (iGaming / Fintech)",
                        "AML & Responsible Gambling Manager",
                        "Compliance Manager / Senior Compliance Specialist",
                        "Risk, Fraud & Payments Manager",
                        "KYC / EDD & Fraud Operations Lead",
                        "Fintech Risk & Payments Operations"
                    ],
                    "ranked_destinations": [
                        "Remote across European Union (Work outside Malta)",
                        "Portugal",
                        "Spain",
                        "France",
                        "Netherlands",
                        "Ireland",
                        "Germany",
                        "Cyprus",
                        "Czech Republic",
                        "Poland",
                        "Estonia"
                    ],
                    "excluded_countries": ["Malta (On-site / Hybrid)"],
                    "block_malta_onsite_hybrid": True,
                    "remote_preference": "remote_first_eu_eligible",
                    "relocation_open": True,
                    "salary_expectation": {
                        "currency": "EUR",
                        "min_annual_gross": 45000,
                        "target_annual_gross": 65000,
                        "flexible_for_stability": False
                    }
                },
                "scoring_weights": {
                    "experience_skills": 35,
                    "location_remote_leave_malta": 35,
                    "language_compatibility": 15,
                    "work_auth_and_contract": 15
                },
                "schedule": {
                    **DEFAULT_SCHEDULE_CONFIG,
                    "timezone": "Europe/Malta"
                }
            }
        },

        # =====================================================================
        # USER 4: LAURENCE WHITMORE (Mom — Profile & Preferences Onboarding)
        # =====================================================================
        {
            "slug": "laurence",
            "full_name": "Laurence Whitmore",
            "email": "laurence@pending-verification.local",
            "is_admin": False,
            "account_status": "pending_verification",
            "profile_verified": False,
            "profile": {
                "personal": {
                    "full_name": "Laurence Whitmore",
                    "email": "",
                    "phone": "",
                    "current_location": "France (or Remote)",
                    "current_country": "France",
                    "open_to_relocation_europe": False,
                    "car_available": True
                },
                "citizenships": ["French"],
                "work_authorization": {
                    "eu_eea_free_movement": True,
                    "france_authorized": True,
                    "requires_eu_sponsorship": False,
                    "summary": "Full unrestricted right to live and work in France and throughout the European Union without visa sponsorship."
                },
                "languages": [
                    {"language": "French", "level": "Native / Fluent", "can_work_professionally": True, "verified": True},
                    {"language": "English", "level": "Professional / Working", "can_work_professionally": True, "verified": True}
                ],
                "experience": [],
                "education": [],
                "skills": [],
                "verification_prompts": [
                    "Specify what industries or roles you are searching for (e.g., Administration, Client Services, Operations, Retail, Healthcare, Education, Remote).",
                    "Confirm your current location and commuting radius (e.g., Orléans area, Loiret, or Remote).",
                    "Upload your CV to automatically extract your previous positions, qualifications, and skills."
                ],
                "preferences": {
                    "target_roles": [
                        "General Administration / Office Coordination",
                        "Customer Relations / Client Services",
                        "Operations & Team Coordination",
                        "Remote Customer Support",
                        "Bilingual French / English Roles"
                    ],
                    "ranked_destinations": ["France (Local & Nationwide)", "Remote (France / Europe)"],
                    "excluded_countries": [],
                    "remote_preference": "open_to_remote_or_local",
                    "relocation_open": False,
                    "salary_expectation": {
                        "currency": "EUR",
                        "min_annual_gross": 24000,
                        "target_annual_gross": 35000,
                        "flexible_for_stability": True
                    }
                },
                "scoring_weights": {
                    "experience_skills": 30,
                    "language_compatibility": 30,
                    "location_remote_transit": 25,
                    "work_auth_and_contract": 15
                },
                "schedule": {
                    **DEFAULT_SCHEDULE_CONFIG,
                    "timezone": "Europe/Paris"
                }
            }
        }
    ]
