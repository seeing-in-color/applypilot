"""FastAPI backend for ApplyPilot web dashboard."""

from __future__ import annotations

import json
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from applypilot.config import APP_DIR, PROFILE_PATH, RESUME_PATH, load_env
from applypilot.database import get_connection, init_db


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class JobResponse(BaseModel):
    url: str
    title: Optional[str]
    company: Optional[str]
    location: Optional[str]
    salary: Optional[str]
    site: Optional[str]
    fit_score: Optional[int]
    score_reasoning: Optional[str]
    apply_status: Optional[str]
    discovered_at: Optional[str]
    applied_at: Optional[str]
    full_description: Optional[str]
    application_url: Optional[str]
    tailored_resume_path: Optional[str]
    cover_letter_path: Optional[str]


class StatsResponse(BaseModel):
    total_discovered: int
    total_enriched: int
    total_scored: int
    high_fit: int  # 7+
    mid_fit: int   # 5-6
    low_fit: int   # 1-4
    applied: int
    failed: int
    pending_input: int
    interviews: int
    offers: int
    rejected: int


class ProfileUpdate(BaseModel):
    personal: Optional[dict] = None
    work_authorization: Optional[dict] = None
    experience: Optional[dict] = None
    education: Optional[dict] = None
    skills: Optional[list] = None
    preferences: Optional[dict] = None


class SettingsUpdate(BaseModel):
    min_score_threshold: Optional[int] = 7
    auto_apply_enabled: Optional[bool] = False
    email_monitoring_enabled: Optional[bool] = False
    llm_delay: Optional[float] = 4.5


class JobStatusUpdate(BaseModel):
    status: str  # discovered, scored, qualified, applied, failed, rejected, interview, offer, needs_input


class SearchConfig(BaseModel):
    titles: list[str]
    locations: list[str]
    remote_only: bool = False
    salary_min: Optional[int] = None


# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and load environment on startup."""
    load_env()
    init_db()
    yield


app = FastAPI(
    title="ApplyPilot",
    description="AI-powered job application pipeline",
    version="0.3.0",
    lifespan=lifespan,
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# API Routes - Dashboard Stats
# ---------------------------------------------------------------------------

@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    """Get dashboard statistics."""
    conn = get_connection()
    
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    enriched = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL"
    ).fetchone()[0]
    scored = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL"
    ).fetchone()[0]
    high_fit = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score >= 7"
    ).fetchone()[0]
    mid_fit = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score BETWEEN 5 AND 6"
    ).fetchone()[0]
    low_fit = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL AND fit_score < 5"
    ).fetchone()[0]
    applied = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE applied_at IS NOT NULL"
    ).fetchone()[0]
    failed = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_status = 'failed'"
    ).fetchone()[0]
    pending = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_status = 'needs_input'"
    ).fetchone()[0]
    interviews = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_status = 'interview'"
    ).fetchone()[0]
    offers = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_status = 'offer'"
    ).fetchone()[0]
    rejected = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_status = 'rejected'"
    ).fetchone()[0]
    
    return StatsResponse(
        total_discovered=total,
        total_enriched=enriched,
        total_scored=scored,
        high_fit=high_fit,
        mid_fit=mid_fit,
        low_fit=low_fit,
        applied=applied,
        failed=failed,
        pending_input=pending,
        interviews=interviews,
        offers=offers,
        rejected=rejected,
    )


# ---------------------------------------------------------------------------
# API Routes - Jobs
# ---------------------------------------------------------------------------

@app.get("/api/jobs")
async def get_jobs(
    status: Optional[str] = None,
    min_score: Optional[int] = None,
    max_score: Optional[int] = None,
    site: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """Get jobs with optional filtering."""
    conn = get_connection()
    
    query = "SELECT * FROM jobs WHERE 1=1"
    params: list = []
    
    if status:
        if status == "qualified":
            query += " AND fit_score >= 7"
        elif status == "needs_input":
            query += " AND apply_status = 'needs_input'"
        elif status == "applied":
            query += " AND applied_at IS NOT NULL"
        elif status == "interview":
            query += " AND apply_status = 'interview'"
        elif status == "rejected":
            query += " AND apply_status = 'rejected'"
        else:
            query += " AND apply_status = ?"
            params.append(status)
    
    if min_score is not None:
        query += " AND fit_score >= ?"
        params.append(min_score)
    
    if max_score is not None:
        query += " AND fit_score <= ?"
        params.append(max_score)
    
    if site:
        query += " AND site = ?"
        params.append(site)
    
    if search:
        query += " AND (title LIKE ? OR description LIKE ? OR location LIKE ?)"
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])
    
    query += " ORDER BY discovered_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    rows = conn.execute(query, params).fetchall()
    
    jobs = []
    for row in rows:
        job = dict(row)
        # Extract company from site or title if available
        job["company"] = _extract_company(job)
        jobs.append(job)
    
    return {"jobs": jobs, "total": len(jobs)}


def _extract_company(job: dict) -> str:
    """Extract company name from job data."""
    # Try to get from URL or site
    url = job.get("url", "")
    site = job.get("site", "")
    
    if "greenhouse" in url.lower():
        # Extract from URL like job-boards.greenhouse.io/companyname/...
        parts = url.split("/")
        for i, p in enumerate(parts):
            if "greenhouse" in p and i + 1 < len(parts):
                return parts[i + 1].replace("-", " ").title()
    
    if "ashbyhq" in url.lower():
        parts = url.split("/")
        for i, p in enumerate(parts):
            if "ashbyhq" in p and i + 1 < len(parts):
                return parts[i + 1].replace("-", " ").title()
    
    if "workday" in url.lower():
        # myworkdayjobs.com URLs often have company name at start
        if "wd" in url and "myworkdayjobs" in url:
            parts = url.split(".")
            if parts:
                return parts[0].replace("https://", "").replace("http://", "").title()
    
    return site or "Unknown"


@app.get("/api/jobs/{job_url:path}")
async def get_job(job_url: str):
    """Get a single job by URL."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (job_url,)).fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = dict(row)
    job["company"] = _extract_company(job)
    return job


@app.patch("/api/jobs/{job_url:path}/status")
async def update_job_status(job_url: str, update: JobStatusUpdate):
    """Update job application status."""
    conn = get_connection()
    
    valid_statuses = ["discovered", "scored", "qualified", "applied", "failed", "rejected", "interview", "offer", "needs_input"]
    if update.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
    
    conn.execute(
        "UPDATE jobs SET apply_status = ? WHERE url = ?",
        (update.status, job_url)
    )
    conn.commit()
    
    return {"message": "Status updated", "status": update.status}


@app.get("/api/jobs/needs-input")
async def get_jobs_needing_input():
    """Get jobs that need manual intervention."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM jobs 
        WHERE apply_status = 'needs_input' 
           OR (apply_error IS NOT NULL AND apply_status != 'applied')
        ORDER BY last_attempted_at DESC
    """).fetchall()
    
    jobs = []
    for row in rows:
        job = dict(row)
        job["company"] = _extract_company(job)
        job["reason"] = _determine_input_reason(job)
        jobs.append(job)
    
    return {"jobs": jobs}


def _determine_input_reason(job: dict) -> str:
    """Determine why a job needs manual input."""
    error = job.get("apply_error", "") or ""
    
    if "captcha" in error.lower():
        return "CAPTCHA blocked automation"
    if "login" in error.lower() or "sign in" in error.lower():
        return "Login required"
    if "cover letter" in error.lower():
        return "Cover letter required"
    if "custom" in error.lower() or "unknown field" in error.lower():
        return "Unknown custom field"
    if "work authorization" in error.lower():
        return "Work authorization question"
    if "timeout" in error.lower():
        return "Page timeout"
    
    return "Manual review needed"


# ---------------------------------------------------------------------------
# API Routes - Profile
# ---------------------------------------------------------------------------

@app.get("/api/profile")
async def get_profile():
    """Get user profile."""
    if not PROFILE_PATH.exists():
        return {"profile": None, "exists": False}
    
    try:
        profile = json.loads(PROFILE_PATH.read_text())
        return {"profile": profile, "exists": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading profile: {e}")


@app.put("/api/profile")
async def update_profile(update: ProfileUpdate):
    """Update user profile."""
    if PROFILE_PATH.exists():
        profile = json.loads(PROFILE_PATH.read_text())
    else:
        profile = {}
    
    # Update only provided fields
    if update.personal is not None:
        profile["personal"] = {**profile.get("personal", {}), **update.personal}
    if update.work_authorization is not None:
        profile["work_authorization"] = {**profile.get("work_authorization", {}), **update.work_authorization}
    if update.experience is not None:
        profile["experience"] = {**profile.get("experience", {}), **update.experience}
    if update.education is not None:
        profile["education"] = {**profile.get("education", {}), **update.education}
    if update.skills is not None:
        profile["skills"] = update.skills
    if update.preferences is not None:
        profile["preferences"] = {**profile.get("preferences", {}), **update.preferences}
    
    PROFILE_PATH.write_text(json.dumps(profile, indent=2))
    return {"message": "Profile updated", "profile": profile}


@app.post("/api/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    """Upload resume file."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    suffix = Path(file.filename).suffix.lower()
    if suffix not in [".pdf", ".txt", ".docx"]:
        raise HTTPException(status_code=400, detail="File must be PDF, TXT, or DOCX")
    
    contents = await file.read()
    
    # Save to appropriate location
    if suffix == ".pdf":
        dest = APP_DIR / "resume.pdf"
    elif suffix == ".txt":
        dest = RESUME_PATH
    else:
        dest = APP_DIR / f"resume{suffix}"
    
    dest.write_bytes(contents)
    
    return {"message": "Resume uploaded", "path": str(dest)}


# ---------------------------------------------------------------------------
# API Routes - Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
async def get_settings():
    """Get application settings."""
    settings_path = APP_DIR / "settings.json"
    
    defaults = {
        "min_score_threshold": 7,
        "auto_apply_enabled": False,
        "email_monitoring_enabled": False,
        "llm_delay": 4.5,
    }
    
    if settings_path.exists():
        try:
            saved = json.loads(settings_path.read_text())
            return {**defaults, **saved}
        except Exception:
            pass
    
    return defaults


@app.put("/api/settings")
async def update_settings(update: SettingsUpdate):
    """Update application settings."""
    settings_path = APP_DIR / "settings.json"
    
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except Exception:
            pass
    
    # Update provided fields
    for field, value in update.model_dump(exclude_none=True).items():
        settings[field] = value
    
    settings_path.write_text(json.dumps(settings, indent=2))
    return {"message": "Settings updated", "settings": settings}


# ---------------------------------------------------------------------------
# API Routes - Pipeline Actions
# ---------------------------------------------------------------------------

@app.post("/api/pipeline/discover")
async def run_discover(background_tasks: BackgroundTasks):
    """Start job discovery in background."""
    from applypilot.pipeline import run_pipeline
    
    def run_in_thread():
        load_env()
        init_db()
        run_pipeline(stages=["discover"], workers=2)
    
    background_tasks.add_task(run_in_thread)
    return {"message": "Discovery started", "status": "running"}


@app.post("/api/pipeline/score")
async def run_score(background_tasks: BackgroundTasks, min_score: int = 7):
    """Start scoring in background."""
    from applypilot.pipeline import run_pipeline
    
    def run_in_thread():
        load_env()
        init_db()
        run_pipeline(stages=["score"], min_score=min_score)
    
    background_tasks.add_task(run_in_thread)
    return {"message": "Scoring started", "status": "running"}


@app.post("/api/pipeline/apply")
async def run_apply(
    background_tasks: BackgroundTasks,
    job_url: Optional[str] = None,
    min_score: int = 7,
    dry_run: bool = False,
):
    """Start auto-apply in background."""
    from applypilot.apply.launcher import main as apply_main
    
    def run_in_thread():
        load_env()
        init_db()
        apply_main(
            limit=1 if job_url else 10,
            target_url=job_url,
            min_score=min_score,
            dry_run=dry_run,
            headless=True,
        )
    
    background_tasks.add_task(run_in_thread)
    return {"message": "Auto-apply started", "status": "running"}


@app.post("/api/pipeline/apply/{job_url:path}")
async def apply_to_job(job_url: str, background_tasks: BackgroundTasks, dry_run: bool = False):
    """Apply to a specific job."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (job_url,)).fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    
    from applypilot.apply.launcher import main as apply_main
    
    def run_in_thread():
        load_env()
        init_db()
        apply_main(
            limit=1,
            target_url=job_url,
            min_score=0,  # Allow any score for manual apply
            dry_run=dry_run,
            headless=False,  # Show browser for manual jobs
        )
    
    background_tasks.add_task(run_in_thread)
    return {"message": f"Applying to {job_url}", "status": "running"}


# ---------------------------------------------------------------------------
# API Routes - Search Config
# ---------------------------------------------------------------------------

@app.get("/api/searches")
async def get_searches():
    """Get search configuration."""
    search_path = APP_DIR / "searches.yaml"
    
    if not search_path.exists():
        return {"searches": []}
    
    import yaml
    try:
        data = yaml.safe_load(search_path.read_text()) or {}
        return {"searches": data.get("searches", [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading searches: {e}")


@app.put("/api/searches")
async def update_searches(searches: list[SearchConfig]):
    """Update search configuration."""
    import yaml
    search_path = APP_DIR / "searches.yaml"
    
    data = {"searches": [s.model_dump() for s in searches]}
    search_path.write_text(yaml.dump(data, default_flow_style=False))
    
    return {"message": "Searches updated"}


# ---------------------------------------------------------------------------
# API Routes - Email Monitoring
# ---------------------------------------------------------------------------

@app.get("/api/email/status")
async def get_email_status():
    """Check Gmail authentication status."""
    try:
        from applypilot.webapp.email_monitor import is_gmail_authenticated, get_auth_url
        
        authenticated = is_gmail_authenticated()
        auth_url = "" if authenticated else get_auth_url()
        
        return {
            "authenticated": authenticated,
            "auth_url": auth_url,
        }
    except ImportError:
        return {
            "authenticated": False,
            "error": "Gmail dependencies not installed. Run: pip install google-api-python-client google-auth-oauthlib",
        }


@app.post("/api/email/sync")
async def sync_emails(background_tasks: BackgroundTasks, days_back: int = 7):
    """Sync emails and update job statuses."""
    from applypilot.webapp.email_monitor import sync_emails as do_sync
    
    def run_sync():
        return do_sync(days_back=days_back)
    
    background_tasks.add_task(run_sync)
    return {"message": "Email sync started", "status": "running"}


@app.post("/api/email/auth")
async def authenticate_email():
    """Start Gmail OAuth flow."""
    try:
        from applypilot.webapp.email_monitor import get_gmail_service
        
        # This will trigger the OAuth flow
        service = get_gmail_service()
        if service:
            return {"message": "Gmail authenticated successfully"}
        else:
            return {"error": "Authentication failed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# API Routes - Activity Log
# ---------------------------------------------------------------------------

@app.get("/api/activity")
async def get_activity(limit: int = 50):
    """Get recent activity log."""
    conn = get_connection()
    
    # Get recent job status changes
    activities = []
    
    # Recently discovered
    discovered = conn.execute("""
        SELECT url, title, site, discovered_at as timestamp, 'discovered' as action
        FROM jobs
        WHERE discovered_at IS NOT NULL
        ORDER BY discovered_at DESC
        LIMIT 10
    """).fetchall()
    
    for row in discovered:
        activities.append({
            "type": "discovered",
            "job_url": row["url"],
            "job_title": row["title"],
            "site": row["site"],
            "timestamp": row["timestamp"],
            "message": f"Discovered: {row['title'] or 'Untitled'} at {row['site'] or 'Unknown'}"
        })
    
    # Recently scored
    scored = conn.execute("""
        SELECT url, title, fit_score, scored_at as timestamp
        FROM jobs
        WHERE scored_at IS NOT NULL
        ORDER BY scored_at DESC
        LIMIT 10
    """).fetchall()
    
    for row in scored:
        activities.append({
            "type": "scored",
            "job_url": row["url"],
            "job_title": row["title"],
            "score": row["fit_score"],
            "timestamp": row["timestamp"],
            "message": f"Scored: {row['title'] or 'Untitled'} - {row['fit_score']}/10"
        })
    
    # Recently applied
    applied = conn.execute("""
        SELECT url, title, applied_at as timestamp, apply_status
        FROM jobs
        WHERE applied_at IS NOT NULL
        ORDER BY applied_at DESC
        LIMIT 10
    """).fetchall()
    
    for row in applied:
        activities.append({
            "type": "applied",
            "job_url": row["url"],
            "job_title": row["title"],
            "status": row["apply_status"],
            "timestamp": row["timestamp"],
            "message": f"Applied: {row['title'] or 'Untitled'}"
        })
    
    # Sort all activities by timestamp
    activities.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    
    return {"activities": activities[:limit]}


# ---------------------------------------------------------------------------
# Run the server
# ---------------------------------------------------------------------------

def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the FastAPI server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
