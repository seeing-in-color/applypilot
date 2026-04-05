import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || ''
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || ''

if (!supabaseUrl || !supabaseAnonKey) {
  console.warn('Supabase credentials not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in .env')
}

export const supabase = createClient(
  supabaseUrl || '',
  supabaseAnonKey || ''
)

// Database types for TypeScript
export interface Job {
  id: string
  job_id: string
  title: string
  company: string
  location?: string
  description?: string
  job_type?: string
  salary_min?: number
  salary_max?: number
  url: string
  site?: string
  search_term?: string
  date_posted?: string
  discovered_at: string
  score?: number
  score_reason?: string
  status: string
  applied_at?: string
  cover_letter?: string
  tailored_resume_path?: string
  notes?: string
  created_at: string
  updated_at: string
}

export interface Application {
  id: string
  job_id: string
  status: string
  applied_at: string
  response_at?: string
  response_type?: string
  notes?: string
  created_at: string
  updated_at: string
}

export interface EmailEvent {
  id: string
  job_id?: string
  email_id: string
  subject?: string
  sender?: string
  received_at?: string
  classification?: string
  snippet?: string
  processed_at: string
}

export interface Profile {
  id: string
  user_id?: string
  first_name?: string
  last_name?: string
  email?: string
  phone?: string
  city?: string
  country?: string
  linkedin_url?: string
  github_url?: string
  portfolio_url?: string
  resume_text?: string
  work_authorization?: Record<string, string>
  experience?: Record<string, string | number>
  created_at: string
  updated_at: string
}

export interface Settings {
  id: string
  user_id?: string
  min_score_threshold: number
  auto_apply_enabled: boolean
  email_monitoring_enabled: boolean
  llm_delay: number
  created_at: string
  updated_at: string
}

// Helper functions for Supabase queries
export const jobsApi = {
  async getAll(filters?: { status?: string; minScore?: number }) {
    let query = supabase.from('jobs').select('*').order('discovered_at', { ascending: false })
    
    if (filters?.status) {
      query = query.eq('status', filters.status)
    }
    if (filters?.minScore) {
      query = query.gte('score', filters.minScore)
    }
    
    return query
  },
  
  async getById(id: string) {
    return supabase.from('jobs').select('*').eq('id', id).single()
  },
  
  async updateStatus(id: string, status: string) {
    return supabase.from('jobs').update({ status, updated_at: new Date().toISOString() }).eq('id', id)
  },
  
  async getStats() {
    const { data: jobs } = await supabase.from('jobs').select('status, score')
    
    if (!jobs) return { total: 0, scored: 0, applied: 0, interviews: 0, avg_score: 0 }
    
    return {
      total: jobs.length,
      scored: jobs.filter(j => j.score !== null).length,
      applied: jobs.filter(j => j.status === 'applied').length,
      interviews: jobs.filter(j => j.status === 'interview').length,
      avg_score: jobs.filter(j => j.score).reduce((sum, j) => sum + (j.score || 0), 0) / 
                 jobs.filter(j => j.score).length || 0
    }
  }
}

export const profileApi = {
  async get() {
    return supabase.from('profiles').select('*').single()
  },
  
  async upsert(profile: Partial<Profile>) {
    return supabase.from('profiles').upsert({
      ...profile,
      updated_at: new Date().toISOString()
    })
  }
}

export const settingsApi = {
  async get() {
    return supabase.from('settings').select('*').single()
  },
  
  async upsert(settings: Partial<Settings>) {
    return supabase.from('settings').upsert({
      ...settings,
      updated_at: new Date().toISOString()
    })
  }
}

export const activityApi = {
  async getRecent(limit = 20) {
    return supabase
      .from('activity_log')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(limit)
  },
  
  async log(action: string, details?: Record<string, unknown>) {
    return supabase.from('activity_log').insert({ action, details })
  }
}
