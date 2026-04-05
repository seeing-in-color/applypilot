// Job types
export interface Job {
  url: string
  title: string | null
  company: string | null
  location: string | null
  salary: string | null
  site: string | null
  strategy: string | null
  description: string | null
  full_description: string | null
  application_url: string | null
  fit_score: number | null
  score_reasoning: string | null
  apply_status: string | null
  apply_error: string | null
  discovered_at: string | null
  scored_at: string | null
  applied_at: string | null
  tailored_resume_path: string | null
  cover_letter_path: string | null
}

// Stats types
export interface Stats {
  total_discovered: number
  total_enriched: number
  total_scored: number
  high_fit: number
  mid_fit: number
  low_fit: number
  applied: number
  failed: number
  pending_input: number
  interviews: number
  offers: number
  rejected: number
}

// Profile types
export interface Profile {
  personal?: {
    first_name?: string
    last_name?: string
    email?: string
    phone?: string
    linkedin_url?: string
    github_url?: string
    portfolio_url?: string
    city?: string
    country?: string
    application_source?: string
  }
  work_authorization?: {
    legally_authorized_to_work?: string
    require_sponsorship?: string
  }
  experience?: {
    years?: number
    current_title?: string
    current_company?: string
  }
  education?: {
    school?: string
    degree?: string
    field?: string
    graduation_year?: number
  }
  skills?: string[]
  preferences?: {
    remote_preference?: string
    willing_to_relocate?: string
  }
  compensation?: {
    desired_salary?: string
  }
  availability?: {
    start_date?: string
    willing_to_relocate?: string
    remote_preference?: string
  }
}

// Settings types
export interface Settings {
  min_score_threshold: number
  auto_apply_enabled: boolean
  email_monitoring_enabled: boolean
  llm_delay: number
}

// Search config types
export interface SearchConfig {
  titles: string[]
  locations: string[]
  remote_only: boolean
  salary_min?: number
}

// Activity types
export interface Activity {
  type: 'discovered' | 'scored' | 'applied' | 'status_change'
  job_url: string
  job_title: string | null
  site?: string
  score?: number
  status?: string
  timestamp: string
  message: string
}

// Email status types
export interface EmailStatus {
  authenticated: boolean
  auth_url?: string
  error?: string
}
