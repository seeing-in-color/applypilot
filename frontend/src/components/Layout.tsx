import { Outlet, NavLink } from 'react-router-dom'
import { 
  LayoutDashboard, 
  Briefcase, 
  Send, 
  Settings, 
  AlertCircle,
  Rocket,
  Sparkles
} from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/jobs', icon: Briefcase, label: 'Jobs' },
  { to: '/applications', icon: Send, label: 'Applications' },
  { to: '/needs-input', icon: AlertCircle, label: 'Needs Input' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

function Layout() {
  return (
    <div className="min-h-screen bg-dark-950">
      {/* Ambient glow effect */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-primary-500/10 rounded-full blur-3xl" />
        <div className="absolute top-1/2 -left-40 w-80 h-80 bg-purple-500/10 rounded-full blur-3xl" />
      </div>

      {/* Header */}
      <header className="glass sticky top-0 z-50 border-t-0 border-x-0">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="relative">
                <Rocket className="h-8 w-8 text-primary-400" />
                <Sparkles className="absolute -top-1 -right-1 h-3 w-3 text-amber-400 animate-pulse" />
              </div>
              <span className="text-xl font-bold text-gradient">ApplyPilot</span>
            </div>
            <nav className="hidden md:flex items-center gap-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    clsx(
                      'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200',
                      isActive
                        ? 'bg-primary-500/20 text-primary-400 shadow-lg shadow-primary-500/10'
                        : 'text-dark-400 hover:text-dark-200 hover:bg-dark-800/50'
                    )
                  }
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
        </div>
      </header>

      {/* Mobile nav */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 glass border-b-0 border-x-0 z-50">
        <div className="flex justify-around py-2 px-2">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex flex-col items-center gap-1 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-200',
                  isActive 
                    ? 'text-primary-400 bg-primary-500/20' 
                    : 'text-dark-500 hover:text-dark-300'
                )
              }
            >
              <item.icon className="h-5 w-5" />
              {item.label}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Main content */}
      <main className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-24 md:pb-8">
        <Outlet />
      </main>
    </div>
  )
}

export default Layout
