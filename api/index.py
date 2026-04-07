"""Vercel serverless API for ApplyPilot - uses Supabase for data."""

import os
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mangum import Mangum
from supabase import create_client

# Initialize Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="ApplyPilot API", version="0.3.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StatsResponse(BaseModel):
    total_discovered: int = 0
    total_enriched: int = 0
    total_scored: int = 0
    high_fit: int = 0
    mid_fit: int = 0
    low_fit: int = 0
    applied: int = 0
    failed: int = 0
    pending_input: int = 0
    interviews: int = 0
    offers: int = 0
    rejected: int = 0


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    if not supabase:
        return StatsResponse()
    
    result = supabase.table("jobs").select("apply_status, fit_score").execute()
    jobs = result.data or []
    
    scored = [j for j in jobs if j.get("fit_score") is not None]
    
    return StatsResponse(
        total_discovered=len(jobs),
        total_enriched=len([j for j in jobs if j.get("apply_status") != "discovered"]),
        total_scored=len(scored),
        high_fit=len([j for j in scored if (j.get("fit_score") or 0) >= 7]),
        mid_fit=len([j for j in scored if 5 <= (j.get("fit_score") or 0) < 7]),
        low_fit=len([j for j in scored if (j.get("fit_score") or 0) < 5]),
        applied=len([j for j in jobs if j.get("apply_status") == "applied"]),
        failed=len([j for j in jobs if j.get("apply_status") == "failed"]),
        pending_input=len([j for j in jobs if j.get("apply_status") == "needs_input"]),
        interviews=len([j for j in jobs if j.get("apply_status") == "interview"]),
        offers=len([j for j in jobs if j.get("apply_status") == "offer"]),
        rejected=len([j for j in jobs if j.get("apply_status") == "rejected"]),
    )


@app.get("/api/jobs")
async def get_jobs(
    status: Optional[str] = None,
    min_score: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
):
    if not supabase:
        return {"jobs": [], "total": 0}
    
    query = supabase.table("jobs").select("*", count="exact")
    
    if status:
        query = query.eq("apply_status", status)
    if min_score:
        query = query.gte("fit_score", min_score)
    
    query = query.order("discovered_at", desc=True).range(offset, offset + limit - 1)
    result = query.execute()
    
    return {"jobs": result.data or [], "total": result.count or 0}


@app.get("/api/jobs/{job_url:path}")
async def get_job(job_url: str):
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    
    result = supabase.table("jobs").select("*").eq("url", job_url).single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return result.data


@app.patch("/api/jobs/{job_url:path}/status")
async def update_job_status(job_url: str, status: str):
    if not supabase:
        raise HTTPException(status_code=503, detail="Database not configured")
    
    result = supabase.table("jobs").update({"apply_status": status}).eq("url", job_url).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {"success": True}


@app.get("/api/jobs/needs-input")
async def get_jobs_needing_input():
    if not supabase:
        return {"jobs": []}
    
    result = supabase.table("jobs").select("*").eq("apply_status", "needs_input").order("discovered_at", desc=True).execute()
    
    jobs = []
    for j in result.data or []:
        j["reason"] = j.get("apply_error") or "Missing information required"
        jobs.append(j)
    
    return {"jobs": jobs}


@app.get("/api/profile")
async def get_profile():
    if not supabase:
        return {"profile": None, "exists": False}
    
    try:
        result = supabase.table("profiles").select("*").limit(1).single().execute()
        return {"profile": result.data, "exists": bool(result.data)}
    except:
        return {"profile": None, "exists": False}


@app.get("/api/settings")
async def get_settings():
    if not supabase:
        return {
            "min_score_threshold": 6,
            "auto_apply_enabled": False,
            "email_monitoring_enabled": True,
            "llm_delay": 4.5
        }
    
    try:
        result = supabase.table("settings").select("*").limit(1).single().execute()
        return result.data or {
            "min_score_threshold": 6,
            "auto_apply_enabled": False,
            "email_monitoring_enabled": True,
            "llm_delay": 4.5
        }
    except:
        return {
            "min_score_threshold": 6,
            "auto_apply_enabled": False,
            "email_monitoring_enabled": True,
            "llm_delay": 4.5
        }


@app.get("/api/activity")
async def get_activity(limit: int = 50):
    if not supabase:
        return {"activities": []}
    
    try:
        result = supabase.table("activity").select("*").order("created_at", desc=True).limit(limit).execute()
        return {"activities": result.data or []}
    except:
        return {"activities": []}


# Pipeline operations - not available on Vercel (require local backend)
@app.post("/api/pipeline/discover")
async def run_discover():
    return {"message": "Discovery requires local backend", "status": "unavailable"}


@app.post("/api/pipeline/score")
async def run_score():
    return {"message": "Scoring requires local backend", "status": "unavailable"}


@app.post("/api/pipeline/apply")
async def run_apply():
    return {"message": "Auto-apply requires local backend with Chrome", "status": "unavailable"}


@app.post("/api/pipeline/apply/{job_url:path}")
async def apply_to_job(job_url: str):
    return {"message": "Auto-apply requires local backend with Chrome", "status": "unavailable"}


# Vercel serverless handler
handler = Mangum(app, lifespan="off")

