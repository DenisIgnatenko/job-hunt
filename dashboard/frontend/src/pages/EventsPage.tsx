import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchEvents, type Event } from '../api/client'
import StatusBadge from '../components/StatusBadge'

const STATUSES = ['all', 'new', 'interested', 'attending', 'attended', 'skipped']
const TYPE_EMOJI: Record<string, string> = {
  meetup: '👥', conference: '🎤', workshop: '🛠️', hackathon: '💻', other: '📅',
}

export default function EventsPage() {
  const [events, setEvents] = useState<Event[]>([])
  const [loading, setLoading] = useState(true)
  const [params, setParams] = useSearchParams()
  const status = params.get('status') ?? 'all'

  useEffect(() => {
    setLoading(true)
    fetchEvents({ status: status === 'all' ? undefined : status })
      .then(data => { setEvents(data); setLoading(false) })
  }, [status])

  return (
    <div className="page">
      <h1>Events</h1>

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
      {!loading && events.length === 0 && <div className="empty">No events found</div>}

      {!loading && (
        <div className="events-grid">
          {events.map(ev => (
            <a
              key={ev.id}
              href={ev.url}
              target="_blank"
              rel="noreferrer"
              className="event-card"
            >
              <div className="event-card-header">
                <span className="event-type-emoji">{TYPE_EMOJI[ev.event_type] ?? '📅'}</span>
                <StatusBadge value={ev.status} />
                <span className="event-score">{ev.score}/10</span>
              </div>
              <div className="event-title">{ev.title}</div>
              {ev.organizer && <div className="event-meta">👤 {ev.organizer}</div>}
              {ev.location && <div className="event-meta">📌 {ev.location}</div>}
              {ev.event_date && <div className="event-meta">🗓 {ev.event_date}</div>}
              {ev.description && <div className="event-desc">{ev.description}</div>}
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
