import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { fetchVacancies, updateVacancyStatus, type Vacancy } from '../api/client'
import StatusBadge from '../components/StatusBadge'

const STATUSES = ['all', 'new', 'in_progress', 'applied', 'interview', 'offer', 'rejected']

// Цвет бейджа Score в зависимости от значения (SRP: вся логика цвета здесь)
function scoreBadgeClass(score: number): string {
  if (score >= 8) return 'badge-green'
  if (score >= 5) return 'badge-yellow'
  return 'badge-red'
}

export default function VacanciesPage() {
  const [vacancies, setVacancies] = useState<Vacancy[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [params, setParams] = useSearchParams()
  const [rejecting, setRejecting] = useState<number | null>(null)
  const nav = useNavigate()
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const status = params.get('status') ?? 'all'
  const platform = params.get('platform') ?? undefined

  // Загружаем вакансии: при поиске — по q, иначе по фильтрам
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setLoading(true)
      fetchVacancies(
        query.trim()
          ? { q: query.trim() }
          : { status: status === 'all' ? undefined : status, platform }
      ).then(data => { setVacancies(data); setLoading(false) })
    }, query ? 250 : 0)
  }, [query, status, platform])

  // Reject прямо из списка — без перехода на детальную страницу.
  // e.stopPropagation() блокирует всплытие клика к <tr onClick={nav}>.
  const handleReject = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation()
    setRejecting(id)
    try {
      await updateVacancyStatus(id, 'rejected')
      // Обновляем статус в локальном стейте — перезагрузка страницы не нужна
      setVacancies(prev =>
        prev.map(v => v.id === id ? { ...v, status: 'rejected' } : v)
      )
    } finally {
      setRejecting(null)
    }
  }

  return (
    <div className="page">
      <h1>Vacancies {platform && !query && <span className="muted">— {platform}</span>}</h1>

      {/* Поиск */}
      <div className="search-wrap">
        <input
          className="search-input"
          type="text"
          placeholder="Search by title, company, location…"
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
        {query && (
          <button className="search-clear" onClick={() => setQuery('')}>✕</button>
        )}
      </div>

      {/* Фильтры по статусу — скрываем при поиске */}
      {!query && (
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
      )}

      {loading && <div className="loading">Loading…</div>}

      {!loading && vacancies.length === 0 && (
        <div className="empty">
          {query ? `No results for "${query}"` : 'No vacancies found'}
        </div>
      )}

      {!loading && vacancies.length > 0 && (
        <>
          {query && (
            <div className="search-count">{vacancies.length} result{vacancies.length !== 1 ? 's' : ''} for "{query}"</div>
          )}
          <table className="table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Company</th>
                <th>Location</th>
                <th>Platform</th>
                <th>Format</th>
                <th>Score</th>
                <th>Status</th>
                <th>Posted</th>
                <th></th>
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
                  <td>
                    {v.score != null
                      ? <span className={`badge ${scoreBadgeClass(v.score)}`}>{v.score}/10</span>
                      : <span className="muted">—</span>
                    }
                  </td>
                  <td><StatusBadge value={v.status} /></td>
                  <td className="date-cell">{daysAgo(v.posted_at ?? v.fetched_at)}</td>
                  <td className="actions-cell" onClick={e => e.stopPropagation()}>
                    {!['rejected', 'rejected_by_company'].includes(v.status) && (
                      <button
                        className="reject-btn"
                        onClick={e => handleReject(e, v.id)}
                        disabled={rejecting === v.id}
                        title="Reject this vacancy"
                      >
                        {rejecting === v.id ? '…' : '✕ Reject'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}

function daysAgo(dateStr: string | null): string {
  if (!dateStr) return '—'
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 86_400_000)
  if (diff < 0)  return '—'
  if (diff === 0) return 'today'
  if (diff === 1) return 'yesterday'
  if (diff < 7)  return `${diff}d ago`
  if (diff < 30) return `${Math.floor(diff / 7)}w ago`
  if (diff < 365) return `${Math.floor(diff / 30)}mo ago`
  return `${Math.floor(diff / 365)}y ago`
}
