import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { 
  AlertCircle, 
  ExternalLink, 
  Building,
  RefreshCw,
  Play,
  CheckCircle,
  Shield,
  FileText,
  Lock,
  HelpCircle
} from 'lucide-react'
import clsx from 'clsx'
import { getJobsNeedingInput, applyToJob, updateJobStatus } from '../api'
import type { Job } from '../types'

function ReasonIcon({ reason }: { reason: string }) {
  const reasonLower = reason.toLowerCase()
  
  if (reasonLower.includes('captcha')) return <Shield className="h-5 w-5 text-amber-400" />
  if (reasonLower.includes('login')) return <Lock className="h-5 w-5 text-red-400" />
  if (reasonLower.includes('cover letter')) return <FileText className="h-5 w-5 text-blue-400" />
  if (reasonLower.includes('work authorization')) return <HelpCircle className="h-5 w-5 text-orange-400" />
  
  return <AlertCircle className="h-5 w-5 text-dark-400" />
}

function NeedsInputCard({ 
  job, 
  reason,
  onRetry,
  onSkip,
  onView,
  retrying
}: { 
  job: Job
  reason: string
  onRetry: () => void
  onSkip: () => void
  onView: () => void
  retrying: boolean
}) {
  return (
    <div className="card p-6 animate-fadeIn">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          <div className="p-2 rounded-lg bg-amber-500/20">
            <ReasonIcon reason={reason} />
          </div>
          <div>
            <h3 className="font-medium text-dark-100">
              {job.title || 'Untitled'}
            </h3>
            <div className="flex items-center gap-2 mt-1 text-sm text-dark-400">
              <Building className="h-4 w-4" />
              {job.company || job.site || 'Unknown'}
            </div>
          </div>
        </div>
        {job.fit_score && (
          <span className={clsx(
            'px-2.5 py-1 rounded-lg text-xs font-semibold',
            job.fit_score >= 7 ? 'score-high' : job.fit_score >= 5 ? 'score-mid' : 'score-low'
          )}>
            {job.fit_score}/10
          </span>
        )}
      </div>

      {/* Reason */}
      <div className="mt-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
        <p className="text-sm text-amber-400 font-medium">Issue: {reason}</p>
        {job.apply_error && (
          <p className="text-xs text-amber-500/80 mt-1">{job.apply_error}</p>
        )}
      </div>

      {/* Actions */}
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          onClick={onRetry}
          disabled={retrying}
          className="btn-primary flex items-center gap-2 text-sm py-2"
        >
          {retrying ? (
            <RefreshCw className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          Retry
        </button>
        <button
          onClick={onView}
          className="btn-secondary flex items-center gap-2 text-sm py-2"
        >
          <ExternalLink className="h-4 w-4" />
          View Details
        </button>
        {job.application_url && (
          <a
            href={job.application_url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-secondary flex items-center gap-2 text-sm py-2"
          >
            <ExternalLink className="h-4 w-4" />
            Apply Manually
          </a>
        )}
        <button
          onClick={onSkip}
          className="btn-ghost flex items-center gap-2 text-sm py-2"
        >
          <CheckCircle className="h-4 w-4" />
          Mark Resolved
        </button>
      </div>
    </div>
  )
}

function NeedsInput() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['jobs-needs-input'],
    queryFn: getJobsNeedingInput,
  })

  const retryMutation = useMutation({
    mutationFn: (jobUrl: string) => applyToJob(jobUrl),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs-needs-input'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })

  const skipMutation = useMutation({
    mutationFn: (jobUrl: string) => updateJobStatus(jobUrl, 'applied'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs-needs-input'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <RefreshCw className="h-8 w-8 text-primary-400 animate-spin mx-auto" />
          <p className="text-dark-400 mt-4">Loading...</p>
        </div>
      </div>
    )
  }

  const jobs = data?.jobs || []

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-dark-100 flex items-center gap-2">
            <AlertCircle className="h-6 w-6 text-amber-400" />
            Needs Input
          </h1>
          <p className="text-dark-400 mt-1">
            {jobs.length} job{jobs.length !== 1 ? 's' : ''} need your attention
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

      {/* Info */}
      <div className="card p-4 border-blue-500/30 bg-blue-500/5">
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-lg bg-blue-500/20">
            <AlertCircle className="h-5 w-5 text-blue-400" />
          </div>
          <div>
            <p className="text-sm text-blue-300 font-medium">
              These jobs encountered issues during auto-apply
            </p>
            <p className="text-xs text-blue-400/80 mt-1">
              Common issues include CAPTCHAs, login requirements, missing information, or custom fields.
              You can retry, apply manually, or mark as resolved.
            </p>
          </div>
        </div>
      </div>

      {/* Jobs List */}
      {jobs.length > 0 ? (
        <div className="space-y-4">
          {jobs.map((job) => (
            <NeedsInputCard
              key={job.url}
              job={job}
              reason={job.reason || 'Unknown issue'}
              onRetry={() => retryMutation.mutate(job.url)}
              onSkip={() => skipMutation.mutate(job.url)}
              onView={() => navigate(`/jobs/${encodeURIComponent(job.url)}`)}
              retrying={retryMutation.isPending && retryMutation.variables === job.url}
            />
          ))}
        </div>
      ) : (
        <div className="card p-12 text-center">
          <div className="p-4 rounded-full bg-emerald-500/20 w-fit mx-auto mb-4">
            <CheckCircle className="h-12 w-12 text-emerald-400" />
          </div>
          <h3 className="text-lg font-medium text-dark-100">All clear!</h3>
          <p className="text-dark-400 mt-1">
            No jobs need your attention right now.
          </p>
        </div>
      )}
    </div>
  )
}

export default NeedsInput
