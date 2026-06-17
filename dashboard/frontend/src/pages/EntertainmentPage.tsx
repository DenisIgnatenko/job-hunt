import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchEvents, updateEventStatus, type Event } from '../api/client'
import StatusBadge from '../components/StatusBadge'

const STATUSES = ['all', 'new', 'interested', 'attending', 'attended', 'skipped']

// Эмодзи для типов развлекательных событий
const TYPE_EMOJI: Record<string, string> = {
  concert:  '🎵',
  festival: '🎪',
  theater:  '🎭',
  outdoor:  '🌿',
  sport:    '⚽',
  market:   '🛍️',
  other:    '🎠',
  // fallback для professional типов если вдруг попадут
  meetup:     '👥',
  conference: '🎤',
  workshop:   '🛠️',
  hackathon:  '💻',
}

const STATUS_ACTIONS: { value: string; label: string }[] = [
  { value: 'new',       label: '🆕 New' },
  { value: 'interested', label: '⭐ Interested' },
  { value: 'attending', label: '🎟 Attending' },
  { value: 'attended',  label: '✅ Attended' },
  { value: 'skipped',   label: '⏭ Skip' },
]

export default function EntertainmentPage() {
  const [events, setEvents] = useState<Event[]>([])
  const [loading, setLoading] = useState(true)
  const [updatingId, setUpdatingId] = useState<number | null>(null)
  const [params, setParams] = useSearchParams()
  const status = params.get('status') ?? 'all'

  useEffect(() => {
    setLoading(true)
    fetchEvents({ status: status === 'all' ? undefined : status, category: 'entertainment' })
      .then(data => { setEvents(data); setLoading(false) })
  }, [status])

  const handleStatusChange = async (eventId: number, nextStatus: string) => {
    setUpdatingId(eventId)
    try {
      await updateEventStatus(eventId, nextStatus)
      setEvents(prev => prev.map(e => e.id === eventId ? { ...e, status: nextStatus } : e))
    } finally {
      setUpdatingId(null)
    }
  }

  return (
    <div className="page">
      <h1>🎠 Entertainment</h1>
      <p className="page-subtitle">
        Concerts, festivals, outdoor events and cultural happenings in Aarhus and Jutland
      </p>

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
      </div>

      {loading && <div className="loading">Loading…</div>}
      {!loading && events.length === 0 && (
        <div className="empty">
          No entertainment events found. The scout runs daily at 09:30 CEST.
        </div>
      )}

      {!loading && (
        <div className="events-grid">
          {events.map(ev => (
            <div key={ev.id} className="event-card">
              <div className="event-card-header">
                <span className="event-type-emoji">{TYPE_EMOJI[ev.event_type] ?? '🎠'}</span>
                <StatusBadge value={ev.status} />
                <span className="event-score">{ev.score}/10</span>
              </div>
              <a href={ev.url} target="_blank" rel="noreferrer" className="event-title">
                {ev.title}
              </a>
              {ev.organizer && <div className="event-meta">👤 {ev.organizer}</div>}
              {ev.location && <div className="event-meta">📌 {ev.location}</div>}
              {ev.event_date && <div className="event-meta">🗓 {ev.event_date}</div>}
              {ev.description && <div className="event-desc">{ev.description}</div>}

              <div className="event-status-actions">
                {STATUS_ACTIONS.map(action => (
                  <button
                    key={action.value}
                    className={`event-status-btn ${ev.status === action.value ? 'event-status-btn--active' : ''}`}
                    disabled={updatingId === ev.id || ev.status === action.value}
                    onClick={() => handleStatusChange(ev.id, action.value)}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
