"""
Supabase client configuration for ApplyPilot.
"""
import os
from typing import Optional
from supabase import create_client, Client

# Get credentials from environment
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

_client: Optional[Client] = None
_admin_client: Optional[Client] = None


def get_supabase() -> Client:
    """Get Supabase client with anon key (for frontend/user operations)."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment"
            )
        _client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _client


def get_supabase_admin() -> Client:
    """Get Supabase client with service role key (for admin operations)."""
    global _admin_client
    if _admin_client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment"
            )
        _admin_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _admin_client


def is_supabase_configured() -> bool:
    """Check if Supabase credentials are configured."""
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY)


# SQL schema for Supabase (run this in Supabase SQL Editor)
SUPABASE_SCHEMA = """
-- Jobs table
CREATE TABLE IF NOT EXISTS jobs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    job_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    description TEXT,
    job_type TEXT,
    salary_min INTEGER,
    salary_max INTEGER,
    url TEXT NOT NULL,
    site TEXT,
    search_term TEXT,
    date_posted TIMESTAMP WITH TIME ZONE,
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    score INTEGER,
    score_reason TEXT,
    status TEXT DEFAULT 'new',
    applied_at TIMESTAMP WITH TIME ZONE,
    cover_letter TEXT,
    tailored_resume_path TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Applications tracking table
CREATE TABLE IF NOT EXISTS applications (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'applied',
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    response_at TIMESTAMP WITH TIME ZONE,
    response_type TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Email monitoring table
CREATE TABLE IF NOT EXISTS email_events (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    email_id TEXT UNIQUE NOT NULL,
    subject TEXT,
    sender TEXT,
    received_at TIMESTAMP WITH TIME ZONE,
    classification TEXT,
    snippet TEXT,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Activity log table
CREATE TABLE IF NOT EXISTS activity_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    action TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User settings table
CREATE TABLE IF NOT EXISTS settings (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID,
    min_score_threshold INTEGER DEFAULT 7,
    auto_apply_enabled BOOLEAN DEFAULT FALSE,
    email_monitoring_enabled BOOLEAN DEFAULT FALSE,
    llm_delay REAL DEFAULT 4.5,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User profile table
CREATE TABLE IF NOT EXISTS profiles (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID UNIQUE,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    city TEXT,
    country TEXT,
    linkedin_url TEXT,
    github_url TEXT,
    portfolio_url TEXT,
    resume_text TEXT,
    work_authorization JSONB,
    experience JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score);
CREATE INDEX IF NOT EXISTS idx_jobs_discovered_at ON jobs(discovered_at);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_email_events_job_id ON email_events(job_id);
CREATE INDEX IF NOT EXISTS idx_activity_log_created_at ON activity_log(created_at);

-- Row Level Security (enable for production)
-- ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE settings ENABLE ROW LEVEL SECURITY;
"""
