import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Jobs from './pages/Jobs'
import JobDetail from './pages/JobDetail'
import Applications from './pages/Applications'
import Settings from './pages/Settings'
import NeedsInput from './pages/NeedsInput'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="jobs" element={<Jobs />} />
        <Route path="jobs/:jobUrl" element={<JobDetail />} />
        <Route path="applications" element={<Applications />} />
        <Route path="needs-input" element={<NeedsInput />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}

export default App
