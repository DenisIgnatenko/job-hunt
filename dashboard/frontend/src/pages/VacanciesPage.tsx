import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { fetchVacancies, type Vacancy } from '../api/client'
import StatusBadge from '../components/StatusBadge'

const STATUSES = ['all', 'new', 'in_progress', 'letter_sent', 'applied', 'interview', 'offer', 'rejected']

export default function VacanciesPage() {
  const [vacancies, setVacancies] = useState<Vacancy[]>([])
  const [loading, setLoading] = useState(true)
  const [params, setParams] = useSearchParams()
  const nav = useNavigate()

  const status = params.get('status') ?? 'all'
  const platform = params.get('platform') ?? undefined

  useEffect(() => {
    setLoading(true)
    fetchVacancies({
      status: status === 'all' ? undefined : status,
      platform,
    }).then(data => { setVacancies(data); setLoading(false) })
  }, [status, platform])

  return (
    <div className="page">
      <h1>Vacancies {platform && <span className="muted">— {platform}</span>}</h1>

      {/* Status filter */}
      <div className="filter-chips">
        {STATUSES.map(s => (
          <button
            key={s}
            className={`chip ${status === s ? 'chip--active' : ''}`}
            onClick={() => {
              const p = new URLSearchParams(params)
              if (s === 'all') p.delete('status')
              else p.set('status', s)
              setParams(p)
            }}
          >
            {s}
          </button>
        ))}
        {platform && (
          <button className="chip chip--clear" onClick={() => {
            const p = new URLSearchParams(params)
            p.delete('platform')
            setParams(p)
          }}>
            ✕ {platform}
          </button>
        )}
      </div>

      {loading && <div className="loading">Loading…</div>}
      {!loading && vacancies.length === 0 && (
        <div className="empty">No vacancies found</div>
      )}

      {!loading && vacancies.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Company</th>
              <th>Location</th>
              <th>Platform</th>
              <th>Format</th>
              <th>Status</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            {vacancies.map(v => (
              <tr key={v.id} className="table-row" onClick={() => nav(`/vacancies/${v.id}`)}>
                <td className="title-cell">{v.title}</td>
                <td>{v.company ?? '—'}</td>
                <td>{v.location ?? '—'}</td>
                <td><StatusBadge value={v.platform} type="platform" /></td>
                <td><StatusBadge value={v.work_format} type="format" /></td>
                <td><StatusBadge value={v.status} /></td>
                <td className="date-cell">{v.fetched_at?.slice(0, 10) ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
