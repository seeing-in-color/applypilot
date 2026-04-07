import { supabase } from './supabase'
import type { Job, Stats, Profile, Settings, SearchConfig, Activity, EmailStatus } from './types'

// Backend API URL - set VITE_API_URL to your deployed FastAPI backend
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const SUPABASE_CONFIGURED = !!(import.meta.env.VITE_SUPABASE_URL && import.meta.env.VITE_SUPABASE_ANON_KEY)

async function fetchBackend<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

// Stats API - prefer backend, fall back to Supabase
export async function getStats(): Promise<Stats> {
  // Try backend first
  try {
    return await fetchBackend<Stats>('/api/stats')
  } catch (e) {
    console.log('Backend unavailable, trying Supabase...')
  }
  
  // Fall back to Supabase
  if (!SUPABASE_CONFIGURED) {
    return {
      total_discovered: 0,
      total_enriched: 0,
      total_scored: 0,
      high_fit: 0,
      mid_fit: 0,
      low_fit: 0,
      applied: 0,
      failed: 0,
      pending_input: 0,
      interviews: 0,
      offers: 0,
      rejected: 0
    }
  }
  
  const { data: jobs, error } = await supabase.from('jobs').select('apply_status, fit_score')
  
  if (error) {
    console.error('Error fetching stats:', error)
    return {
      total_discovered: 0,
      total_enriched: 0,
      total_scored: 0,
      high_fit: 0,
      mid_fit: 0,
      low_fit: 0,
      applied: 0,
      failed: 0,
      pending_input: 0,
      interviews: 0,
      offers: 0,
      rejected: 0
    }
  }
  
  const scoredJobs = jobs?.filter(j => j.fit_score !== null) || []

  return {
    total_discovered: jobs?.length || 0,
    total_enriched: jobs?.filter(j => j.apply_status !== 'discovered').length || 0,
    total_scored: scoredJobs.length,
    high_fit: scoredJobs.filter(j => (j.fit_score || 0) >= 7).length,
    mid_fit: scoredJobs.filter(j => (j.fit_score || 0) >= 5 && (j.fit_score || 0) < 7).length,
    low_fit: scoredJobs.filter(j => (j.fit_score || 0) < 5).length,
    applied: jobs?.filter(j => j.apply_status === 'applied').length || 0,
    failed: jobs?.filter(j => j.apply_status === 'failed').length || 0,
    pending_input: jobs?.filter(j => j.apply_status === 'needs_input').length || 0,
    interviews: jobs?.filter(j => j.apply_status === 'interview').length || 0,
    offers: jobs?.filter(j => j.apply_status === 'offer').length || 0,
    rejected: jobs?.filter(j => j.apply_status === 'rejected').length || 0
  }
}

// Jobs API - prefer backend, fall back to Supabase
export async function getJobs(params?: {
  status?: string
  min_score?: number
  max_score?: number
  site?: string
  search?: string
  limit?: number
  offset?: number
}): Promise<{ jobs: Job[]; total: number }> {
  // Try backend first
  try {
    const searchParams = new URLSearchParams()
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          searchParams.set(key, String(value))
        }
      })
    }
    const query = searchParams.toString()
    return await fetchBackend<{ jobs: Job[]; total: number }>(`/api/jobs${query ? `?${query}` : ''}`)
  } catch (e) {
    console.log('Backend unavailable for jobs, trying Supabase...')
  }

  // Fall back to Supabase
  if (!SUPABASE_CONFIGURED) {
    return { jobs: [], total: 0 }
  }

  let query = supabase.from('jobs').select('*', { count: 'exact' })
  
  if (params?.status) {
    query = query.eq('apply_status', params.status)
  }
  if (params?.min_score) {
    query = query.gte('fit_score', params.min_score)
  }
  if (params?.max_score) {
    query = query.lte('fit_score', params.max_score)
  }
  if (params?.site) {
    query = query.eq('site', params.site)
  }
  if (params?.search) {
    query = query.or(`title.ilike.%${params.search}%,company.ilike.%${params.search}%`)
  }
  
  query = query.order('discovered_at', { ascending: false })
  
  if (params?.limit) {
    query = query.limit(params.limit)
  }
  if (params?.offset) {
    query = query.range(params.offset, params.offset + (params.limit || 50) - 1)
  }
  
  const { data, count, error } = await query
  
  if (error) {
    console.error('Error fetching jobs:', error)
    return { jobs: [], total: 0 }
  }
  
  // Map Supabase fields to frontend Job type
  const jobs: Job[] = (data || []).map(j => ({
    url: j.url,
    title: j.title,
    company: j.company,
    site: j.site,
    location: j.location,
    salary: j.salary,
    strategy: j.strategy || null,
    description: j.description,
    full_description: j.full_description,
    application_url: j.application_url,
    fit_score: j.fit_score,
    score_reasoning: j.score_reasoning,
    apply_status: j.apply_status,
    apply_error: j.apply_error || null,
    discovered_at: j.discovered_at,
    scored_at: j.scored_at,
    applied_at: j.applied_at,
    tailored_resume_path: j.tailored_resume_path,
    cover_letter_path: j.cover_letter_path,
  }))
  
  return { jobs, total: count || 0 }
}

export async function getJob(jobUrl: string): Promise<Job> {
  // Try backend first
  try {
    return await fetchBackend<Job>(`/api/jobs/${encodeURIComponent(jobUrl)}`)
  } catch (e) {
    console.log('Backend unavailable for job detail, trying Supabase...')
  }

  if (!SUPABASE_CONFIGURED) {
    throw new Error('Job not found')
  }

  const { data, error } = await supabase
    .from('jobs')
    .select('*')
    .eq('url', jobUrl)
    .single()
  
  if (error || !data) {
    throw new Error('Job not found')
  }
  
  return {
    url: data.url,
    title: data.title,
    company: data.company,
    site: data.site,
    location: data.location,
    salary: data.salary,
    strategy: data.strategy || null,
    description: data.description,
    full_description: data.full_description,
    application_url: data.application_url,
    fit_score: data.fit_score,
    score_reasoning: data.score_reasoning,
    apply_status: data.apply_status,
    apply_error: data.apply_error || null,
    discovered_at: data.discovered_at,
    scored_at: data.scored_at,
    applied_at: data.applied_at,
    tailored_resume_path: data.tailored_resume_path,
    cover_letter_path: data.cover_letter_path,
  }
}

export async function updateJobStatus(jobUrl: string, status: string): Promise<void> {
  const { error } = await supabase
    .from('jobs')
    .update({ apply_status: status, updated_at: new Date().toISOString() })
    .eq('url', jobUrl)
  
  if (error) {
    throw new Error('Failed to update status')
  }
}

export async function getJobsNeedingInput(): Promise<{ jobs: (Job & { reason: string })[] }> {
  // Try backend first
  try {
    return await fetchBackend<{ jobs: (Job & { reason: string })[] }>('/api/jobs/needs-input')
  } catch (e) {
    console.log('Backend unavailable for needs-input, trying Supabase...')
  }

  if (!SUPABASE_CONFIGURED) {
    return { jobs: [] }
  }

  const { data, error } = await supabase
    .from('jobs')
    .select('*')
    .eq('apply_status', 'needs_input')
    .order('discovered_at', { ascending: false })
  
  if (error) {
    console.error('Error fetching jobs needing input:', error)
    return { jobs: [] }
  }
  
  return {
    jobs: (data || []).map(j => ({
      url: j.url,
      title: j.title,
      company: j.company,
      site: j.site,
      location: j.location,
      salary: j.salary,
      strategy: j.strategy || null,
      description: j.description,
      full_description: j.full_description,
      application_url: j.application_url,
      fit_score: j.fit_score,
      score_reasoning: j.score_reasoning,
      apply_status: j.apply_status,
      apply_error: j.apply_error || null,
      discovered_at: j.discovered_at,
      scored_at: j.scored_at,
      applied_at: j.applied_at,
      tailored_resume_path: j.tailored_resume_path,
      cover_letter_path: j.cover_letter_path,
      reason: j.apply_error || 'Missing information required'
    }))
  }
}

// Profile API
export async function getProfile(): Promise<{ profile: Profile | null; exists: boolean }> {
  // Try backend first
  try {
    return await fetchBackend<{ profile: Profile | null; exists: boolean }>('/api/profile')
  } catch (e) {
    console.log('Backend unavailable for profile, trying Supabase...')
  }

  if (!SUPABASE_CONFIGURED) {
    return { profile: null, exists: false }
  }

  const { data, error } = await supabase.from('profiles').select('*').limit(1).single()
  
  if (error && error.code !== 'PGRST116') {
    console.error('Error fetching profile:', error)
  }
  
  return { profile: data || null, exists: !!data }
}

export async function updateProfile(profile: Partial<Profile>): Promise<{ profile: Profile }> {
  // Try backend first
  try {
    return await fetchBackend<{ profile: Profile }>('/api/profile', {
      method: 'PUT',
      body: JSON.stringify(profile),
    })
  } catch (e) {
    console.log('Backend unavailable for profile update, trying Supabase...')
  }

  if (!SUPABASE_CONFIGURED) {
    throw new Error('Profile update requires backend or Supabase')
  }

  const { data: existing } = await supabase.from('profiles').select('id').limit(1).single()
  
  let result
  if (existing) {
    result = await supabase
      .from('profiles')
      .update({ ...profile, updated_at: new Date().toISOString() })
      .eq('id', existing.id)
      .select()
      .single()
  } else {
    result = await supabase
      .from('profiles')
      .insert({ ...profile, created_at: new Date().toISOString(), updated_at: new Date().toISOString() })
      .select()
      .single()
  }
  
  if (result.error) {
    throw new Error('Failed to update profile')
  }
  
  return { profile: result.data }
}

export async function uploadResume(_file: File): Promise<{ message: string; path: string }> {
  // Resume upload requires backend - return placeholder for static deployment
  return { message: 'Resume upload requires backend server', path: '' }
}

// Settings API
export async function getSettings(): Promise<Settings> {
  // Try backend first
  try {
    return await fetchBackend<Settings>('/api/settings')
  } catch (e) {
    console.log('Backend unavailable for settings, trying Supabase...')
  }

  if (!SUPABASE_CONFIGURED) {
    return {
      min_score_threshold: 6,
      auto_apply_enabled: false,
      email_monitoring_enabled: true,
      llm_delay: 4.5
    }
  }

  const { data, error } = await supabase.from('settings').select('*').limit(1).single()
  
  if (error && error.code !== 'PGRST116') {
    console.error('Error fetching settings:', error)
  }
  
  return data || {
    min_score_threshold: 6,
    auto_apply_enabled: false,
    email_monitoring_enabled: true,
    llm_delay: 4.5
  }
}

export async function updateSettings(settings: Partial<Settings>): Promise<Settings> {
  // Try backend first
  try {
    return await fetchBackend<Settings>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    })
  } catch (e) {
    console.log('Backend unavailable for settings update, trying Supabase...')
  }

  if (!SUPABASE_CONFIGURED) {
    throw new Error('Settings update requires backend or Supabase')
  }

  const { data: existing } = await supabase.from('settings').select('id').limit(1).single()
  
  let result
  if (existing) {
    result = await supabase
      .from('settings')
      .update({ ...settings, updated_at: new Date().toISOString() })
      .eq('id', existing.id)
      .select()
      .single()
  } else {
    result = await supabase
      .from('settings')
      .insert({ ...settings, created_at: new Date().toISOString(), updated_at: new Date().toISOString() })
      .select()
      .single()
  }
  
  if (result.error) {
    throw new Error('Failed to update settings')
  }
  
  return result.data
}

// Pipeline API - uses backend if VITE_API_URL is configured
export async function runDiscover(): Promise<{ message: string; status: string }> {
  const result = await fetchBackend<{ message: string; status: string }>('/api/pipeline/discover', { method: 'POST' })
  if (result) return result
  return { message: 'Set VITE_API_URL to enable discovery', status: 'unavailable' }
}

export async function runScore(_minScore?: number): Promise<{ message: string; status: string }> {
  const params = _minScore !== undefined ? `?min_score=${_minScore}` : ''
  const result = await fetchBackend<{ message: string; status: string }>(`/api/pipeline/score${params}`, { method: 'POST' })
  if (result) return result
  return { message: 'Set VITE_API_URL to enable scoring', status: 'unavailable' }
}

export async function runApply(params?: {
  job_url?: string
  min_score?: number
  dry_run?: boolean
}): Promise<{ message: string; status: string }> {
  const searchParams = new URLSearchParams()
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.set(key, String(value))
      }
    })
  }
  const query = searchParams.toString()
  const result = await fetchBackend<{ message: string; status: string }>(`/api/pipeline/apply${query ? `?${query}` : ''}`, { method: 'POST' })
  if (result) return result
  return { message: 'Set VITE_API_URL to enable auto-apply', status: 'unavailable' }
}

export async function applyToJob(jobUrl: string, dryRun = false): Promise<{ message: string; status: string }> {
  const params = dryRun ? '?dry_run=true' : ''
  const result = await fetchBackend<{ message: string; status: string }>(`/api/pipeline/apply/${encodeURIComponent(jobUrl)}${params}`, { method: 'POST' })
  if (result) return result
  return { message: 'Set VITE_API_URL to enable auto-apply', status: 'unavailable' }
}

// Search config API
export async function getSearches(): Promise<{ searches: SearchConfig[] }> {
  const { data } = await supabase.from('settings').select('searches').limit(1).single()
  return { searches: data?.searches || [] }
}

export async function updateSearches(searches: SearchConfig[]): Promise<{ message: string }> {
  const { data: existing } = await supabase.from('settings').select('id').limit(1).single()
  
  if (existing) {
    await supabase.from('settings').update({ searches }).eq('id', existing.id)
  }
  
  return { message: 'Searches updated' }
}

// Email API - requires backend
export async function getEmailStatus(): Promise<EmailStatus> {
  return { authenticated: false, error: 'Email monitoring requires local backend' }
}

export async function syncEmails(_daysBack = 7): Promise<{ message: string; status: string }> {
  return { message: 'Email sync requires local backend', status: 'unavailable' }
}

export async function authenticateEmail(): Promise<{ message?: string; error?: string }> {
  return { error: 'Email authentication requires local backend' }
}

// Activity API
export async function getActivity(limit = 50): Promise<{ activities: Activity[] }> {
  // Try backend first
  try {
    return await fetchBackend<{ activities: Activity[] }>(`/api/activity?limit=${limit}`)
  } catch (e) {
    console.log('Backend unavailable for activity, trying Supabase...')
  }

  if (!SUPABASE_CONFIGURED) {
    return { activities: [] }
  }

  const { data, error } = await supabase
    .from('activity')
    .select('*')
    .order('created_at', { ascending: false })
    .limit(limit)
  
  if (error) {
    // Activity table might not exist - return empty
    return { activities: [] }
  }
  
  return { activities: data || [] }
}
