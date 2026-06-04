import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchStats, type Stats } from '../api/client'

const PIPELINE = ['new', 'in_progress', 'applied', 'interview', 'offer']
const PIPELINE_LABELS: Record<string, string> = {
  new:         '🔍 New',
  in_progress: '⚙️ In progress',
  applied:     '📤 Applied',
  interview:   '🎙️ Interview',
  offer:       '🎉 Offer',
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const nav = useNavigate()

  useEffect(() => {
    fetchStats().then(s => { setStats(s); setLoading(false) })
  }, [])

  if (loading) return <div className="loading">Loading…</div>
  if (!stats) return <div className="error">Failed to load stats</div>

  const rejected = (stats.vacancies['rejected'] ?? 0) + (stats.vacancies['rejected_by_company'] ?? 0)
  const total = Object.values(stats.vacancies).reduce((a, b) => a + b, 0)

  return (
    <div className="page">
      <h1>Dashboard</h1>

      {/* Vacancy pipeline */}
      <section className="section">
        <h2>Vacancy pipeline <span className="muted">({total} total)</span></h2>
        <div className="pipeline">
          {PIPELINE.map(status => (
            <div
              key={status}
              className="pipeline-card"
              onClick={() => nav(`/vacancies?status=${status}`)}
            >
              <div className="pipeline-count">
                {/* in_progress визуально включает letter_sent */}
                {status === 'in_progress'
                  ? (stats.vacancies['in_progress'] ?? 0) + (stats.vacancies['letter_sent'] ?? 0)
                  : (stats.vacancies[status] ?? 0)}
              </div>
              <div className="pipeline-label">{PIPELINE_LABELS[status]}</div>
            </div>
          ))}
          <div className="pipeline-card pipeline-card--rejected">
            <div className="pipeline-count">{rejected}</div>
            <div className="pipeline-label">❌ Rejected</div>
          </div>
        </div>
      </section>

      {/* Sources */}
      <section className="section">
        <h2>By platform</h2>
        <div className="stat-grid">
          {Object.entries(stats.platforms).map(([platform, count]) => (
            <div
              key={platform}
              className="stat-card"
              onClick={() => nav(`/vacancies?platform=${platform}`)}
            >
              <div className="stat-count">{count}</div>
              <div className="stat-label">{platform}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Events */}
      <section className="section">
        <h2>Events</h2>
        <div className="stat-grid">
          {Object.entries(stats.events)
            .filter(([, c]) => c > 0)
            .map(([status, count]) => (
              <div key={status} className="stat-card">
                <div className="stat-count">{count}</div>
                <div className="stat-label">{status}</div>
              </div>
            ))}
        </div>
      </section>
    </div>
  )
}
