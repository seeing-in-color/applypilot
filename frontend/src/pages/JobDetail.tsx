import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  ArrowLeft, 
  ExternalLink, 
  MapPin, 
  Building, 
  DollarSign,
  FileText,
  Play,
  RefreshCw,
  CheckCircle,
  XCircle,
  Sparkles
} from 'lucide-react'
import clsx from 'clsx'
import { getJob, updateJobStatus, applyToJob } from '../api'

function JobDetail() {
  const { jobUrl } = useParams<{ jobUrl: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: job, isLoading, error } = useQuery({
    queryKey: ['job', jobUrl],
    queryFn: () => getJob(decodeURIComponent(jobUrl || '')),
    enabled: !!jobUrl,
  })

  const statusMutation = useMutation({
    mutationFn: ({ status }: { status: string }) => 
      updateJobStatus(decodeURIComponent(jobUrl || ''), status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['job', jobUrl] })
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  const applyMutation = useMutation({
    mutationFn: () => applyToJob(decodeURIComponent(jobUrl || '')),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['job', jobUrl] })
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <RefreshCw className="h-8 w-8 text-primary-400 animate-spin mx-auto" />
          <p className="text-dark-400 mt-4">Loading job details...</p>
        </div>
      </div>
    )
  }

  if (error || !job) {
    return (
      <div className="text-center py-16">
        <div className="p-4 rounded-full bg-red-500/20 w-fit mx-auto mb-4">
          <XCircle className="h-12 w-12 text-red-400" />
        </div>
        <h2 className="text-xl font-semibold text-dark-100">Job not found</h2>
        <button
          onClick={() => navigate('/jobs')}
          className="mt-4 text-primary-400 hover:text-primary-300 transition-colors"
        >
          Back to jobs
        </button>
      </div>
    )
  }

  const scoreColor = job.fit_score 
    ? job.fit_score >= 7 ? 'text-emerald-400' 
    : job.fit_score >= 5 ? 'text-amber-400' 
    : 'text-red-400'
    : 'text-dark-500'

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/jobs')}
          className="p-2 hover:bg-dark-800 rounded-lg transition-colors text-dark-400 hover:text-dark-200"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-dark-100">
            {job.title || 'Untitled Job'}
          </h1>
          <div className="flex flex-wrap items-center gap-4 mt-2 text-dark-400">
            <span className="flex items-center gap-1">
              <Building className="h-4 w-4" />
              {job.company || job.site || 'Unknown Company'}
            </span>
            {job.location && (
              <span className="flex items-center gap-1">
                <MapPin className="h-4 w-4" />
                {job.location}
              </span>
            )}
            {job.salary && (
              <span className="flex items-center gap-1">
                <DollarSign className="h-4 w-4" />
                {job.salary}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-3">
        {job.application_url && (
          <a
            href={job.application_url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-secondary flex items-center gap-2"
          >
            <ExternalLink className="h-4 w-4" />
            Open Application
          </a>
        )}
        <button
          onClick={() => applyMutation.mutate()}
          disabled={applyMutation.isPending || job.apply_status === 'applied'}
          className={clsx(
            'flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all',
            job.apply_status === 'applied'
              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 cursor-default'
              : 'btn-primary'
          )}
        >
          {applyMutation.isPending ? (
            <RefreshCw className="h-4 w-4 animate-spin" />
          ) : job.apply_status === 'applied' ? (
            <CheckCircle className="h-4 w-4" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          {job.apply_status === 'applied' ? 'Applied' : 'Auto-Apply'}
        </button>
        <select
          value={job.apply_status || ''}
          onChange={(e) => statusMutation.mutate({ status: e.target.value })}
          className="input py-2"
        >
          <option value="">Set Status...</option>
          <option value="discovered">Discovered</option>
          <option value="scored">Scored</option>
          <option value="qualified">Qualified</option>
          <option value="applied">Applied</option>
          <option value="interview">Interview</option>
          <option value="rejected">Rejected</option>
          <option value="offer">Offer</option>
          <option value="needs_input">Needs Input</option>
        </select>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Main content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Job Description */}
          <div className="card p-6">
            <h2 className="text-lg font-semibold text-dark-100 mb-4 flex items-center gap-2">
              <div className="p-2 rounded-lg bg-primary-500/20">
                <FileText className="h-5 w-5 text-primary-400" />
              </div>
              Job Description
            </h2>
            <div className="prose prose-sm max-w-none prose-invert">
              {job.full_description ? (
                <div className="whitespace-pre-wrap text-dark-300 leading-relaxed">
                  {job.full_description}
                </div>
              ) : job.description ? (
                <p className="text-dark-300">{job.description}</p>
              ) : (
                <p className="text-dark-500 italic">No description available</p>
              )}
            </div>
          </div>

          {/* Score Reasoning */}
          {job.score_reasoning && (
            <div className="card p-6">
              <h2 className="text-lg font-semibold text-dark-100 mb-4 flex items-center gap-2">
                <div className="p-2 rounded-lg bg-amber-500/20">
                  <Sparkles className="h-5 w-5 text-amber-400" />
                </div>
                AI Score Analysis
              </h2>
              <div className="whitespace-pre-wrap text-dark-300 leading-relaxed">
                {job.score_reasoning}
              </div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Score Card */}
          <div className="card p-6 relative overflow-hidden">
            <div className={clsx(
              'absolute inset-0 bg-gradient-to-br opacity-30',
              job.fit_score && job.fit_score >= 7 ? 'from-emerald-500/20 to-emerald-600/5' :
              job.fit_score && job.fit_score >= 5 ? 'from-amber-500/20 to-amber-600/5' :
              'from-dark-700 to-dark-800'
            )} />
            <div className="relative">
              <h3 className="text-sm font-semibold text-dark-400 uppercase tracking-wider mb-3">
                Fit Score
              </h3>
              <div className={clsx('text-5xl font-bold', scoreColor)}>
                {job.fit_score !== null ? `${job.fit_score}/10` : '—'}
              </div>
              {job.fit_score !== null && (
                <p className="text-sm text-dark-400 mt-2">
                  {job.fit_score >= 7 ? 'High fit - recommended to apply' :
                   job.fit_score >= 5 ? 'Moderate fit - review before applying' :
                   'Low fit - consider skipping'}
                </p>
              )}
            </div>
          </div>

          {/* Status Card */}
          <div className="card p-6">
            <h3 className="text-sm font-semibold text-dark-400 uppercase tracking-wider mb-3">
              Status
            </h3>
            <span className={clsx(
              'inline-block px-3 py-1.5 rounded-lg text-sm font-semibold',
              job.apply_status ? `status-${job.apply_status}` : 'bg-dark-700 text-dark-400'
            )}>
              {job.apply_status || 'Not scored'}
            </span>
          </div>

          {/* Timeline */}
          <div className="card p-6">
            <h3 className="text-sm font-semibold text-dark-400 uppercase tracking-wider mb-3">
              Timeline
            </h3>
            <div className="space-y-3 text-sm">
              {job.discovered_at && (
                <div className="flex justify-between">
                  <span className="text-dark-500">Discovered</span>
                  <span className="text-dark-200">
                    {new Date(job.discovered_at).toLocaleDateString()}
                  </span>
                </div>
              )}
              {job.scored_at && (
                <div className="flex justify-between">
                  <span className="text-dark-500">Scored</span>
                  <span className="text-dark-200">
                    {new Date(job.scored_at).toLocaleDateString()}
                  </span>
                </div>
              )}
              {job.applied_at && (
                <div className="flex justify-between">
                  <span className="text-dark-500">Applied</span>
                  <span className="text-dark-200">
                    {new Date(job.applied_at).toLocaleDateString()}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Files */}
          {(job.tailored_resume_path || job.cover_letter_path) && (
            <div className="card p-6">
              <h3 className="text-sm font-semibold text-dark-400 uppercase tracking-wider mb-3">
                Documents
              </h3>
              <div className="space-y-2">
                {job.tailored_resume_path && (
                  <div className="flex items-center gap-2 text-sm text-dark-300">
                    <FileText className="h-4 w-4 text-primary-400" />
                    Tailored Resume
                  </div>
                )}
                {job.cover_letter_path && (
                  <div className="flex items-center gap-2 text-sm text-dark-300">
                    <FileText className="h-4 w-4 text-primary-400" />
                    Cover Letter
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default JobDetail
