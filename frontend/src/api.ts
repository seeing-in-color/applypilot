import type { Job, Stats, Profile, Settings, SearchConfig, Activity, EmailStatus } from './types'

const API_BASE = '/api'

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
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

// Stats API
export async function getStats(): Promise<Stats> {
  return fetchJSON<Stats>('/stats')
}

// Jobs API
export async function getJobs(params?: {
  status?: string
  min_score?: number
  max_score?: number
  site?: string
  search?: string
  limit?: number
  offset?: number
}): Promise<{ jobs: Job[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        searchParams.set(key, String(value))
      }
    })
  }
  const query = searchParams.toString()
  return fetchJSON<{ jobs: Job[]; total: number }>(`/jobs${query ? `?${query}` : ''}`)
}

export async function getJob(jobUrl: string): Promise<Job> {
  return fetchJSON<Job>(`/jobs/${encodeURIComponent(jobUrl)}`)
}

export async function updateJobStatus(jobUrl: string, status: string): Promise<void> {
  await fetchJSON(`/jobs/${encodeURIComponent(jobUrl)}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
}

export async function getJobsNeedingInput(): Promise<{ jobs: (Job & { reason: string })[] }> {
  return fetchJSON<{ jobs: (Job & { reason: string })[] }>('/jobs/needs-input')
}

// Profile API
export async function getProfile(): Promise<{ profile: Profile | null; exists: boolean }> {
  return fetchJSON<{ profile: Profile | null; exists: boolean }>('/profile')
}

export async function updateProfile(profile: Partial<Profile>): Promise<{ profile: Profile }> {
  return fetchJSON<{ profile: Profile }>('/profile', {
    method: 'PUT',
    body: JSON.stringify(profile),
  })
}

export async function uploadResume(file: File): Promise<{ message: string; path: string }> {
  const formData = new FormData()
  formData.append('file', file)
  
  const response = await fetch(`${API_BASE}/resume/upload`, {
    method: 'POST',
    body: formData,
  })
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Upload failed' }))
    throw new Error(error.detail)
  }
  
  return response.json()
}

// Settings API
export async function getSettings(): Promise<Settings> {
  return fetchJSON<Settings>('/settings')
}

export async function updateSettings(settings: Partial<Settings>): Promise<Settings> {
  return fetchJSON<Settings>('/settings', {
    method: 'PUT',
    body: JSON.stringify(settings),
  })
}

// Pipeline API
export async function runDiscover(): Promise<{ message: string; status: string }> {
  return fetchJSON<{ message: string; status: string }>('/pipeline/discover', { method: 'POST' })
}

export async function runScore(minScore?: number): Promise<{ message: string; status: string }> {
  const params = minScore !== undefined ? `?min_score=${minScore}` : ''
  return fetchJSON<{ message: string; status: string }>(`/pipeline/score${params}`, { method: 'POST' })
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
  return fetchJSON<{ message: string; status: string }>(`/pipeline/apply${query ? `?${query}` : ''}`, { method: 'POST' })
}

export async function applyToJob(jobUrl: string, dryRun = false): Promise<{ message: string; status: string }> {
  const params = dryRun ? '?dry_run=true' : ''
  return fetchJSON<{ message: string; status: string }>(`/pipeline/apply/${encodeURIComponent(jobUrl)}${params}`, { method: 'POST' })
}

// Search config API
export async function getSearches(): Promise<{ searches: SearchConfig[] }> {
  return fetchJSON<{ searches: SearchConfig[] }>('/searches')
}

export async function updateSearches(searches: SearchConfig[]): Promise<{ message: string }> {
  return fetchJSON<{ message: string }>('/searches', {
    method: 'PUT',
    body: JSON.stringify(searches),
  })
}

// Email API
export async function getEmailStatus(): Promise<EmailStatus> {
  return fetchJSON<EmailStatus>('/email/status')
}

export async function syncEmails(daysBack = 7): Promise<{ message: string; status: string }> {
  return fetchJSON<{ message: string; status: string }>(`/email/sync?days_back=${daysBack}`, { method: 'POST' })
}

export async function authenticateEmail(): Promise<{ message?: string; error?: string }> {
  return fetchJSON<{ message?: string; error?: string }>('/email/auth', { method: 'POST' })
}

// Activity API
export async function getActivity(limit = 50): Promise<{ activities: Activity[] }> {
  return fetchJSON<{ activities: Activity[] }>(`/activity?limit=${limit}`)
}
