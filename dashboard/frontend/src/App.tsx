import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { hasCredentials, setCredentials } from './api/client'
import Navbar from './components/Navbar'
import DashboardPage from './pages/DashboardPage'
import EventsPage from './pages/EventsPage'
import VacanciesPage from './pages/VacanciesPage'
import VacancyDetailPage from './pages/VacancyDetailPage'
import { useState } from 'react'

function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [user, setUser] = useState('')
  const [pass, setPass] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!user || !pass) { setError('Fill in both fields'); return }
    setCredentials(user, pass)
    onLogin()
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
        <button type="submit">Sign in</button>
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
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
