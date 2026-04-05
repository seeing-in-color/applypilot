import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  Search, 
  Star, 
  Send, 
  CheckCircle, 
  XCircle, 
  Calendar,
  Award,
  AlertCircle,
  RefreshCw,
  TrendingUp,
  Zap
} from 'lucide-react'
import clsx from 'clsx'
import { getStats, getActivity, runDiscover, runScore, runApply } from '../api'
import type { Stats, Activity } from '../types'

function StatCard({ 
  title, 
  value, 
  icon: Icon, 
  color = 'primary',
  onClick,
  subtitle
}: { 
  title: string
  value: number
  icon: React.ComponentType<{ className?: string }>
  color?: 'primary' | 'green' | 'yellow' | 'red' | 'purple' | 'teal' | 'cyan'
  onClick?: () => void
  subtitle?: string
}) {
  const colorClasses = {
    primary: 'from-primary-500/20 to-primary-600/10 text-primary-400 border-primary-500/20',
    green: 'from-emerald-500/20 to-emerald-600/10 text-emerald-400 border-emerald-500/20',
    yellow: 'from-amber-500/20 to-amber-600/10 text-amber-400 border-amber-500/20',
    red: 'from-red-500/20 to-red-600/10 text-red-400 border-red-500/20',
    purple: 'from-purple-500/20 to-purple-600/10 text-purple-400 border-purple-500/20',
    teal: 'from-teal-500/20 to-teal-600/10 text-teal-400 border-teal-500/20',
    cyan: 'from-cyan-500/20 to-cyan-600/10 text-cyan-400 border-cyan-500/20',
  }

  const iconBgClasses = {
    primary: 'bg-primary-500/20 text-primary-400',
    green: 'bg-emerald-500/20 text-emerald-400',
    yellow: 'bg-amber-500/20 text-amber-400',
    red: 'bg-red-500/20 text-red-400',
    purple: 'bg-purple-500/20 text-purple-400',
    teal: 'bg-teal-500/20 text-teal-400',
    cyan: 'bg-cyan-500/20 text-cyan-400',
  }

  return (
    <div 
      className={clsx(
        'card p-5 relative overflow-hidden group',
        onClick && 'card-hover'
      )}
      onClick={onClick}
    >
      {/* Gradient background */}
      <div className={clsx(
        'absolute inset-0 bg-gradient-to-br opacity-50',
        colorClasses[color]
      )} />
      
      <div className="relative flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-dark-400">{title}</p>
          <p className="text-3xl font-bold text-dark-100 mt-1">{value}</p>
          {subtitle && <p className="text-xs text-dark-500 mt-1">{subtitle}</p>}
        </div>
        <div className={clsx('p-3 rounded-xl', iconBgClasses[color])}>
          <Icon className="h-6 w-6" />
        </div>
      </div>
    </div>
  )
}

function ActionButton({
  label,
  icon: Icon,
  onClick,
  loading,
  disabled,
  variant = 'primary'
}: {
  label: string
  icon: React.ComponentType<{ className?: string }>
  onClick: () => void
  loading?: boolean
  disabled?: boolean
  variant?: 'primary' | 'secondary'
}) {
  return (
    <button
      onClick={onClick}
      disabled={loading || disabled}
      className={clsx(
        'flex items-center gap-2 font-medium transition-all duration-300',
        variant === 'primary'
          ? 'btn-primary'
          : 'btn-secondary',
        (loading || disabled) && 'cursor-not-allowed opacity-60'
      )}
    >
      {loading ? (
        <RefreshCw className="h-4 w-4 animate-spin" />
      ) : (
        <Icon className="h-4 w-4" />
      )}
      {label}
    </button>
  )
}

function ActivityItem({ activity }: { activity: Activity }) {
  const iconMap = {
    discovered: Search,
    scored: Star,
    applied: Send,
    status_change: CheckCircle,
  }
  const Icon = iconMap[activity.type] || CheckCircle

  const colorMap = {
    discovered: 'bg-blue-500/20 text-blue-400',
    scored: 'bg-amber-500/20 text-amber-400',
    applied: 'bg-purple-500/20 text-purple-400',
    status_change: 'bg-emerald-500/20 text-emerald-400',
  }

  return (
    <div className="flex items-start gap-3 py-3 animate-fadeIn">
      <div className={clsx('p-2 rounded-lg mt-0.5', colorMap[activity.type])}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-dark-200 truncate">{activity.message}</p>
        <p className="text-xs text-dark-500 mt-0.5">
          {activity.timestamp ? new Date(activity.timestamp).toLocaleString() : 'Unknown time'}
        </p>
      </div>
    </div>
  )
}

function Dashboard() {
  const queryClient = useQueryClient()
  
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: getStats,
    refetchInterval: 10000,
  })

  const { data: activityData } = useQuery({
    queryKey: ['activity'],
    queryFn: () => getActivity(20),
    refetchInterval: 15000,
  })

  const discoverMutation = useMutation({
    mutationFn: runDiscover,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      queryClient.invalidateQueries({ queryKey: ['activity'] })
    },
  })

  const scoreMutation = useMutation({
    mutationFn: () => runScore(7),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      queryClient.invalidateQueries({ queryKey: ['activity'] })
    },
  })

  const applyMutation = useMutation({
    mutationFn: () => runApply({ min_score: 7 }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      queryClient.invalidateQueries({ queryKey: ['activity'] })
    },
  })

  if (statsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <RefreshCw className="h-10 w-10 text-primary-400 animate-spin mx-auto" />
          <p className="text-dark-400 mt-4">Loading pipeline...</p>
        </div>
      </div>
    )
  }

  const s: Stats = stats || {
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
    rejected: 0,
  }

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-dark-100 flex items-center gap-2">
            <TrendingUp className="h-6 w-6 text-primary-400" />
            Dashboard
          </h1>
          <p className="text-dark-400 mt-1">Overview of your job application pipeline</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ActionButton
            label="Discover Jobs"
            icon={Search}
            onClick={() => discoverMutation.mutate()}
            loading={discoverMutation.isPending}
            variant="secondary"
          />
          <ActionButton
            label="Score Jobs"
            icon={Star}
            onClick={() => scoreMutation.mutate()}
            loading={scoreMutation.isPending}
            variant="secondary"
          />
          <ActionButton
            label="Auto-Apply"
            icon={Zap}
            onClick={() => applyMutation.mutate()}
            loading={applyMutation.isPending}
          />
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Total Discovered" value={s.total_discovered} icon={Search} color="primary" />
        <StatCard title="Scored" value={s.total_scored} icon={Star} color="yellow" />
        <StatCard title="High Fit (7+)" value={s.high_fit} icon={CheckCircle} color="green" />
        <StatCard title="Applied" value={s.applied} icon={Send} color="purple" />
      </div>

      {/* Secondary Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <StatCard title="Mid Fit (5-6)" value={s.mid_fit} icon={Star} color="yellow" />
        <StatCard title="Low Fit (<5)" value={s.low_fit} icon={XCircle} color="red" />
        <StatCard title="Interviews" value={s.interviews} icon={Calendar} color="cyan" />
        <StatCard title="Offers" value={s.offers} icon={Award} color="green" />
        <StatCard title="Rejected" value={s.rejected} icon={XCircle} color="red" />
        <StatCard title="Needs Input" value={s.pending_input} icon={AlertCircle} color="yellow" />
      </div>

      {/* Activity Feed */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold text-dark-100 mb-4 flex items-center gap-2">
          <Zap className="h-5 w-5 text-amber-400" />
          Recent Activity
        </h2>
        <div className="divide-y divide-dark-800/50">
          {activityData?.activities?.length ? (
            activityData.activities.map((activity, i) => (
              <ActivityItem key={`${activity.job_url}-${i}`} activity={activity} />
            ))
          ) : (
            <div className="text-center py-12">
              <Search className="h-12 w-12 text-dark-600 mx-auto mb-4" />
              <p className="text-dark-400">No recent activity</p>
              <p className="text-dark-500 text-sm mt-1">Click "Discover Jobs" to get started!</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default Dashboard
