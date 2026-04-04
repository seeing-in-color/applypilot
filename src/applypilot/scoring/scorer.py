"""Job fit scoring: LLM-powered evaluation of candidate-job match quality.

Scores jobs on a 1-10 scale by comparing a **condensed candidate profile**
(identity + resume excerpt + resume-substantiated profile fields from
``profile.json`` + ``resume.txt``) to each job description. Keeps prompts short
for better model behavior.
"""

import logging
import math
import re
import sqlite3
import time
from datetime import datetime, timezone

from rich.console import Console
from rich.panel import Panel

from applypilot.config import get_apply_pilot_llm_delay
from applypilot.database import get_connection, get_jobs_by_stage, init_db
from applypilot.discovery.travel_filter import is_excessive_travel_requirement
from applypilot.llm import get_client
from applypilot.resume import ensure_clean_resume_text

log = logging.getLogger(__name__)
console = Console()

# Defaults for `applypilot run score` (overridden by CLI / pipeline)
DEFAULT_SCORE_CHUNK_SIZE = 25
DEFAULT_SCORE_CHUNK_DELAY_SEC = 5.0

# Job posting body; candidate side uses a condensed profile (not full resume).
SCORE_MAX_JOB_DESC_CHARS = 4000
# Condensed candidate profile: identity + structured resume + verified profile lines.
SCORE_MAX_PROFILE_CHARS = 3000
# Upper bound for the resume section block before fixed sections are assembled.
_RESUME_EXCERPT_BUDGET = 2300

# When True, scoring emits full diagnostic logs (job essentials, prompt sizes,
# chunk summaries). Default False: only per-job score lines + errors/warnings.
# Override per run with ``run_scoring(verbose=True)`` or CLI ``--score-verbose``.
SCORE_VERBOSE = False

# ---------------------------------------------------------------------------
# Job description → "job essentials" (heuristic, no extra LLM calls)
# ---------------------------------------------------------------------------

# Section title keywords → bucket (order in _BUCKET_RANK determines assembly priority).
_BUCKET_RANK: dict[str, int] = {
    "summary": 10,
    "role": 10,
    "resp": 20,
    "req": 30,
    "pref": 40,
    "skills": 50,
    "other": 80,
    "unknown": 90,
    "drop": 999,
    "low": 100,
}

# Titles matching these substrings are dropped (benefits, legal, boilerplate).
_DROP_TITLE_SUBSTRINGS = (
    "benefit", "perks", "what we offer", "compensation package",
    "salary and benefits", "total rewards",
    "equal opportunity", "eeo", "affirmative action",
    "diversity, equity", "de&i", "dei ",
    "privacy policy", "privacy notice", "cookie policy",
    "legal notice", "applicant privacy",
    "gdpr", "ccpa",
    "about the company", "our story", "our mission",
)

# Deprioritized (keep only if space remains after higher buckets).
_LOW_TITLE_SUBSTRINGS = (
    "our culture", "why join", "life at", "our values",
    "who we are", "meet the team",
)

# Map free-text title to bucket.
_SUMMARY_MARKERS = (
    "about the role", "about this role", "role overview", "position summary",
    "job summary", "summary", "overview", "the role", "position description",
    "description", "introduction",
)
_RESP_MARKERS = (
    "responsibilit", "what you'll do", "what you will", "key responsibilit",
    "duties", "day to day", "day-to-day", "role responsibilit",
)
_REQ_MARKERS = (
    "required qualification", "minimum qualification", "must have",
    "basic qualification", "requirements", "required skills",
    "qualification", "you have", "you need",
)
_PREF_MARKERS = (
    "preferred qualification", "nice to have", "bonus", "plus if",
    "preferred skills", "desired",
)
_SKILLS_MARKERS = (
    "skills", "technical skills", "technologies", "tools", "tech stack",
    "experience with", "years of experience", "proficiency",
)


def _normalize_header_line(line: str) -> str:
    s = line.strip()
    s = re.sub(r"^#+\s*", "", s)
    s = re.sub(r"^\*\*|\*\*$", "", s).strip()
    s = re.sub(r":\s*$", "", s)
    return s.strip()


# Common ATS / careers-site section titles (single line, no colon).
_KNOWN_SECTION_ONE_LINE = frozenset(
    {
        "about the role",
        "about this role",
        "about the position",
        "the role",
        "role overview",
        "position overview",
        "position summary",
        "job summary",
        "job description",
        "overview",
        "summary",
        "role",
        "description",
        "what you'll do",
        "what you will do",
        "what youll do",
        "day to day",
        "day-to-day",
        "key responsibilities",
        "your responsibilities",
        "responsibilities",
        "duties",
        "minimum qualifications",
        "required qualifications",
        "basic qualifications",
        "qualifications",
        "requirements",
        "required skills",
        "must have",
        "you have",
        "you will need",
        "preferred qualifications",
        "nice to have",
        "bonus points",
        "skills",
        "technical skills",
        "skills and experience",
        "skills & experience",
        "technologies",
        "tools",
        "tech stack",
        "experience",
        "education",
        "benefits",
        "perks",
        "compensation",
        "what we offer",
        "equal opportunity employer",
        "eeo statement",
        "diversity statement",
        "privacy",
        "applicant privacy",
    }
)


def _is_probable_section_header(line: str) -> bool:
    """Heuristic: line looks like a section title, not body text."""
    s = line.strip()
    if len(s) < 3 or len(s) > 140:
        return False
    norm = re.sub(r"\s+", " ", _normalize_header_line(s)).lower()
    if norm in _KNOWN_SECTION_ONE_LINE:
        return True
    if re.match(r"^#{1,6}\s+\S", s):
        return True
    if re.match(r"^\*\*.+\*\*\s*$", s):
        return True
    # Short ALL CAPS heading (avoid sentences)
    core = re.sub(r"[^A-Za-z]", "", s)
    if len(core) >= 4 and s.upper() == s and len(s) <= 70 and not s.endswith("."):
        return True
    # Short Title: or Title (no period mid-line)
    if s.endswith(":") and len(s) <= 90 and s.count(".") == 0:
        return True
    # Numbered section "1. Something" or "A."
    if re.match(r"^(\d+|[a-z])\s*[\).\]]\s+[A-Za-z]", s) and len(s) < 100:
        return True
    return False


def _classify_section_title(title: str) -> str:
    t = _normalize_header_line(title).lower()
    if any(d in t for d in _DROP_TITLE_SUBSTRINGS):
        return "drop"
    if any(d in t for d in _LOW_TITLE_SUBSTRINGS):
        return "low"
    if any(m in t for m in _SUMMARY_MARKERS):
        return "summary"
    if any(m in t for m in _RESP_MARKERS):
        return "resp"
    # Preferred BEFORE generic "qualification" / "requirements" so
    # "Preferred qualifications" maps to pref, not req.
    if any(m in t for m in _PREF_MARKERS):
        return "pref"
    if "preferred" in t and ("qualif" in t or "skill" in t or "experience" in t):
        return "pref"
    if any(m in t for m in _REQ_MARKERS):
        return "req"
    if any(m in t for m in _SKILLS_MARKERS):
        return "skills"
    if "role" in t and ("about" in t or "job" in t):
        return "role"
    return "unknown"


def _split_description_into_sections(text: str) -> list[tuple[str, str]]:
    """Split on probable headers; first block uses title ``Introduction``."""
    if not text or not str(text).strip():
        return []
    lines = str(text).replace("\r\n", "\n").split("\n")
    sections: list[tuple[str, str]] = []
    header = "Introduction"
    buf: list[str] = []

    for line in lines:
        if _is_probable_section_header(line) and buf:
            body = "\n".join(buf).strip()
            if body:
                sections.append((header, body))
            header = _normalize_header_line(line) or "Section"
            buf = []
        elif _is_probable_section_header(line) and not buf:
            header = _normalize_header_line(line) or "Section"
        else:
            buf.append(line)

    tail = "\n".join(buf).strip()
    if tail:
        sections.append((header, tail))
    return sections


def _paragraph_boilerplate_score(paragraph: str) -> float:
    """Higher = more likely junk (benefits/legal/culture); used when no headers."""
    p = paragraph.lower()[:800]
    score = 0.0
    first_line = paragraph.strip().split("\n", 1)[0].strip().lower()
    if first_line in ("benefits", "perks", "what we offer", "equal opportunity employer"):
        score += 5.0
    for d in _DROP_TITLE_SUBSTRINGS:
        if d in p:
            score += 3.0
    if "equal opportunity" in p or "eeo" in p:
        score += 5.0
    if "privacy" in p and "policy" in p:
        score += 4.0
    if re.search(r"\b401\s*\(?k\)?\b", p) or "health insurance" in p:
        score += 2.0
    if len(paragraph) > 1200 and score >= 2:
        score += 1.0
    return score


def _essentials_from_paragraphs(text: str, max_chars: int) -> tuple[str, list[str], list[str]]:
    """Fallback: filter paragraphs by boilerplate score; keep high-signal chunks."""
    paras = re.split(r"\n\s*\n+", str(text).strip())
    scored: list[tuple[float, str]] = []
    for para in paras:
        p = para.strip()
        if len(p) < 40:
            continue
        sc = _paragraph_boilerplate_score(p)
        scored.append((sc, p))
    scored.sort(key=lambda x: x[0])
    kept: list[str] = []
    dropped_labels: list[str] = []
    for sc, p in scored:
        if sc >= 4.0:
            dropped_labels.append("boilerplate_paragraph")
            continue
        kept.append(p)
    body = "\n\n".join(kept).strip()
    if not body:
        body = str(text).strip()[:max_chars]
    body, _, out_len = truncate_text(body, max_chars)
    return body, ["paragraph_filter"], list(dict.fromkeys(dropped_labels)) if dropped_labels else []


def _truncate_at_word_boundary(text: str, max_chars: int) -> str:
    suffix = "\n\n[Job essentials truncated.]"
    if len(text) <= max_chars:
        return text
    budget = max(0, max_chars - len(suffix))
    cut = text[: budget + 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    cut = cut.rstrip()
    if len(cut) + len(suffix) > max_chars:
        cut = text[:budget].rstrip()
    return cut + suffix


def extract_job_essentials_for_scoring(
    raw_description: str,
    max_chars: int,
    *,
    verbose: bool = False,
) -> tuple[str, int, int, list[str], list[str]]:
    """Build a compact *job essentials* block for scoring (no extra LLM calls).

    Returns ``(text, original_len, final_len, kept_labels, dropped_or_skipped_labels)``.
    """
    raw = str(raw_description or "").strip()
    orig_len = len(raw)
    if not raw:
        return "", orig_len, 0, [], []

    sections = _split_description_into_sections(raw)
    kept_labels: list[str] = []
    dropped_labels: list[str] = []
    pieces: list[tuple[int, str, str]] = []  # rank, label, body

    if len(sections) < 2:
        # Too few headers — paragraph-level fallback
        body, kl, dl = _essentials_from_paragraphs(raw, max_chars)
        kept_labels.extend(kl)
        dropped_labels.extend(dl)
        if verbose:
            log.info(
                "Job essentials (no clear sections): paragraph filter | raw=%d -> %d chars | kept=%s dropped=%s",
                orig_len,
                len(body),
                kept_labels or ["paragraphs"],
                dropped_labels or ["(none)"],
            )
        return body, orig_len, len(body), kept_labels, dropped_labels

    for title, body in sections:
        if not (body or "").strip():
            continue
        bucket = _classify_section_title(title)
        rank = _BUCKET_RANK.get(bucket, _BUCKET_RANK["unknown"])
        label = f"{bucket}:{title[:48]}"
        if bucket == "drop":
            dropped_labels.append(label)
            continue
        if bucket == "low":
            dropped_labels.append(f"deprioritized:{title[:48]}")
            pieces.append((_BUCKET_RANK["low"], label, body))
            continue
        kept_labels.append(label)
        pieces.append((rank, label, body))

    pieces.sort(key=lambda x: x[0])
    # Rebuild: high-value first; append low-priority only if room
    ordered_bodies: list[str] = []
    low_bodies: list[str] = []
    for rank, label, body in pieces:
        if rank >= _BUCKET_RANK["low"]:
            low_bodies.append(body)
        else:
            ordered_bodies.append(body)

    out = "\n\n---\n\n".join(ordered_bodies).strip()
    if low_bodies:
        rest = "\n\n---\n\n".join(low_bodies)
        out = (out + "\n\n---\n\n" + rest).strip() if out else rest.strip()

    if not out.strip():
        out, _, _ = truncate_text(raw, max_chars)
        kept_labels = ["(fallback: raw truncated)"]
        dropped_labels.append("(no sections retained; using raw)")

    out = _truncate_at_word_boundary(out, max_chars)
    final_len = len(out)

    if log.isEnabledFor(logging.DEBUG):
        detail = " | ".join(
            f"{t!r} -> {_classify_section_title(t)} ({len(b)} chars)"
            for t, b in sections
        )
        log.debug("Job essentials per-section: %s", detail)
    if verbose:
        log.info(
            "Job essentials: kept [%s] | skipped/dropped [%s] | raw=%d -> essentials=%d chars",
            "; ".join(kept_labels) if kept_labels else "(none)",
            "; ".join(dropped_labels) if dropped_labels else "(none)",
            orig_len,
            final_len,
        )

    return out, orig_len, final_len, kept_labels, dropped_labels


def _clip_section_text(text: str, budget: int) -> str:
    """Truncate section body to budget with a word boundary when possible."""
    text = (text or "").strip()
    if len(text) <= budget:
        return text
    cut = text[: budget]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip() + "…"


def _join_titled_blocks(blocks: list[tuple[str, str]]) -> str:
    if not blocks:
        return ""
    parts: list[str] = []
    for t, b in blocks:
        parts.append(f"[{t}]\n{b.strip()}")
    return "\n\n".join(parts)


def build_weighted_job_text_for_scoring(raw_description: str, max_chars: int) -> str:
    """Structure job text for weighted scoring: Required → Responsibilities → Preferred (+ other).

    No extra LLM calls. Uses the same section split / classification as job essentials.
    """
    raw = str(raw_description or "").strip()
    if not raw:
        return ""

    sections = _split_description_into_sections(raw)
    req_blocks: list[tuple[str, str]] = []
    pref_blocks: list[tuple[str, str]] = []
    resp_blocks: list[tuple[str, str]] = []
    other_blocks: list[tuple[str, str]] = []

    def collect_from_sections() -> None:
        for title, body in sections:
            if not (body or "").strip():
                continue
            bucket = _classify_section_title(title)
            if bucket == "drop":
                continue
            if bucket == "low":
                other_blocks.append((title, body))
                continue
            if bucket in ("req", "skills"):
                req_blocks.append((title, body))
            elif bucket == "pref":
                pref_blocks.append((title, body))
            elif bucket == "resp":
                resp_blocks.append((title, body))
            else:
                other_blocks.append((title, body))

    if len(sections) >= 2:
        collect_from_sections()
    else:
        # Unstructured: one block for inference (still use weighted prompt rules).
        body, _, _ = _essentials_from_paragraphs(raw, max_chars - 280)
        return (
            "NOTE: Section headings were not detected in this posting. "
            "Infer which parts are required vs preferred vs responsibilities.\n\n"
            f"## Job posting (unstructured)\n{body}"
        ).strip()

    req_t = _join_titled_blocks(req_blocks)
    resp_t = _join_titled_blocks(resp_blocks)
    pref_t = _join_titled_blocks(pref_blocks)
    other_t = _join_titled_blocks(other_blocks)

    if not req_t and not resp_t and not pref_t:
        merged = _join_titled_blocks(
            [(t, b) for t, b in sections if (b or "").strip() and _classify_section_title(t) != "drop"]
        )
        merged = _clip_section_text(merged, max_chars - 200)
        if not merged.strip():
            return ""
        return (
            "NOTE: Required / preferred / responsibilities were not clearly labeled. "
            "Infer them from the text below.\n\n"
            f"## Job posting\n{merged}"
        ).strip()

    # Character budgets: required and responsibilities matter most for fit.
    hdr_slack = 280
    usable = max(0, max_chars - hdr_slack)
    br = int(usable * 0.40)
    bx = int(usable * 0.34)
    bp = int(usable * 0.19)
    bo = max(0, usable - br - bx - bp)

    req_c = _clip_section_text(req_t, br)
    resp_c = _clip_section_text(resp_t, bx)
    pref_c = _clip_section_text(pref_t, bp)
    other_c = _clip_section_text(other_t, bo) if other_t else ""

    parts_out = [
        "## Required qualifications (highest weight)",
        "Judge fit primarily against this block (must-haves: skills, experience, education, certifications).",
        "",
        req_c if req_c.strip() else "(No separate required section — infer must-haves from the posting.)",
        "",
        "## Responsibilities (medium weight)",
        "How well does the candidate's experience match what they would do in the role?",
        "",
        resp_c if resp_c.strip() else "(No separate responsibilities section — infer from the posting.)",
        "",
        "## Preferred qualifications (low weight)",
        "Nice-to-have only. Gaps here must NOT heavily lower the score if required items are met.",
        "",
        pref_c if pref_c.strip() else "(None listed separately or none identified.)",
    ]
    if other_c.strip():
        parts_out.extend(
            [
                "",
                "## Additional context (lower weight)",
                other_c,
            ]
        )

    out = "\n".join(parts_out).strip()
    if len(out) > max_chars:
        out = _truncate_at_word_boundary(out, max_chars)
    return out


def truncate_text(text: str | None, max_chars: int) -> tuple[str, int, int]:
    """Truncate text for LLM input. Returns ``(text, original_len, result_len)``.

    If longer than ``max_chars``, cuts to ``max_chars`` and appends a one-line notice
    (the notice is included in ``result_len``).
    """
    if text is None:
        return "", 0, 0
    s = str(text)
    orig = len(s)
    if orig <= max_chars:
        return s, orig, orig
    cut = s[:max_chars].rstrip()
    suffix = "\n\n[Truncated for API context limits.]"
    out = cut + suffix
    return out, orig, len(out)


def _load_profile_for_scoring() -> dict:
    """Load ``profile.json`` if present; scoring still works with an empty dict."""
    try:
        from applypilot.config import load_profile

        return load_profile()
    except Exception as exc:
        log.warning(
            "Condensed scoring: could not load profile.json (%s). Using resume excerpt only.",
            exc,
        )
        return {}


_PROFILE_PLACEHOLDER_VALUES = (
    "your_legal_name",
    "your city, your state/province",
    "software engineer",
)


def _is_placeholder_profile_value(value: str) -> bool:
    s = (value or "").strip().lower()
    return bool(s) and s in _PROFILE_PLACEHOLDER_VALUES


def _clean_profile_text(value: object) -> str:
    s = str(value).strip() if value is not None else ""
    return "" if _is_placeholder_profile_value(s) else s


def profile_has_placeholders(profile: dict | None) -> bool:
    """True when known placeholder/default values are present."""
    p = profile or {}
    personal = p.get("personal") or {}
    exp = p.get("experience") or {}
    checks = [
        personal.get("full_name"),
        personal.get("city"),
        f"{personal.get('city', '')}, {personal.get('province_state', '')}".strip(", "),
        exp.get("target_role"),
        p.get("name"),
        p.get("location"),
        p.get("target_role"),
    ]
    return any(_is_placeholder_profile_value(str(v or "")) for v in checks if v is not None)


def _example_defaults_block() -> str:
    """Example fallback values shown only when no real profile is loaded."""
    return (
        "EXAMPLE DEFAULTS (not used for scoring)\n"
        "Name: YOUR_LEGAL_NAME\n"
        "Location: Your City, Your State/Province\n"
        "Target role: software engineer\n"
        "Update ./profile.json with your real background."
    )


def _token_or_phrase_in_resume(phrase: str, resume_lower: str) -> bool:
    """Return True if ``phrase`` appears in the resume (conservative matching).

    Avoids common substring traps (e.g. *Java* vs *JavaScript*) for plain
    alphabetic tokens; allows symbol-heavy skills (e.g. C++, .NET) as substring.
    """
    s = (phrase or "").strip()
    if not s or not resume_lower:
        return False
    sl = s.lower()
    if " " in sl:
        return re.sub(r"\s+", " ", sl) in resume_lower
    # Symbol / mixed tokens: require literal substring (resume is lowercased).
    if not re.match(r"^[a-z][a-z0-9]*$", sl):
        return sl in resume_lower
    # Plain word: boundary-style match
    return bool(
        re.search(rf"(?<![a-z0-9])({re.escape(sl)})(?![a-z0-9])", resume_lower)
    )


def _build_identity_block(profile: dict) -> list[str]:
    """Compact identity from profile only (no invented titles or skills)."""
    lines: list[str] = []
    personal = profile.get("personal") or {}
    exp = profile.get("experience") or {}

    # Support both nested profile schema and flat user profile keys.
    name = _clean_profile_text(personal.get("full_name") or profile.get("name"))
    if name:
        lines.append(f"Name: {name}")
    city = _clean_profile_text(personal.get("city"))
    st = _clean_profile_text(personal.get("province_state"))
    location_flat = _clean_profile_text(profile.get("location"))
    if city or st:
        lines.append(f"Location: {', '.join(x for x in (city, st) if x)}")
    elif location_flat:
        lines.append(f"Location: {location_flat}")

    tr = _clean_profile_text(exp.get("target_role") or profile.get("target_role"))
    if tr:
        lines.append(f"Target role: {tr}")
    cjt = _clean_profile_text(exp.get("current_job_title"))
    if cjt:
        lines.append(f"Recent title: {cjt}")
    cc = _clean_profile_text(exp.get("current_company"))
    if cc:
        lines.append(f"Recent employer: {cc}")
    yoe = exp.get("years_of_experience_total", profile.get("years_experience"))
    if yoe is not None and str(yoe).strip():
        lines.append(f"Years experience (profile): {yoe}")
    edu = _clean_profile_text(exp.get("education_level") or profile.get("education"))
    if edu:
        lines.append(f"Education: {edu}")
    summary = _clean_profile_text(profile.get("summary"))
    if summary:
        lines.append(f"Summary: {summary}")
    return lines


def _skills_boundary_matching_resume(profile: dict, resume_lower: str) -> str:
    """Include ``skills_boundary`` entries only when they appear in resume text."""
    if not resume_lower.strip():
        return ""
    sb = profile.get("skills_boundary") or {}
    sections: list[str] = []
    for key in ("languages", "frameworks", "devops", "databases", "tools"):
        items = sb.get(key)
        if not isinstance(items, list):
            continue
        ok = [
            _clean_profile_text(x)
            for x in items
            if _clean_profile_text(x) and _token_or_phrase_in_resume(_clean_profile_text(x), resume_lower)
        ]
        if ok:
            label = key.replace("_", " ").title()
            sections.append(f"{label}: {', '.join(ok[:20])}")
    return "\n".join(sections)


def _resume_facts_matching_resume(profile: dict, resume_lower: str) -> str:
    """Include resume_facts lines only when the text appears in the resume."""
    if not resume_lower.strip():
        return ""
    rf = profile.get("resume_facts") or {}
    lines_out: list[str] = []
    if isinstance(rf.get("preserved_companies"), list):
        ok = [
            _clean_profile_text(c)
            for c in rf["preserved_companies"]
            if _clean_profile_text(c) and _token_or_phrase_in_resume(_clean_profile_text(c), resume_lower)
        ]
        if ok:
            lines_out.append("Companies: " + ", ".join(ok[:12]))
    if isinstance(rf.get("preserved_projects"), list):
        ok = [
            _clean_profile_text(c)
            for c in rf["preserved_projects"]
            if _clean_profile_text(c) and _token_or_phrase_in_resume(_clean_profile_text(c), resume_lower)
        ]
        if ok:
            lines_out.append("Projects: " + ", ".join(ok[:10]))
    if isinstance(rf.get("real_metrics"), list):
        ok = [
            _clean_profile_text(c)
            for c in rf["real_metrics"]
            if _clean_profile_text(c) and _token_or_phrase_in_resume(_clean_profile_text(c), resume_lower)
        ]
        if ok:
            lines_out.append("Metrics: " + "; ".join(ok[:8]))
    school = _clean_profile_text(rf.get("preserved_school"))
    if school and _token_or_phrase_in_resume(school, resume_lower):
        lines_out.append(f"School: {school}")
    return "\n".join(lines_out)


def print_scoring_candidate_profile(candidate_profile: str) -> None:
    """Echo the exact profile string sent to the scoring LLM (for verification)."""
    console.print()
    console.print(
        Panel(
            candidate_profile,
            title="Candidate profile (used for scoring)",
            border_style="cyan",
            expand=False,
        )
    )
    console.print(
        f"[dim]Length: {len(candidate_profile)} / {SCORE_MAX_PROFILE_CHARS} chars[/dim]\n"
    )


def print_profile_placeholder_warning() -> None:
    """Warn that profile defaults/placeholders were detected."""
    console.print(
        "[yellow]Candidate profile contains defaults/placeholders. "
        "Update ./profile.json for better scoring.[/yellow]"
    )


_LOW_SIGNAL_LINE_MARKERS = (
    "references available upon request",
    "responsible for",
    "duties included",
    "hardworking",
    "team player",
    "excellent communication skills",
)


def _trim_low_signal_lines(lines: list[str], max_lines: int) -> list[str]:
    """Keep high-signal lines first (metrics/keywords/bullets), then fill remaining."""
    if not lines:
        return []
    hi: list[str] = []
    lo: list[str] = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        lower = s.lower()
        has_metric = bool(re.search(r"\d", s)) or "%" in s or "$" in s
        has_keyword = any(
            k in lower
            for k in (
                "integration", "automation", "api", "stakeholder", "solution",
                "demo", "architecture", "consult", "customer", "implementation",
            )
        )
        looks_bullet = bool(re.match(r"^[-•*▪·]\s+", s))
        low_signal = any(m in lower for m in _LOW_SIGNAL_LINE_MARKERS)
        if (has_metric or has_keyword or looks_bullet) and not low_signal:
            hi.append(s)
        else:
            lo.append(s)
    ranked = hi + lo
    return ranked[:max_lines]


def _resume_snippet_for_profile(resume_text: str, max_chars: int) -> str:
    """Build a structured resume block for scoring.

    Sections:
    - summary
    - core skills
    - key experience
    - technical skills
    """
    if not resume_text or not str(resume_text).strip():
        return ""
    text = str(resume_text).strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    lower = text.lower()

    def _section_lines(markers: tuple[str, ...], cap_lines: int = 12, span: int = 900) -> list[str]:
        best = -1
        for marker in markers:
            idx = lower.find(marker)
            if idx >= 0 and (best < 0 or idx < best):
                best = idx
        if best < 0:
            return []
        chunk = text[best : best + span]
        chunk_lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
        return _trim_low_signal_lines(chunk_lines, cap_lines)

    summary_lines = _section_lines(("summary", "profile", "about", "overview"), cap_lines=5, span=600)
    if not summary_lines:
        summary_lines = _trim_low_signal_lines([ln for ln in lines if len(ln) >= 80], 4)

    core_skill_lines = _section_lines(("core skills", "skills", "competencies", "strengths"), cap_lines=8, span=600)
    tech_skill_lines = _section_lines(("technical skills", "technologies", "tech stack", "tools"), cap_lines=10, span=700)
    exp_lines = _section_lines(
        ("professional experience", "work experience", "experience", "employment", "career"),
        cap_lines=18,
        span=1400,
    )
    if not exp_lines:
        exp_lines = _trim_low_signal_lines(
            [ln for ln in lines if re.match(r"^[-•*▪·]\s+", ln) or len(ln) >= 70],
            14,
        )

    parts: list[str] = []
    if summary_lines:
        parts.append("SUMMARY\n" + "\n".join(summary_lines))
    if core_skill_lines:
        parts.append("CORE SKILLS\n" + "\n".join(core_skill_lines))
    if exp_lines:
        parts.append("KEY EXPERIENCE\n" + "\n".join(exp_lines))
    if tech_skill_lines:
        parts.append("TECHNICAL SKILLS\n" + "\n".join(tech_skill_lines))
    if not parts:
        return text[:max_chars].rstrip()

    combined = "\n\n".join(parts)
    return combined[:max_chars].rstrip()


def build_condensed_candidate_profile(resume_text: str, profile: dict | None) -> tuple[str, int, int]:
    """Build a ≤3000 char profile: identity, structured resume, then verified profile lines.

    ``skills_boundary`` and ``resume_facts`` are included only when each entry
    appears in ``resume.txt`` (no inferred or free-floating skill lists).

    Returns ``(profile_text, original_resume_len, final_profile_len)``.
    """
    p = profile or {}
    rt = (resume_text or "").strip()
    resume_lower = rt.lower()

    identity_lines = _build_identity_block(p)
    identity_block = ""
    if identity_lines:
        identity_block = "IDENTITY\n" + "\n".join(identity_lines)

    skills_inner = _skills_boundary_matching_resume(p, resume_lower)
    skills_block = ""
    if skills_inner:
        skills_block = "PROFILE SKILLS (also in resume text)\n" + skills_inner

    highlights_inner = _resume_facts_matching_resume(p, resume_lower)
    highlights_block = ""
    if highlights_inner:
        highlights_block = "NOTABLE (from profile; text appears in resume)\n" + highlights_inner

    # Reserve space for fixed sections; give the rest to the resume excerpt.
    sep = 2
    overhead = sep * 3
    fixed_len = overhead
    for block in (identity_block, skills_block, highlights_block):
        if block:
            fixed_len += len(block)

    excerpt_budget = SCORE_MAX_PROFILE_CHARS - fixed_len - 64
    excerpt_budget = max(800, min(_RESUME_EXCERPT_BUDGET, excerpt_budget))
    snippet = _resume_snippet_for_profile(rt, excerpt_budget)
    resume_block = ""
    if snippet:
        resume_block = "RESUME (primary evidence)\n" + snippet

    parts: list[str] = []
    if identity_block:
        parts.append(identity_block)
    if resume_block:
        parts.append(resume_block)
    if skills_block:
        parts.append(skills_block)
    if highlights_block:
        parts.append(highlights_block)

    if not parts:
        combined = rt[:SCORE_MAX_PROFILE_CHARS] if rt else "[No resume text available.]"
    else:
        combined = "\n\n".join(parts)

    body, orig_len, out_len = truncate_text(combined, SCORE_MAX_PROFILE_CHARS)
    resume_in_len = len(resume_text or "")
    return body, resume_in_len, out_len


# ── Scoring Prompt ────────────────────────────────────────────────────────

SCORE_PROMPT = """You score how well the CANDIDATE PROFILE fits the JOB POSTING.

The posting is organized into weighted sections (when present):

1) **Required qualifications** — HIGHEST weight. These are must-haves (skills, years, education, licenses, core tools). If the candidate clearly satisfies **most** of the stated requirements, the score should be **at least 6–7** unless there is a **disqualifying** gap (e.g. a hard requirement they completely lack, such as a required license or mandatory technology they have zero experience with).

2) **Responsibilities** — MEDIUM weight. Compare the candidate's experience to what they would do day-to-day; this should move the score up or down in the mid range when combined with required fit.

3) **Preferred qualifications** — LOW weight. Treat as bonuses only. **Missing preferred / nice-to-have items must NOT pull the score below the mid range (5–6) by themselves** and must NOT dominate the score. Do not apply a large penalty solely for gaps in preferred items when required qualifications are largely met.

**Calibration (apply in order):**
- Strong match on required + reasonable alignment with responsibilities → typically **7–10**.
- Meets most required items with no disqualifying gap → **minimum 6–7** unless you explicitly justify a rare exception in REASONING.
- Weak required fit → scores can be **1–5**; cite the blocking gaps.
- Prefer citing **required** fit first in REASONING, then responsibilities, then preferred items only briefly if useful.

The candidate profile is intentionally short. Output exactly three lines:

SCORE: [integer 1-10 only]
KEYWORDS: [comma-separated ATS-relevant terms from the job that fit this candidate]
REASONING: [2-4 sentences: required fit first, then responsibilities, then preferred if relevant]"""


def _parse_score_response(response: str) -> dict:
    """Parse the LLM's score response into structured data.

    Args:
        response: Raw LLM response text (OpenAI ``message.content`` or Gemini text).

    Returns:
        {"score": int, "keywords": str, "reasoning": str}
    """
    if response is None or not str(response).strip():
        return {"score": 0, "keywords": "", "reasoning": "Empty LLM response"}

    score = 0
    keywords = ""
    reasoning = str(response)

    for line in response.split("\n"):
        line = line.strip()
        if line.startswith("SCORE:"):
            try:
                score = int(re.search(r"\d+", line).group())
                score = max(1, min(10, score))
            except (AttributeError, ValueError):
                score = 0
        elif line.startswith("KEYWORDS:"):
            keywords = line.replace("KEYWORDS:", "").strip()
        elif line.startswith("REASONING:"):
            reasoning = line.replace("REASONING:", "").strip()

    return {"score": score, "keywords": keywords, "reasoning": reasoning}


def score_job(
    candidate_profile: str,
    job: dict,
    *,
    verbose: bool = False,
) -> dict:
    """Score a single job against a **condensed** candidate profile (not full resume).

    Args:
        candidate_profile: Short profile text (identity, structured resume, verified lines), ≤ ~3000 chars.
        job: Job dict with keys: title, site, location, full_description.
        verbose: If True, log prompt/essentials diagnostics (see ``SCORE_VERBOSE``).

    Returns:
        {"score": int, "keywords": str, "reasoning": str}
    """
    eff_verbose = verbose or SCORE_VERBOSE
    raw_desc = job.get("full_description") or ""
    desc_orig = len(str(raw_desc))

    desc_body = build_weighted_job_text_for_scoring(raw_desc, SCORE_MAX_JOB_DESC_CHARS)
    if not (desc_body or "").strip():
        desc_body, _, desc_out, _kept_sections, _dropped_sections = (
            extract_job_essentials_for_scoring(
                raw_desc, SCORE_MAX_JOB_DESC_CHARS, verbose=eff_verbose
            )
        )
    else:
        desc_out = len(desc_body)
        _kept_sections = []
        _dropped_sections = []

    if eff_verbose:
        log.info(
            "Score prompt sizes: candidate_profile=%d chars; job_description %d -> %d chars (weighted sections) | %s",
            len(candidate_profile),
            desc_orig,
            desc_out,
            (job.get("title") or "?")[:60],
        )

    job_text = (
        f"TITLE: {job['title']}\n"
        f"COMPANY: {job['site']}\n"
        f"LOCATION: {job.get('location', 'N/A')}\n\n"
        f"JOB POSTING (weighted sections for scoring):\n{desc_body}"
    )

    messages = [
        {"role": "system", "content": SCORE_PROMPT},
        {
            "role": "user",
            "content": (
                f"CANDIDATE PROFILE:\n{candidate_profile}\n\n"
                f"---\n\nJOB POSTING:\n{job_text}"
            ),
        },
    ]

    try:
        client = get_client()
        response = client.chat(messages, max_tokens=512, temperature=0.2)
        return _parse_score_response(response)
    except Exception as e:
        log.error("LLM error scoring job '%s': %s", job.get("title", "?"), e)
        return {"score": 0, "keywords": "", "reasoning": f"LLM error: {e}"}


def run_scoring(
    limit: int = 0,
    rescore: bool = False,
    chunk_size: int = DEFAULT_SCORE_CHUNK_SIZE,
    chunk_delay: float = DEFAULT_SCORE_CHUNK_DELAY_SEC,
    *,
    verbose: bool = False,
) -> dict:
    """Score unscored jobs that have full descriptions.

    Jobs are processed in chunks (default size 25) with a pause between chunks
    to stay within API rate limits. Each job is written to the DB immediately
    after scoring. Failures are isolated per job.

    Args:
        limit: Maximum number of jobs to score in this run.
        rescore: If True, re-score all jobs (not just unscored ones).
        chunk_size: Jobs per chunk before a between-chunk pause (default 25).
        chunk_delay: Seconds to sleep after each chunk except the last (default 5).
        verbose: If True (or module ``SCORE_VERBOSE`` is True), emit full scoring logs.

    Returns:
        {"scored": int, "errors": int, "elapsed": float, "distribution": list}
    """
    eff_verbose = verbose or SCORE_VERBOSE
    resume_text, resume_source_used = ensure_clean_resume_text()
    profile = _load_profile_for_scoring()
    if not profile:
        console.print()
        console.print(
            Panel(
                _example_defaults_block(),
                title="Profile status",
                border_style="yellow",
                expand=False,
            )
        )
    elif profile_has_placeholders(profile):
        print_profile_placeholder_warning()
    candidate_profile, resume_chars, profile_chars = build_condensed_candidate_profile(
        resume_text, profile
    )
    print_scoring_candidate_profile(candidate_profile)
    if eff_verbose:
        log.info(
            "Condensed candidate profile for scoring: resume_input=%d chars -> profile=%d chars (max %d)",
            resume_chars,
            profile_chars,
            SCORE_MAX_PROFILE_CHARS,
        )
        log.info("Resume source used for scoring: %s", resume_source_used)

    conn = get_connection()

    if rescore:
        query = "SELECT * FROM jobs WHERE full_description IS NOT NULL"
        if limit > 0:
            query += f" LIMIT {limit}"
        jobs = conn.execute(query).fetchall()
    else:
        jobs = get_jobs_by_stage(conn=conn, stage="pending_score", limit=limit)

    if not jobs:
        if eff_verbose:
            log.info("No unscored jobs with descriptions found.")
        return {"scored": 0, "errors": 0, "elapsed": 0.0, "distribution": []}

    # Convert sqlite3.Row to dicts if needed
    if jobs and not isinstance(jobs[0], dict):
        columns = jobs[0].keys()
        jobs = [dict(zip(columns, row)) for row in jobs]

    # Safety pass: remove any existing jobs that require >25% travel.
    travel_filtered = 0
    kept_jobs: list[dict] = []
    for job in jobs:
        desc = job.get("full_description") or ""
        too_much_travel, travel_pct = is_excessive_travel_requirement(desc)
        if too_much_travel:
            conn.execute("DELETE FROM jobs WHERE url = ?", (job.get("url"),))
            travel_filtered += 1
            if eff_verbose:
                log.info(
                    "Travel filter: removed '%s' (%s%% travel > 25%%)",
                    (job.get("title") or "?")[:80],
                    travel_pct,
                )
            continue
        kept_jobs.append(job)
    if travel_filtered:
        conn.commit()
        console.print(
            f"[yellow]Travel filter: removed {travel_filtered} job(s) requiring >25% travel before scoring.[/yellow]"
        )
    jobs = kept_jobs

    cs = max(1, int(chunk_size))
    cd = max(0.0, float(chunk_delay))
    inter_job_delay = get_apply_pilot_llm_delay()
    if eff_verbose and inter_job_delay > 0:
        log.info(
            "LLM inter-request delay: %.1fs (APPLY_PILOT_LLM_DELAY; set 0 to disable)",
            inter_job_delay,
        )
    if eff_verbose and cd > 0:
        log.info("Between-chunk pause: %.1fs (--chunk-delay)", cd)

    total_jobs = len(jobs)
    num_chunks = max(1, math.ceil(total_jobs / cs))

    if eff_verbose:
        log.info(
            "Scoring %d jobs in %d chunk(s) of up to %d jobs each",
            total_jobs, num_chunks, cs,
        )
    t0 = time.time()
    completed = 0
    errors = 0
    results: list[dict] = []

    for chunk_idx, start in enumerate(range(0, total_jobs, cs), start=1):
        chunk = jobs[start : start + cs]
        n_in_chunk = len(chunk)
        if eff_verbose:
            console.print(
                f"[bold cyan]Scoring chunk {chunk_idx}/{num_chunks} ({n_in_chunk} jobs)[/bold cyan]"
            )
            log.info("Scoring chunk %d/%d (%d jobs)", chunk_idx, num_chunks, n_in_chunk)

        chunk_ok = 0
        chunk_fail = 0

        for j_idx, job in enumerate(chunk):
            result = score_job(candidate_profile, job, verbose=eff_verbose)
            result["url"] = job["url"]
            completed += 1

            if result["score"] == 0:
                errors += 1
                chunk_fail += 1
            else:
                chunk_ok += 1

            results.append(result)

            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ? WHERE url = ?",
                (
                    result["score"],
                    f"{result['keywords']}\n{result['reasoning']}",
                    now,
                    result["url"],
                ),
            )
            conn.commit()

            log.info(
                "[%d/%d] score=%d  %s",
                completed,
                total_jobs,
                result["score"],
                job.get("title", "?")[:60],
            )

            if j_idx < n_in_chunk - 1 and inter_job_delay > 0:
                time.sleep(inter_job_delay)

        if eff_verbose:
            console.print(
                f"[bold green]Chunk complete:[/bold green] {chunk_ok} succeeded, {chunk_fail} failed"
            )
            log.info(
                "Chunk complete: %d succeeded, %d failed",
                chunk_ok,
                chunk_fail,
            )

        if chunk_idx < num_chunks and cd > 0:
            time.sleep(cd)

    elapsed = time.time() - t0
    if eff_verbose:
        log.info(
            "Done: %d scored in %.1fs (%.1f jobs/sec)",
            len(results),
            elapsed,
            len(results) / elapsed if elapsed > 0 else 0,
        )

    # Score distribution
    dist = conn.execute("""
        SELECT fit_score, COUNT(*) FROM jobs
        WHERE fit_score IS NOT NULL
        GROUP BY fit_score ORDER BY fit_score DESC
    """).fetchall()
    distribution = [(row[0], row[1]) for row in dist]

    return {
        "scored": len(results),
        "errors": errors,
        "elapsed": elapsed,
        "distribution": distribution,
    }


# ---------------------------------------------------------------------------
# Single-job CLI (``applypilot run score-one``)
# ---------------------------------------------------------------------------

def find_job_for_score_one(
    conn: sqlite3.Connection,
    *,
    url_fragment: str | None = None,
    title_substring: str | None = None,
) -> dict:
    """Return one job row as a dict, or raise ``ValueError`` (none / ambiguous)."""
    has_url = bool(url_fragment and str(url_fragment).strip())
    has_title = bool(title_substring and str(title_substring).strip())
    if has_url == has_title:
        raise ValueError("Specify exactly one of url_fragment or title_substring.")
    min_desc = 50
    if has_url:
        needle = str(url_fragment).strip()
        rows = conn.execute(
            "SELECT * FROM jobs WHERE url LIKE ? "
            "AND full_description IS NOT NULL AND length(trim(full_description)) >= ?",
            (f"%{needle}%", min_desc),
        ).fetchall()
        hint = f"url containing {needle!r}"
    else:
        needle = str(title_substring).strip()
        rows = conn.execute(
            "SELECT * FROM jobs WHERE lower(title) LIKE lower(?) "
            "AND full_description IS NOT NULL AND length(trim(full_description)) >= ?",
            (f"%{needle}%", min_desc),
        ).fetchall()
        hint = f"title containing {needle!r}"

    if not rows:
        raise ValueError(
            f"No job found with a full description ({hint}). "
            "Enrich the job first, or check your spelling."
        )
    if len(rows) > 1:
        lines = [f"  • {r['title'][:100]}\n    {r['url']}" for r in rows[:15]]
        more = f"\n  … and {len(rows) - 15} more" if len(rows) > 15 else ""
        raise ValueError(
            f"Found {len(rows)} jobs ({hint}); narrow --url-fragment or --title.\n"
            + "\n".join(lines)
            + more
        )
    row = rows[0]
    return {k: row[k] for k in row.keys()}


def gap_hints_from_reasoning(reasoning: str) -> str | None:
    """Best-effort lines that often describe weak fit / gaps (from rationale text)."""
    if not reasoning or not str(reasoning).strip():
        return None
    sentences = re.split(r"(?<=[.!?])\s+", str(reasoning).strip())
    triggers = (
        "lack", "missing", "weak", "limited", "no direct", "not align",
        "however", "although", "gap", "without", "insufficient", "unclear",
        "less", "does not", "doesn't", "not a strong",
    )
    hits: list[str] = []
    for s in sentences:
        sl = s.lower()
        if any(t in sl for t in triggers) and len(s.strip()) > 15:
            hits.append(s.strip())
    if not hits:
        return None
    return "\n".join(f"• {h}" for h in hits[:8])


def run_score_one(
    *,
    url_fragment: str | None = None,
    title: str | None = None,
    write_db: bool = False,
    verbose: bool = False,
) -> dict:
    """Load profile + one DB job, run ``score_job``, optionally persist scores.

    Returns keys: ``job`` (dict), ``score``, ``keywords``, ``reasoning``.
    """
    init_db()
    conn = get_connection()
    job = find_job_for_score_one(
        conn, url_fragment=url_fragment, title_substring=title
    )
    too_much_travel, travel_pct = is_excessive_travel_requirement(job.get("full_description") or "")
    if too_much_travel:
        raise ValueError(
            f"Job filtered: requires {travel_pct}% travel (max allowed is 25%)."
        )
    resume_text, resume_source_used = ensure_clean_resume_text()
    profile = _load_profile_for_scoring()
    if not profile:
        console.print()
        console.print(
            Panel(
                _example_defaults_block(),
                title="Profile status",
                border_style="yellow",
                expand=False,
            )
        )
    elif profile_has_placeholders(profile):
        print_profile_placeholder_warning()
    candidate_profile, _, _ = build_condensed_candidate_profile(resume_text, profile)
    print_scoring_candidate_profile(candidate_profile)
    if verbose:
        log.info("Resume source used for score-one: %s", resume_source_used)
    result = score_job(candidate_profile, job, verbose=verbose)
    if write_db:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ? WHERE url = ?",
            (
                result["score"],
                f"{result.get('keywords', '')}\n{result.get('reasoning', '')}",
                now,
                job["url"],
            ),
        )
        conn.commit()
    return {"job": job, **result}
