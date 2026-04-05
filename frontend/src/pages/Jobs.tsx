import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { 
  Search, 
  Filter, 
  ExternalLink,
  MapPin,
  Building,
  DollarSign,
  RefreshCw,
  Briefcase
} from 'lucide-react'
import clsx from 'clsx'
import { getJobs } from '../api'
import type { Job } from '../types'

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-dark-500">—</span>
  
  const colorClass = score >= 7 ? 'score-high' : score >= 5 ? 'score-mid' : 'score-low'
  
  return (
    <span className={clsx('px-2.5 py-1 rounded-lg text-xs font-semibold', colorClass)}>
      {score}/10
    </span>
  )
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-dark-500">—</span>
  
  const statusLabels: Record<string, string> = {
    discovered: 'Discovered',
    new: 'New',
    scored: 'Scored',
    qualified: 'Qualified',
    applied: 'Applied',
    interview: 'Interview',
    rejected: 'Rejected',
    offer: 'Offer',
    needs_input: 'Needs Input',
    failed: 'Failed',
  }
  
  return (
    <span className={clsx('px-2.5 py-1 rounded-lg text-xs font-semibold', `status-${status}`)}>
      {statusLabels[status] || status}
    </span>
  )
}

function JobRow({ job, onClick }: { job: Job; onClick: () => void }) {
  return (
    <tr 
      className="table-row cursor-pointer group"
      onClick={onClick}
    >
      <td className="px-6 py-4">
        <div className="flex flex-col">
          <span className="font-medium text-dark-100 truncate max-w-xs group-hover:text-primary-400 transition-colors">
            {job.title || 'Untitled'}
          </span>
          <span className="text-sm text-dark-400 flex items-center gap-1 mt-1">
            <Building className="h-3 w-3" />
            {job.company || job.site || 'Unknown'}
          </span>
        </div>
      </td>
      <td className="px-6 py-4">
        <div className="flex items-center gap-1 text-sm text-dark-400">
          <MapPin className="h-3 w-3" />
          {job.location || 'N/A'}
        </div>
      </td>
      <td className="px-6 py-4">
        <div className="flex items-center gap-1 text-sm text-dark-400">
          <DollarSign className="h-3 w-3" />
          {job.salary || 'N/A'}
        </div>
      </td>
      <td className="px-6 py-4">
        <span className="text-sm text-dark-400">{job.site || 'Unknown'}</span>
      </td>
      <td className="px-6 py-4">
        <ScoreBadge score={job.fit_score} />
      </td>
      <td className="px-6 py-4">
        <StatusBadge status={job.apply_status} />
      </td>
      <td className="px-6 py-4">
        <span className="text-sm text-dark-500">
          {job.discovered_at ? new Date(job.discovered_at).toLocaleDateString() : '—'}
        </span>
      </td>
      <td className="px-6 py-4">
        {job.application_url && (
          <a
            href={job.application_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-primary-400 hover:text-primary-300 transition-colors"
          >
            <ExternalLink className="h-4 w-4" />
          </a>
        )}
      </td>
    </tr>
  )
}

function Jobs() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [minScore, setMinScore] = useState<number | undefined>()
  const [status, setStatus] = useState<string>('')
  const [site, setSite] = useState<string>('')

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['jobs', { search, minScore, status, site }],
    queryFn: () => getJobs({ 
      search: search || undefined, 
      min_score: minScore,
      status: status || undefined,
      site: site || undefined,
      limit: 100 
    }),
  })

  const handleJobClick = (job: Job) => {
    navigate(`/jobs/${encodeURIComponent(job.url)}`)
  }

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-dark-100 flex items-center gap-2">
            <Briefcase className="h-6 w-6 text-primary-400" />
            Jobs
          </h1>
          <p className="text-dark-400 mt-1">
            {data?.total || 0} jobs found
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="btn-secondary flex items-center gap-2"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="card p-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-dark-500" />
            <input
              type="text"
              placeholder="Search jobs..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="input w-full pl-10"
            />
          </div>

          {/* Min Score */}
          <div className="flex items-center gap-2">
            <label className="text-sm text-dark-400">Min Score:</label>
            <select
              value={minScore || ''}
              onChange={(e) => setMinScore(e.target.value ? Number(e.target.value) : undefined)}
              className="input py-2"
            >
              <option value="">All</option>
              <option value="9">9+</option>
              <option value="7">7+</option>
              <option value="5">5+</option>
            </select>
          </div>

          {/* Status */}
          <div className="flex items-center gap-2">
            <label className="text-sm text-dark-400">Status:</label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="input py-2"
            >
              <option value="">All</option>
              <option value="qualified">Qualified (7+)</option>
              <option value="applied">Applied</option>
              <option value="interview">Interview</option>
              <option value="rejected">Rejected</option>
              <option value="needs_input">Needs Input</option>
            </select>
          </div>

          {/* Site */}
          <div className="flex items-center gap-2">
            <label className="text-sm text-dark-400">Source:</label>
            <select
              value={site}
              onChange={(e) => setSite(e.target.value)}
              className="input py-2"
            >
              <option value="">All</option>
              <option value="Indeed">Indeed</option>
              <option value="LinkedIn">LinkedIn</option>
              <option value="Glassdoor">Glassdoor</option>
              <option value="ZipRecruiter">ZipRecruiter</option>
              <option value="Greenhouse">Greenhouse</option>
              <option value="Workday">Workday</option>
            </select>
          </div>

          {/* Clear filters */}
          {(search || minScore || status || site) && (
            <button
              onClick={() => {
                setSearch('')
                setMinScore(undefined)
                setStatus('')
                setSite('')
              }}
              className="text-sm text-primary-400 hover:text-primary-300 transition-colors"
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <RefreshCw className="h-8 w-8 text-primary-400 animate-spin mx-auto" />
              <p className="text-dark-400 mt-4">Loading jobs...</p>
            </div>
          </div>
        ) : data?.jobs?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-4 text-left">Job</th>
                  <th className="px-6 py-4 text-left">Location</th>
                  <th className="px-6 py-4 text-left">Salary</th>
                  <th className="px-6 py-4 text-left">Source</th>
                  <th className="px-6 py-4 text-left">Score</th>
                  <th className="px-6 py-4 text-left">Status</th>
                  <th className="px-6 py-4 text-left">Found</th>
                  <th className="px-6 py-4 text-left">Link</th>
                </tr>
              </thead>
              <tbody>
                {data.jobs.map((job) => (
                  <JobRow 
                    key={job.url} 
                    job={job} 
                    onClick={() => handleJobClick(job)} 
                  />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-64">
            <Filter className="h-12 w-12 mb-4 text-dark-600" />
            <p className="text-dark-400">No jobs found</p>
            <p className="text-sm text-dark-500 mt-1">Try adjusting your filters or run discovery</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default Jobs
