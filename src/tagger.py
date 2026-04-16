"""
DracoHub Careers — Job tagger.

Tags each job with structured O&G metadata:
    category       : Engineering | Finance | Operations | HSE | HR |
                     IT/Digital | Legal/Contracts | Management | Other
    discipline     : Drilling | Reservoir | Production | Subsurface |
                     Facilities | Marine/Offshore | Geoscience |
                     Instrumentation | Chemical/Process | (None)
    seniority      : Graduate/Entry | Mid-Level | Senior | Manager | Executive
    employment_type: Full-time | Contract | Internship
    skills         : list[str]  (O&G-specific certifications & tools)
    tagger         : "rule-based" | "claude"  (for audit/swap tracking)

Public API
----------
    tag_job(job: dict) -> dict
        Returns a tags dict. Never raises — returns a minimal fallback on error.

Swap strategy
-------------
    When you're ready to switch to Claude API:
    1. Implement _claude_tagger(job) → dict  (same output shape)
    2. Set TAGGER_BACKEND = "claude" in config or env
    3. Nothing else changes — insert_jobs() calls tag_job() blindly.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — change TAGGER_BACKEND to "claude" to swap
# ---------------------------------------------------------------------------
import os
TAGGER_BACKEND = os.getenv("TAGGER_BACKEND", "rule-based")


# ---------------------------------------------------------------------------
# Rule-based engine
# ---------------------------------------------------------------------------

# ---- Category keywords ----
_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    # Most specific first — first match wins
    ("HSE", [
        "hse", "qhse", "safety", "health, safety", "environment",
        "environmental", "sustainability", "esg", "hsse",
    ]),
    ("Legal/Contracts", [
        "legal", "counsel", "contracts administrator", "contract manager",
        "compliance", "regulatory", "governance", "paralegal",
    ]),
    ("IT/Digital", [
        "it ", "information technology", "digital", "data scientist",
        "data analyst", "data engineer", "software", "systems engineer",
        "sap", "erp", "cybersecurity", "network", "developer",
        "devops", "business intelligence", "bi analyst", "analytics",
    ]),
    ("Finance", [
        "finance", "financial", "accounting", "accountant", "auditor",
        "audit", "tax", "treasury", "economist", "economics",
        "commercial analyst", "budget", "cost control", "cost controller",
        "cost engineer", "revenue", "trader", "trading", "commodity",
    ]),
    ("HR", [
        "human resources", " hr ", "hr manager", "hrbp", "talent",
        "recruitment", "recruiter", "learning and development",
        "organisational development", "l&d", "people partner",
        "compensation", "payroll",
    ]),
    ("Management", [
        "chief executive", "ceo", "coo", "cfo", "cto", "managing director",
        "general manager", "vice president", " vp ", "head of ",
        "director of", "country manager",
    ]),
    ("Operations", [
        "operations manager", "operations coordinator", "logistics",
        "supply chain", "procurement", "materials management",
        "warehouse", "inventory", "vendor management", "shipping",
        "superintendent", "plant manager", "terminal", "dispatcher",
    ]),
    ("Engineering", [
        "engineer", "engineering", "drilling", "reservoir", "production",
        "petroleum", "geoscience", "geophysics", "geology", "geologist",
        "geophysicist", "facilities", "process", "chemical", "mechanical",
        "civil", "structural", "electrical", "instrumentation", "control",
        "automation", "subsurface", "petrophysics", "petrophysicist",
        "marine", "offshore", "naval", "pipeline", "integrity",
        "commissioning", "construction", "project engineer",
    ]),
    ("Project Management", [
        "project manager", "project management", "pmo", "programme manager",
        "project coordinator", "project controls", "planning engineer",
        "scheduler",
    ]),
]

# ---- Discipline keywords (Engineering only) ----
_DISCIPLINE_RULES: list[tuple[str, list[str]]] = [
    ("Drilling", [
        "drilling", "well ", "wellbore", "borehole", "completion",
        "workover", "well intervention", "driller", "mud ", "cementing",
        "directional", "mwd", "lwd",
    ]),
    ("Reservoir", [
        "reservoir", "petrophysic", "simulation", "modelling", "model",
        "dynamic model", "static model", "material balance",
    ]),
    ("Production", [
        "production engineer", "production technologist", "production optim",
        "artificial lift", "nodal analysis", "well performance", "processing",
        "production chemistry",
    ]),
    ("Subsurface", [
        "subsurface", "geoscience", "geology", "geologist", "geophysic",
        "geophysicist", "seismic", "stratigraph", "sedimentolog",
        "structural geol",
    ]),
    ("Facilities", [
        "facilities", "fpso", "pipeline", "integrity", "mechanical",
        "civil", "structural", "piping", "corrosion", "rotating equipment",
        "static equipment",
    ]),
    ("Marine/Offshore", [
        "marine", "offshore", "vessel", "maritime", "naval", "port",
        "harbour", "dynamic positioning", "dp operator",
    ]),
    ("Instrumentation", [
        "instrument", "automation", "control", "scada", "dcs",
        "plc", "electrical", "e&i", "telecoms",
    ]),
    ("Chemical/Process", [
        "chemical", "process", "petrochemical", "refin", "hysys",
        "aspen", "process safety", "hazop",
    ]),
    ("Geoscience", [
        "geoscience", "geolog", "geophys", "seismic", "exploration",
    ]),
    ("Project Management", [
        "project manager", "project engineer", "pmo", "epc", "epci",
        "commissioning", "construction manager",
    ]),
]

# ---- Seniority keywords ----
_SENIORITY_RULES: list[tuple[str, list[str]]] = [
    ("Executive", [
        "chief ", "ceo", "coo", "cfo", "cto", "managing director",
        "vice president", " vp ", "general manager", "country manager",
    ]),
    ("Manager", [
        "manager", "head of", "director", "superintendent", "team lead",
        "team leader",
    ]),
    ("Senior", [
        "senior", " sr.", " sr ", "lead ", "principal", "specialist",
        "expert", "advisor", "consultant",
    ]),
    ("Graduate/Entry", [
        "graduate", "trainee", "intern", "internship", "entry level",
        "entry-level", "junior", " jr ", "fresh", "nysc", "youth corps",
        "programme", "early career",
    ]),
    # Mid-Level is the default — no explicit keywords needed
]

# ---- Employment type ----
_EMPLOYMENT_RULES: list[tuple[str, list[str]]] = [
    ("Internship", ["intern", "internship", "industrial training", "nysc"]),
    ("Contract", [
        "contract", "contractor", "temporary", " temp ", "fixed term",
        "fixed-term", "locum",
    ]),
    # Full-time is the default
]

# ---- O&G-specific skills / certifications / tools ----
_SKILLS_KEYWORDS: list[str] = [
    # Certifications
    "nebosh", "iosh", "bosiet", "huet", "iwcf", "iadc", "opito",
    "pmp", "prince2", "six sigma", "lean six sigma",
    # Software
    "sap", "oracle", "petrel", "eclipse", "pipesim", "prosper", "gap",
    "olga", "hysys", "aspen", "matlab", "python", "sql", "power bi",
    "tableau", "autocad", "pdms", "aveva", "openworks",
    # Technical
    "hpht", "h2s", "hazop", "hazid", "bow-tie", "lopa",
    "production chemistry", "flow assurance", "integrity management",
    "asset integrity", "rcm", "fmea", "risk assessment",
    "dynamic positioning", "dp",
    # Standards
    "api", "asme", "iso", "norsok", "astm", "ansi",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text(job: dict) -> str:
    """Combine title + description into a single lowercased string for matching."""
    title = (job.get("job_title") or job.get("title") or "").lower()
    desc = (job.get("description") or "")[:800].lower()
    return f"{title} {desc}"


def _match_any(text: str, keywords: list[str]) -> bool:
    return any(kw in text for kw in keywords)


def _first_match(text: str, rules: list[tuple[str, list[str]]]) -> str | None:
    for label, keywords in rules:
        if _match_any(text, keywords):
            return label
    return None


def _extract_skills(text: str) -> list[str]:
    found = []
    for skill in _SKILLS_KEYWORDS:
        # Word-boundary match (avoid partial matches in long words)
        if re.search(r'\b' + re.escape(skill) + r'\b', text):
            found.append(skill.upper() if len(skill) <= 5 else skill.title())
    return sorted(set(found))


# ---------------------------------------------------------------------------
# Rule-based tagger
# ---------------------------------------------------------------------------

def _rule_based_tagger(job: dict) -> dict:
    text = _text(job)

    category = _first_match(text, _CATEGORY_RULES) or "Other"

    discipline = None
    if category in ("Engineering", "Project Management", "Operations"):
        discipline = _first_match(text, _DISCIPLINE_RULES)

    seniority = _first_match(text, _SENIORITY_RULES) or "Mid-Level"
    employment_type = _first_match(text, _EMPLOYMENT_RULES) or "Full-time"
    skills = _extract_skills(text)

    return {
        "category":        category,
        "discipline":      discipline,
        "seniority":       seniority,
        "employment_type": employment_type,
        "skills":          skills,
        "tagger":          "rule-based",
    }


# ---------------------------------------------------------------------------
# Claude API tagger (stub — swap in when ready)
# ---------------------------------------------------------------------------

def _claude_tagger(job: dict) -> dict:
    """
    Call Claude API to tag a job. Drop-in replacement for _rule_based_tagger.

    TODO when implementing:
    1. pip install anthropic
    2. Set ANTHROPIC_API_KEY in .env
    3. Build a tight system prompt with the taxonomy above
    4. Request JSON output (use claude-3-haiku — cheapest, fast)
    5. Validate response shape before returning
    6. Fall back to _rule_based_tagger() on any error

    Estimated cost: ~$0.001 per job → ~$1/month at current volume.
    """
    raise NotImplementedError(
        "Claude tagger not yet implemented. "
        "Set TAGGER_BACKEND=rule-based or implement _claude_tagger()."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def tag_job(job: dict) -> dict:
    """
    Tag a single job dict. Returns a tags dict. Never raises.

    Switch between backends by setting TAGGER_BACKEND env var:
        TAGGER_BACKEND=rule-based  (default)
        TAGGER_BACKEND=claude
    """
    try:
        if TAGGER_BACKEND == "claude":
            return _claude_tagger(job)
        return _rule_based_tagger(job)
    except NotImplementedError:
        raise
    except Exception as exc:
        logger.error("tag_job failed for %r: %s", job.get("job_title"), exc)
        return {
            "category":        "Other",
            "discipline":      None,
            "seniority":       "Mid-Level",
            "employment_type": "Full-time",
            "skills":          [],
            "tagger":          "rule-based",
        }
