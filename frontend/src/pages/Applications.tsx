import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { 
  Send, 
  Calendar, 
  Award, 
  XCircle, 
  Clock,
  Building,
  RefreshCw,
  ChevronRight
} from 'lucide-react'
import clsx from 'clsx'
import { getJobs } from '../api'
import type { Job } from '../types'

function ApplicationCard({ job, onClick }: { job: Job; onClick: () => void }) {
  const statusConfig: Record<string, { icon: typeof Send; color: string; bgColor: string; label: string }> = {
    applied: { icon: Send, color: 'text-purple-400', bgColor: 'bg-purple-500/20', label: 'Applied' },
    interview: { icon: Calendar, color: 'text-cyan-400', bgColor: 'bg-cyan-500/20', label: 'Interview' },
    offer: { icon: Award, color: 'text-emerald-400', bgColor: 'bg-emerald-500/20', label: 'Offer' },
    rejected: { icon: XCircle, color: 'text-red-400', bgColor: 'bg-red-500/20', label: 'Rejected' },
    failed: { icon: XCircle, color: 'text-red-400', bgColor: 'bg-red-500/20', label: 'Failed' },
  }

  const config = statusConfig[job.apply_status || ''] || { 
    icon: Clock, 
    color: 'text-dark-400', 
    bgColor: 'bg-dark-700',
    label: job.apply_status || 'Unknown' 
  }
  const Icon = config.icon

  return (
    <div 
      className="card p-4 card-hover group"
      onClick={onClick}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <h3 className="font-medium text-dark-100 truncate group-hover:text-primary-400 transition-colors">
            {job.title || 'Untitled'}
          </h3>
          <div className="flex items-center gap-2 mt-1 text-sm text-dark-400">
            <Building className="h-4 w-4" />
            {job.company || job.site || 'Unknown'}
          </div>
        </div>
        <div className={clsx('p-2 rounded-lg', config.bgColor, config.color)}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
      
      <div className="mt-4 flex items-center justify-between">
        <span className={clsx(
          'px-2.5 py-1 rounded-lg text-xs font-semibold',
          `status-${job.apply_status}`
        )}>
          {config.label}
        </span>
        <div className="flex items-center gap-2 text-sm text-dark-500">
          {job.applied_at && (
            <span>{new Date(job.applied_at).toLocaleDateString()}</span>
          )}
          <ChevronRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
        </div>
      </div>

      {job.apply_error && (
        <div className="mt-3 p-2 bg-red-500/10 border border-red-500/30 rounded-lg text-xs text-red-400">
          {job.apply_error}
        </div>
      )}
    </div>
  )
}

function StatusSection({ 
  title, 
  jobs, 
  onJobClick,
  emptyMessage 
}: { 
  title: string
  jobs: Job[]
  onJobClick: (job: Job) => void
  emptyMessage: string
}) {
  return (
    <div>
      <h2 className="text-lg font-semibold text-dark-100 mb-4">
        {title} <span className="text-dark-500">({jobs.length})</span>
      </h2>
      {jobs.length > 0 ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {jobs.map((job) => (
            <ApplicationCard 
              key={job.url} 
              job={job} 
              onClick={() => onJobClick(job)} 
            />
          ))}
        </div>
      ) : (
        <div className="card p-8 text-center">
          <p className="text-dark-400">{emptyMessage}</p>
        </div>
      )}
    </div>
  )
}

function Applications() {
  const navigate = useNavigate()

  const { data: appliedData, isLoading: appliedLoading } = useQuery({
    queryKey: ['jobs', 'applied'],
    queryFn: () => getJobs({ status: 'applied', limit: 50 }),
  })

  const { data: interviewData, isLoading: interviewLoading } = useQuery({
    queryKey: ['jobs', 'interview'],
    queryFn: () => getJobs({ status: 'interview', limit: 50 }),
  })

  const { data: offerData, isLoading: offerLoading } = useQuery({
    queryKey: ['jobs', 'offer'],
    queryFn: () => getJobs({ status: 'offer', limit: 50 }),
  })

  const { data: rejectedData, isLoading: rejectedLoading } = useQuery({
    queryKey: ['jobs', 'rejected'],
    queryFn: () => getJobs({ status: 'rejected', limit: 50 }),
  })

  const isLoading = appliedLoading || interviewLoading || offerLoading || rejectedLoading

  const handleJobClick = (job: Job) => {
    navigate(`/jobs/${encodeURIComponent(job.url)}`)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <RefreshCw className="h-8 w-8 text-primary-400 animate-spin mx-auto" />
          <p className="text-dark-400 mt-4">Loading applications...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-dark-100 flex items-center gap-2">
          <Send className="h-6 w-6 text-primary-400" />
          Applications
        </h1>
        <p className="text-dark-400 mt-1">Track your submitted applications and their status</p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card p-4 relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-purple-500/20 to-purple-600/10" />
          <div className="relative">
            <div className="flex items-center gap-2 text-purple-400">
              <Send className="h-5 w-5" />
              <span className="font-medium">Applied</span>
            </div>
            <p className="text-3xl font-bold text-dark-100 mt-2">
              {appliedData?.jobs?.length || 0}
            </p>
          </div>
        </div>
        <div className="card p-4 relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/20 to-cyan-600/10" />
          <div className="relative">
            <div className="flex items-center gap-2 text-cyan-400">
              <Calendar className="h-5 w-5" />
              <span className="font-medium">Interviews</span>
            </div>
            <p className="text-3xl font-bold text-dark-100 mt-2">
              {interviewData?.jobs?.length || 0}
            </p>
          </div>
        </div>
        <div className="card p-4 relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/20 to-emerald-600/10" />
          <div className="relative">
            <div className="flex items-center gap-2 text-emerald-400">
              <Award className="h-5 w-5" />
              <span className="font-medium">Offers</span>
            </div>
            <p className="text-3xl font-bold text-dark-100 mt-2">
              {offerData?.jobs?.length || 0}
            </p>
          </div>
        </div>
        <div className="card p-4 relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-red-500/20 to-red-600/10" />
          <div className="relative">
            <div className="flex items-center gap-2 text-red-400">
              <XCircle className="h-5 w-5" />
              <span className="font-medium">Rejected</span>
            </div>
            <p className="text-3xl font-bold text-dark-100 mt-2">
              {rejectedData?.jobs?.length || 0}
            </p>
          </div>
        </div>
      </div>

      {/* Sections */}
      <StatusSection 
        title="Interviews Scheduled"
        jobs={interviewData?.jobs || []}
        onJobClick={handleJobClick}
        emptyMessage="No interviews scheduled yet"
      />

      <StatusSection 
        title="Offers Received"
        jobs={offerData?.jobs || []}
        onJobClick={handleJobClick}
        emptyMessage="No offers yet - keep applying!"
      />

      <StatusSection 
        title="Applied"
        jobs={appliedData?.jobs || []}
        onJobClick={handleJobClick}
        emptyMessage="No applications submitted yet"
      />

      <StatusSection 
        title="Rejected"
        jobs={rejectedData?.jobs || []}
        onJobClick={handleJobClick}
        emptyMessage="No rejections (that's good!)"
      />
    </div>
  )
}

export default Applications
