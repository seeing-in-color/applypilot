import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  User, 
  Briefcase, 
  Mail, 
  FileText, 
  Settings as SettingsIcon,
  Save,
  RefreshCw,
  Upload,
  CheckCircle,
  AlertCircle,
  Link as LinkIcon,
  Sparkles
} from 'lucide-react'
import clsx from 'clsx'
import { 
  getProfile, 
  updateProfile, 
  getSettings, 
  updateSettings, 
  uploadResume,
  getEmailStatus,
  syncEmails
} from '../api'
import type { Profile, Settings as SettingsType } from '../types'

function Section({ 
  title, 
  icon: Icon, 
  children 
}: { 
  title: string
  icon: React.ComponentType<{ className?: string }>
  children: React.ReactNode 
}) {
  return (
    <div className="card p-6">
      <h2 className="text-lg font-semibold text-dark-100 mb-4 flex items-center gap-2">
        <div className="p-2 rounded-lg bg-primary-500/20">
          <Icon className="h-5 w-5 text-primary-400" />
        </div>
        {title}
      </h2>
      {children}
    </div>
  )
}

function FormField({ 
  label, 
  value, 
  onChange, 
  type = 'text',
  placeholder 
}: { 
  label: string
  value: string
  onChange: (value: string) => void
  type?: string
  placeholder?: string
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-dark-300 mb-1.5">
        {label}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="input w-full"
      />
    </div>
  )
}

function Settings() {
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // Profile state
  const { data: profileData } = useQuery({
    queryKey: ['profile'],
    queryFn: getProfile,
  })

  const [profile, setProfile] = useState<Profile>({})

  // Settings state
  const { data: settingsData } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
  })

  const [settings, setSettings] = useState<SettingsType>({
    min_score_threshold: 7,
    auto_apply_enabled: false,
    email_monitoring_enabled: false,
    llm_delay: 4.5,
  })

  // Email status
  const { data: emailStatus } = useQuery({
    queryKey: ['email-status'],
    queryFn: getEmailStatus,
  })

  // Initialize state from fetched data
  useState(() => {
    if (profileData?.profile) {
      setProfile(profileData.profile)
    }
  })

  useState(() => {
    if (settingsData) {
      setSettings(settingsData)
    }
  })

  // Mutations
  const profileMutation = useMutation({
    mutationFn: updateProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      setMessage({ type: 'success', text: 'Profile saved!' })
    },
    onError: (error) => {
      setMessage({ type: 'error', text: error.message })
    },
  })

  const settingsMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setMessage({ type: 'success', text: 'Settings saved!' })
    },
    onError: (error) => {
      setMessage({ type: 'error', text: error.message })
    },
  })

  const resumeMutation = useMutation({
    mutationFn: uploadResume,
    onSuccess: () => {
      setMessage({ type: 'success', text: 'Resume uploaded!' })
    },
    onError: (error) => {
      setMessage({ type: 'error', text: error.message })
    },
  })

  const emailSyncMutation = useMutation({
    mutationFn: () => syncEmails(7),
    onSuccess: () => {
      setMessage({ type: 'success', text: 'Email sync started!' })
    },
  })

  const handleSaveProfile = async () => {
    setSaving(true)
    await profileMutation.mutateAsync(profile)
    setSaving(false)
  }

  const handleSaveSettings = async () => {
    setSaving(true)
    await settingsMutation.mutateAsync(settings)
    setSaving(false)
  }

  const handleResumeUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      resumeMutation.mutate(file)
    }
  }

  const updatePersonal = (key: string, value: string) => {
    setProfile(p => ({
      ...p,
      personal: { ...p.personal, [key]: value }
    }))
  }

  const updateWorkAuth = (key: string, value: string) => {
    setProfile(p => ({
      ...p,
      work_authorization: { ...p.work_authorization, [key]: value }
    }))
  }

  const updateExperience = (key: string, value: string | number) => {
    setProfile(p => ({
      ...p,
      experience: { ...p.experience, [key]: value }
    }))
  }

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-dark-100 flex items-center gap-2">
            <SettingsIcon className="h-6 w-6 text-primary-400" />
            Settings
          </h1>
          <p className="text-dark-400 mt-1">Manage your profile and preferences</p>
        </div>
      </div>

      {/* Message */}
      {message && (
        <div className={clsx(
          'flex items-center gap-2 p-4 rounded-lg border',
          message.type === 'success' 
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' 
            : 'bg-red-500/10 border-red-500/30 text-red-400'
        )}>
          {message.type === 'success' ? (
            <CheckCircle className="h-5 w-5" />
          ) : (
            <AlertCircle className="h-5 w-5" />
          )}
          {message.text}
          <button 
            onClick={() => setMessage(null)}
            className="ml-auto text-sm underline hover:no-underline"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Personal Information */}
        <Section title="Personal Information" icon={User}>
          <div className="grid sm:grid-cols-2 gap-4">
            <FormField
              label="First Name"
              value={profile.personal?.first_name || ''}
              onChange={(v) => updatePersonal('first_name', v)}
            />
            <FormField
              label="Last Name"
              value={profile.personal?.last_name || ''}
              onChange={(v) => updatePersonal('last_name', v)}
            />
            <FormField
              label="Email"
              type="email"
              value={profile.personal?.email || ''}
              onChange={(v) => updatePersonal('email', v)}
            />
            <FormField
              label="Phone"
              type="tel"
              value={profile.personal?.phone || ''}
              onChange={(v) => updatePersonal('phone', v)}
            />
            <FormField
              label="City"
              value={profile.personal?.city || ''}
              onChange={(v) => updatePersonal('city', v)}
            />
            <FormField
              label="Country"
              value={profile.personal?.country || ''}
              onChange={(v) => updatePersonal('country', v)}
            />
          </div>
          <div className="mt-4">
            <button
              onClick={handleSaveProfile}
              disabled={saving}
              className="btn-primary flex items-center gap-2"
            >
              {saving ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Save Profile
            </button>
          </div>
        </Section>

        {/* Links */}
        <Section title="Online Profiles" icon={LinkIcon}>
          <div className="space-y-4">
            <FormField
              label="LinkedIn URL"
              value={profile.personal?.linkedin_url || ''}
              onChange={(v) => updatePersonal('linkedin_url', v)}
              placeholder="https://linkedin.com/in/yourprofile"
            />
            <FormField
              label="GitHub URL"
              value={profile.personal?.github_url || ''}
              onChange={(v) => updatePersonal('github_url', v)}
              placeholder="https://github.com/yourusername"
            />
            <FormField
              label="Portfolio URL"
              value={profile.personal?.portfolio_url || ''}
              onChange={(v) => updatePersonal('portfolio_url', v)}
              placeholder="https://yourportfolio.com"
            />
          </div>
        </Section>

        {/* Work Authorization */}
        <Section title="Work Authorization" icon={Briefcase}>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-dark-300 mb-1.5">
                Legally authorized to work in the US?
              </label>
              <select
                value={profile.work_authorization?.legally_authorized_to_work || ''}
                onChange={(e) => updateWorkAuth('legally_authorized_to_work', e.target.value)}
                className="input w-full"
              >
                <option value="">Select...</option>
                <option value="Yes">Yes</option>
                <option value="No">No</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-dark-300 mb-1.5">
                Require visa sponsorship?
              </label>
              <select
                value={profile.work_authorization?.require_sponsorship || ''}
                onChange={(e) => updateWorkAuth('require_sponsorship', e.target.value)}
                className="input w-full"
              >
                <option value="">Select...</option>
                <option value="Yes">Yes</option>
                <option value="No">No</option>
              </select>
            </div>
          </div>
        </Section>

        {/* Experience */}
        <Section title="Experience" icon={Briefcase}>
          <div className="space-y-4">
            <FormField
              label="Years of Experience"
              type="number"
              value={String(profile.experience?.years || '')}
              onChange={(v) => updateExperience('years', parseInt(v) || 0)}
            />
            <FormField
              label="Current Job Title"
              value={profile.experience?.current_title || ''}
              onChange={(v) => updateExperience('current_title', v)}
            />
            <FormField
              label="Current Company"
              value={profile.experience?.current_company || ''}
              onChange={(v) => updateExperience('current_company', v)}
            />
          </div>
        </Section>

        {/* Resume */}
        <Section title="Resume" icon={FileText}>
          <div className="space-y-4">
            <div className="border-2 border-dashed border-dark-700 rounded-xl p-6 text-center hover:border-primary-500/50 transition-colors">
              <Upload className="h-10 w-10 text-dark-500 mx-auto mb-3" />
              <p className="text-sm text-dark-400 mb-3">
                Upload your resume (PDF, TXT, or DOCX)
              </p>
              <input
                type="file"
                accept=".pdf,.txt,.docx"
                onChange={handleResumeUpload}
                className="hidden"
                id="resume-upload"
              />
              <label
                htmlFor="resume-upload"
                className="btn-primary inline-flex items-center gap-2 cursor-pointer"
              >
                {resumeMutation.isPending ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4" />
                )}
                Choose File
              </label>
            </div>
          </div>
        </Section>

        {/* Email Monitoring */}
        <Section title="Email Monitoring" icon={Mail}>
          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 bg-dark-800/50 rounded-xl border border-dark-700">
              <div>
                <p className="font-medium text-dark-200">Gmail Connection</p>
                <p className="text-sm text-dark-400">
                  {emailStatus?.authenticated 
                    ? 'Connected - monitoring for job responses'
                    : 'Not connected'}
                </p>
              </div>
              <span className={clsx(
                'px-3 py-1.5 rounded-lg text-sm font-medium',
                emailStatus?.authenticated 
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                  : 'bg-dark-700 text-dark-400 border border-dark-600'
              )}>
                {emailStatus?.authenticated ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            {emailStatus?.authenticated && (
              <button
                onClick={() => emailSyncMutation.mutate()}
                disabled={emailSyncMutation.isPending}
                className="btn-secondary flex items-center gap-2"
              >
                {emailSyncMutation.isPending ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                Sync Emails Now
              </button>
            )}
            {!emailStatus?.authenticated && emailStatus?.auth_url && (
              <a
                href={emailStatus.auth_url}
                className="btn-primary inline-flex items-center gap-2"
              >
                <Mail className="h-4 w-4" />
                Connect Gmail
              </a>
            )}
          </div>
        </Section>

        {/* Auto-Apply Settings */}
        <Section title="Auto-Apply Settings" icon={Sparkles}>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-dark-300 mb-1.5">
                Minimum Score Threshold
              </label>
              <select
                value={settings.min_score_threshold}
                onChange={(e) => setSettings(s => ({ ...s, min_score_threshold: parseInt(e.target.value) }))}
                className="input w-full"
              >
                <option value="9">9+ only (very selective)</option>
                <option value="7">7+ (recommended)</option>
                <option value="5">5+ (more applications)</option>
              </select>
              <p className="text-xs text-dark-500 mt-1.5">
                Only auto-apply to jobs with this score or higher
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-dark-300 mb-1.5">
                LLM Delay (seconds)
              </label>
              <input
                type="number"
                step="0.5"
                min="0"
                value={settings.llm_delay}
                onChange={(e) => setSettings(s => ({ ...s, llm_delay: parseFloat(e.target.value) }))}
                className="input w-full"
              />
              <p className="text-xs text-dark-500 mt-1.5">
                Delay between AI API calls (for rate limiting)
              </p>
            </div>
            <button
              onClick={handleSaveSettings}
              disabled={saving}
              className="btn-primary flex items-center gap-2"
            >
              {saving ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Save Settings
            </button>
          </div>
        </Section>
      </div>
    </div>
  )
}

export default Settings
