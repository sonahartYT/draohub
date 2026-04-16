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
# Claude API tagger
# ---------------------------------------------------------------------------

_CLAUDE_SYSTEM_PROMPT = """You are classifying Nigerian oil & gas job listings into structured tags.

Given a job title and company name, return ONLY a valid JSON object — no explanation, no markdown.

TAXONOMY (use exactly these values):

category (pick the ONE primary function of the role):
  Engineering | HSE | Operations | Finance | IT/Digital | Legal/Contracts |
  Management | HR | Project Management | Other

discipline (O&G sub-speciality — null if not clearly a technical/engineering role):
  Drilling | Reservoir | Production | Subsurface | Facilities |
  Marine/Offshore | Geoscience | Instrumentation | Chemical/Process |
  Project Management | null

seniority:
  Graduate/Entry | Mid-Level | Senior | Manager | Executive

employment_type:
  Full-time | Contract | Internship

skills: array of up to 5 specific O&G tools, certifications, or technical skills
  clearly implied by the title (e.g. ["HSSE", "SAP", "NEBOSH", "Petrel", "IWCF"])
  Use [] if nothing specific is implied.

RULES:
- Base classification ONLY on the job title. Ignore company name unless the title is ambiguous.
- category = the PRIMARY job function, not keywords in a description.
  e.g. "Facilities Engineer" → Engineering (not HSE even if safety is involved)
  e.g. "SAP Consultant" → IT/Digital
  e.g. "Contracts Administrator" → Legal/Contracts
  e.g. "Business Development Manager" → Management or Operations (not HSE)
  e.g. "Sustainability Analyst" → HSE only if clearly environmental/safety focused
- discipline = null for non-engineering roles (Finance, HR, IT, Legal, Management, HSE)
- seniority clues: "Graduate/Trainee/Intern/NYSC/Entry" → Graduate/Entry,
  "Senior/Lead/Principal/Specialist" → Senior,
  "Manager/Head/Superintendent/Team Lead" → Manager,
  "Director/VP/Chief/GM/MD" → Executive,
  everything else → Mid-Level
- employment_type: "Contract/Contractor/Temporary" → Contract,
  "Intern/Industrial Training/NYSC" → Internship, else Full-time

Output format (strict JSON, no other text):
{"category":"...","discipline":null,"seniority":"...","employment_type":"...","skills":[]}"""

_VALID_CATEGORIES = {
    "Engineering", "HSE", "Operations", "Finance", "IT/Digital",
    "Legal/Contracts", "Management", "HR", "Project Management", "Other"
}
_VALID_DISCIPLINES = {
    "Drilling", "Reservoir", "Production", "Subsurface", "Facilities",
    "Marine/Offshore", "Geoscience", "Instrumentation", "Chemical/Process",
    "Project Management", None
}
_VALID_SENIORITIES = {"Graduate/Entry", "Mid-Level", "Senior", "Manager", "Executive"}
_VALID_EMPLOYMENT = {"Full-time", "Contract", "Internship"}


def _validate_claude_response(data: dict) -> dict:
    """Ensure Claude's response has valid values; fall back to safe defaults."""
    return {
        "category":        data.get("category") if data.get("category") in _VALID_CATEGORIES else "Other",
        "discipline":      data.get("discipline") if data.get("discipline") in _VALID_DISCIPLINES else None,
        "seniority":       data.get("seniority") if data.get("seniority") in _VALID_SENIORITIES else "Mid-Level",
        "employment_type": data.get("employment_type") if data.get("employment_type") in _VALID_EMPLOYMENT else "Full-time",
        "skills":          [s for s in (data.get("skills") or []) if isinstance(s, str)][:5],
        "tagger":          "claude",
    }


def _claude_tagger(job: dict) -> dict:
    """
    Tag one job using Claude 3 Haiku. Falls back to rule-based on any error.
    Cost: ~$0.000087 per job (~$0.13/month at current volume).
    """
    import anthropic
    import json as _json

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set — cannot use Claude tagger")

    title   = (job.get("job_title") or job.get("title") or "").strip()
    company = (job.get("company") or "").strip()

    if not title:
        return _rule_based_tagger(job)

    client = anthropic.Anthropic(api_key=anthropic_key)
    user_msg = f'Title: "{title}"\nCompany: "{company}"'

    msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=150,
        system=_CLAUDE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = msg.content[0].text.strip()

    # Strip markdown code fences if Claude adds them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    data = _json.loads(raw)
    return _validate_claude_response(data)


def tag_jobs_batch_claude(jobs: list[dict]) -> list[dict]:
    """
    Tag multiple jobs in a single Claude API call (10 per call).
    Used by batch_tag.py for efficiency. Returns list of tags dicts.
    Falls back to one-by-one on parse error.
    """
    import anthropic
    import json as _json

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=anthropic_key)

    lines = []
    for i, job in enumerate(jobs, 1):
        title   = (job.get("job_title") or job.get("title") or "").strip()
        company = (job.get("company") or "").strip()
        lines.append(f'{i}. Title: "{title}" | Company: "{company}"')

    user_msg = (
        "Classify each job. Return a JSON array with one object per job, "
        "in the same order. Each object must follow the taxonomy exactly.\n\n"
        + "\n".join(lines)
    )

    msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=150 * len(jobs),
        system=_CLAUDE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    results = _json.loads(raw)
    if not isinstance(results, list) or len(results) != len(jobs):
        raise ValueError(f"Expected {len(jobs)} results, got {len(results) if isinstance(results, list) else type(results)}")

    return [_validate_claude_response(r) for r in results]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def tag_job(job: dict) -> dict:
    """
    Tag a single job dict. Returns a tags dict. Never raises.

    Switch backends via TAGGER_BACKEND env var:
        TAGGER_BACKEND=rule-based  (default)
        TAGGER_BACKEND=claude
    """
    try:
        if TAGGER_BACKEND == "claude":
            return _claude_tagger(job)
        return _rule_based_tagger(job)
    except Exception as exc:
        logger.error("tag_job failed for %r: %s", job.get("job_title"), exc)
        # Always fall back to rule-based — never drop a job
        try:
            tags = _rule_based_tagger(job)
            tags["tagger"] = "rule-based-fallback"
            return tags
        except Exception:
            return {
                "category":        "Other",
                "discipline":      None,
                "seniority":       "Mid-Level",
                "employment_type": "Full-time",
                "skills":          [],
                "tagger":          "fallback",
            }
