import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchVacancy, type VacancyDetail } from '../api/client'
import StatusBadge from '../components/StatusBadge'

export default function VacancyDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [vacancy, setVacancy] = useState<VacancyDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const nav = useNavigate()

  useEffect(() => {
    if (!id) return
    fetchVacancy(Number(id)).then(v => { setVacancy(v); setLoading(false) })
  }, [id])

  if (loading) return <div className="loading">Loading…</div>
  if (!vacancy) return <div className="error">Vacancy not found</div>

  const letter = vacancy.cover_letters[0] ?? null

  return (
    <div className="page page--detail">
      <button className="back-btn" onClick={() => nav(-1)}>← Back</button>

      <div className="detail-header">
        <h1>{vacancy.title}</h1>
        <div className="detail-meta">
          {vacancy.company && <span>🏢 {vacancy.company}</span>}
          {vacancy.location && <span>📌 {vacancy.location}</span>}
          <StatusBadge value={vacancy.platform} type="platform" />
          <StatusBadge value={vacancy.work_format} type="format" />
          <StatusBadge value={vacancy.status} />
        </div>
        <a href={vacancy.url} target="_blank" rel="noreferrer" className="apply-link">
          Open job posting ↗
        </a>
      </div>

      {vacancy.description && (
        <section className="section">
          <h2>Job description</h2>
          <pre className="description">{vacancy.description}</pre>
        </section>
      )}

      {letter && (
        <section className="section">
          <h2>Cover letter <span className="muted">v{letter.version}</span></h2>
          <pre className="cover-letter">{letter.body}</pre>
        </section>
      )}

      {!letter && (
        <div className="empty">No cover letter generated yet</div>
      )}
    </div>
  )
}
