"""Job fit scoring: LLM-powered evaluation of candidate-job match quality.

Scores jobs on a 1-10 scale by comparing a **condensed candidate profile**
(skills, alignment, resume excerpt from ``profile.json`` + ``resume.txt``)
to each job description. Keeps prompts short for better model behavior.
"""

import logging
import math
import re
import time
from datetime import datetime, timezone

from rich.console import Console

from applypilot.config import RESUME_PATH, get_apply_pilot_llm_delay
from applypilot.database import get_connection, get_jobs_by_stage
from applypilot.llm import get_client

log = logging.getLogger(__name__)
console = Console()

# Defaults for `applypilot run score` (overridden by CLI / pipeline)
DEFAULT_SCORE_CHUNK_SIZE = 25
DEFAULT_SCORE_CHUNK_DELAY_SEC = 5.0

# Job posting body; candidate side uses a condensed profile (not full resume).
SCORE_MAX_JOB_DESC_CHARS = 4000
# Condensed candidate profile: skills + alignment + resume snippet (1–2k chars).
SCORE_MAX_PROFILE_CHARS = 2000
# Portion of resume used when building the excerpt before global cap.
_RESUME_EXCERPT_BUDGET = 1200

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
    if any(m in t for m in _REQ_MARKERS):
        return "req"
    if any(m in t for m in _PREF_MARKERS):
        return "pref"
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


def _resume_snippet_for_profile(resume_text: str, max_chars: int) -> str:
    """Pull a short, informative slice of the resume (bullets / experience block)."""
    if not resume_text or not str(resume_text).strip():
        return ""
    text = str(resume_text).strip()
    lower = text.lower()
    best = -1
    for marker in (
        "professional experience",
        "work experience",
        "experience",
        "employment",
        "work history",
        "career",
    ):
        idx = lower.find(marker)
        if idx >= 0 and (best < 0 or idx < best):
            best = idx
    if best >= 0:
        chunk = text[best : best + max_chars]
        if len(chunk) >= 200:
            return chunk[:max_chars].rstrip()

    lines = text.splitlines()
    bullets: list[str] = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if re.match(r"^[-•*▪·]\s+", s) or re.match(r"^\d+[\).]\s+", s):
            bullets.append(s)
        elif len(s) > 60:
            bullets.append(s)
    if bullets:
        out = "\n".join(bullets[:40])
        return out[:max_chars].rstrip()
    return text[:max_chars].rstrip()


def build_condensed_candidate_profile(resume_text: str, profile: dict | None) -> tuple[str, int, int]:
    """Build a 1–2k char profile: skills, alignment, highlights, resume excerpt.

    Returns ``(profile_text, original_resume_len, final_profile_len)``.
    """
    p = profile or {}
    parts: list[str] = []

    sb = p.get("skills_boundary") or {}
    skill_bits: list[str] = []
    for key in ("languages", "frameworks", "devops", "databases", "tools"):
        items = sb.get(key)
        if isinstance(items, list) and items:
            skill_bits.append(f"{key.replace('_', ' ').title()}: {', '.join(str(x) for x in items[:20])}")
    if skill_bits:
        parts.append("KEY SKILLS\n" + "\n".join(skill_bits))

    exp = p.get("experience") or {}
    align: list[str] = []
    if exp.get("target_role"):
        align.append(f"Target role: {exp['target_role']}")
    if exp.get("years_of_experience_total"):
        align.append(f"Approx. experience: {exp['years_of_experience_total']} years")
    if exp.get("education_level"):
        align.append(f"Education: {exp['education_level']}")
    if exp.get("current_job_title"):
        align.append(f"Current/recent title: {exp['current_job_title']}")
    if exp.get("current_company"):
        align.append(f"Current/recent company: {exp['current_company']}")
    if align:
        parts.append("ROLE ALIGNMENT\n" + "\n".join(align))

    rf = p.get("resume_facts") or {}
    highlights: list[str] = []
    if isinstance(rf.get("preserved_companies"), list) and rf["preserved_companies"]:
        highlights.append("Companies: " + ", ".join(str(x) for x in rf["preserved_companies"][:10]))
    if isinstance(rf.get("preserved_projects"), list) and rf["preserved_projects"]:
        highlights.append("Projects: " + ", ".join(str(x) for x in rf["preserved_projects"][:8]))
    if isinstance(rf.get("real_metrics"), list) and rf["real_metrics"]:
        highlights.append("Metrics: " + "; ".join(str(x) for x in rf["real_metrics"][:6]))
    if rf.get("preserved_school"):
        highlights.append(f"School: {rf['preserved_school']}")
    if highlights:
        parts.append("HIGHLIGHTS\n" + "\n".join(highlights))

    snippet = _resume_snippet_for_profile(resume_text, _RESUME_EXCERPT_BUDGET)
    if snippet:
        parts.append("RELEVANT EXPERIENCE (resume excerpt)\n" + snippet)

    combined = "\n\n".join(parts) if parts else (resume_text or "").strip()
    if not combined:
        combined = "[No resume text available.]"

    body, orig_len, out_len = truncate_text(combined, SCORE_MAX_PROFILE_CHARS)
    resume_in_len = len(resume_text or "")
    return body, resume_in_len, out_len


# ── Scoring Prompt ────────────────────────────────────────────────────────

SCORE_PROMPT = """You score how well the CANDIDATE PROFILE fits the JOB POSTING.

Focus on three things:
1) Skills match — overlap between the candidate's skills and skills/tools in the job.
2) Experience relevance — past work and projects vs. responsibilities in the posting.
3) Role alignment — seniority, domain, and title fit (not exact title match required).

The profile is intentionally short. If there is clear overlap, score in the 7–10 range. Use lower scores only when overlap is weak or missing. Output exactly three lines:

SCORE: [integer 1-10 only]
KEYWORDS: [comma-separated ATS-relevant terms from the job that fit this candidate]
REASONING: [2-3 sentences citing skills, experience, and role fit]"""


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
        candidate_profile: Short profile text (skills, alignment, resume excerpt), ≤ ~2k chars.
        job: Job dict with keys: title, site, location, full_description.
        verbose: If True, log prompt/essentials diagnostics (see ``SCORE_VERBOSE``).

    Returns:
        {"score": int, "keywords": str, "reasoning": str}
    """
    eff_verbose = verbose or SCORE_VERBOSE
    raw_desc = job.get("full_description") or ""
    desc_body, desc_orig, desc_out, _kept_sections, _dropped_sections = (
        extract_job_essentials_for_scoring(
            raw_desc, SCORE_MAX_JOB_DESC_CHARS, verbose=eff_verbose
        )
    )

    if eff_verbose:
        log.info(
            "Score prompt sizes: candidate_profile=%d chars; job_description %d -> %d chars (essentials) | %s",
            len(candidate_profile),
            desc_orig,
            desc_out,
            (job.get("title") or "?")[:60],
        )

    job_text = (
        f"TITLE: {job['title']}\n"
        f"COMPANY: {job['site']}\n"
        f"LOCATION: {job.get('location', 'N/A')}\n\n"
        f"DESCRIPTION:\n{desc_body}"
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
    resume_text = RESUME_PATH.read_text(encoding="utf-8")
    profile = _load_profile_for_scoring()
    candidate_profile, resume_chars, profile_chars = build_condensed_candidate_profile(
        resume_text, profile
    )
    if eff_verbose:
        log.info(
            "Condensed candidate profile for scoring: resume_input=%d chars -> profile=%d chars (max %d)",
            resume_chars,
            profile_chars,
            SCORE_MAX_PROFILE_CHARS,
        )

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
