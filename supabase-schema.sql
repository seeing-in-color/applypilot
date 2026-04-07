-- ApplyPilot Supabase Schema
-- Run this in Supabase Dashboard → SQL Editor

-- Jobs table (main table used by the app)
CREATE TABLE IF NOT EXISTS jobs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    title TEXT,
    company TEXT,
    location TEXT,
    salary TEXT,
    site TEXT,
    strategy TEXT,
    description TEXT,
    full_description TEXT,
    application_url TEXT,
    fit_score INTEGER,
    score_reasoning TEXT,
    apply_status TEXT DEFAULT 'discovered',
    apply_error TEXT,
    discovered_at TIMESTAMPTZ DEFAULT NOW(),
    scored_at TIMESTAMPTZ,
    applied_at TIMESTAMPTZ,
    tailored_resume_path TEXT,
    cover_letter_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Profiles table
CREATE TABLE IF NOT EXISTS profiles (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    personal JSONB DEFAULT '{}',
    work_authorization JSONB DEFAULT '{}',
    experience JSONB DEFAULT '{}',
    education JSONB DEFAULT '{}',
    skills TEXT[],
    preferences JSONB DEFAULT '{}',
    compensation JSONB DEFAULT '{}',
    availability JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Settings table
CREATE TABLE IF NOT EXISTS settings (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    min_score_threshold INTEGER DEFAULT 6,
    auto_apply_enabled BOOLEAN DEFAULT false,
    email_monitoring_enabled BOOLEAN DEFAULT true,
    llm_delay FLOAT DEFAULT 4.5,
    searches JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Activity log table
CREATE TABLE IF NOT EXISTS activity (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    type TEXT NOT NULL,
    job_url TEXT,
    job_title TEXT,
    site TEXT,
    score INTEGER,
    status TEXT,
    message TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_jobs_apply_status ON jobs(apply_status);
CREATE INDEX IF NOT EXISTS idx_jobs_fit_score ON jobs(fit_score);
CREATE INDEX IF NOT EXISTS idx_jobs_discovered_at ON jobs(discovered_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_created_at ON activity(created_at DESC);

-- Enable Row Level Security (optional but recommended)
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity ENABLE ROW LEVEL SECURITY;

-- Create policy to allow all operations (adjust for your auth setup)
CREATE POLICY "Allow all for jobs" ON jobs FOR ALL USING (true);
CREATE POLICY "Allow all for profiles" ON profiles FOR ALL USING (true);
CREATE POLICY "Allow all for settings" ON settings FOR ALL USING (true);
CREATE POLICY "Allow all for activity" ON activity FOR ALL USING (true);
