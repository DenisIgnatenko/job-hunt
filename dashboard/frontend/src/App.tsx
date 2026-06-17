import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { hasCredentials, setCredentials, verifyCredentials } from './api/client'
import Navbar from './components/Navbar'
import DashboardPage from './pages/DashboardPage'
import EntertainmentPage from './pages/EntertainmentPage'
import EventsPage from './pages/EventsPage'
import VacanciesPage from './pages/VacanciesPage'
import VacancyDetailPage from './pages/VacancyDetailPage'
import { useState } from 'react'

function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [user, setUser] = useState('')
  const [pass, setPass] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!user || !pass) { setError('Fill in both fields'); return }
    setLoading(true)
    setError('')
    try {
      const ok = await verifyCredentials(user, pass)
      if (ok) {
        setCredentials(user, pass)
        onLogin()
      } else {
        setError('Invalid username or password')
      }
    } catch {
      setError('Cannot connect to server')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-form" onSubmit={handleSubmit}>
        <h1>Job Hunt</h1>
        <p className="login-sub">Dashboard</p>
        {error && <div className="error-msg">{error}</div>}
        <input
          type="text" placeholder="Username" value={user} autoFocus
          onChange={e => setUser(e.target.value)}
        />
        <input
          type="password" placeholder="Password" value={pass}
          onChange={e => setPass(e.target.value)}
        />
        <button type="submit" disabled={loading}>
          {loading ? 'Checking…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}

export default function App() {
  const [authed, setAuthed] = useState(hasCredentials())

  if (!authed) {
    return <LoginPage onLogin={() => setAuthed(true)} />
  }

  return (
    <BrowserRouter>
      <div className="app">
        <Navbar />
        <main className="content">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/vacancies" element={<VacanciesPage />} />
            <Route path="/vacancies/:id" element={<VacancyDetailPage />} />
            <Route path="/events" element={<EventsPage />} />
            <Route path="/entertainment" element={<EntertainmentPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
