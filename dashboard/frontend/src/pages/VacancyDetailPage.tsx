import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  fetchCompanyReport,
  fetchMatchAnalysis,
  fetchVacancy,
  generateLetter,
  updateVacancyStatus,
  type VacancyDetail,
} from '../api/client'
import StatusBadge from '../components/StatusBadge'

// Доступные переходы из каждого статуса
const _IN_PROGRESS_ACTIONS = [
  { label: '📤 Mark applied', next: 'applied',  style: 'btn-primary' },
  { label: '❌ Reject',       next: 'rejected', style: 'btn-danger' },
]

const STATUS_ACTIONS: Record<string, { label: string; next: string; style: string }[]> = {
  new: [
    { label: '⚙️ Take to work', next: 'in_progress', style: 'btn-primary' },
    { label: '❌ Skip',          next: 'rejected',    style: 'btn-danger' },
  ],
  in_progress:  _IN_PROGRESS_ACTIONS,
  letter_sent:  _IN_PROGRESS_ACTIONS,  // внутренний статус, внешне = in_progress
  applied: [
    { label: '🎙️ Interview',     next: 'interview',   style: 'btn-primary' },
    { label: '💔 Rejected by company', next: 'rejected_by_company', style: 'btn-danger' },
  ],
  interview: [
    { label: '🎉 Offer!',        next: 'offer',       style: 'btn-success' },
    { label: '💔 Rejected by company', next: 'rejected_by_company', style: 'btn-danger' },
  ],
  offer: [],
  rejected: [
    { label: '↩️ Restore to new', next: 'new',        style: 'btn-secondary' },
  ],
  rejected_by_company: [
    { label: '↩️ Restore to new', next: 'new',        style: 'btn-secondary' },
  ],
}

export default function VacancyDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [vacancy, setVacancy] = useState<VacancyDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [companyReport, setCompanyReport] = useState<string | null>(null)
  const [loadingReport, setLoadingReport] = useState(false)
  const [matchAnalysis, setMatchAnalysis] = useState<string | null>(null)
  const [loadingMatch, setLoadingMatch] = useState(false)
  const nav = useNavigate()

  useEffect(() => {
    if (!id) return
    fetchVacancy(Number(id)).then(v => {
      setVacancy(v)
      // Загружаем кэшированные отчёты из БД — не нужно генерировать заново
      setCompanyReport(v.company_report)
      setMatchAnalysis(v.match_analysis)
      setLoading(false)
    })
  }, [id])

  const handleAction = async (nextStatus: string) => {
    if (!vacancy?.id) return

    // "Take to work" — запускаем AI pipeline (15-30 сек)
    if (nextStatus === 'in_progress') {
      setGenerating(true)
      try {
        await generateLetter(vacancy.id)
        const updated = await fetchVacancy(vacancy.id)
        setVacancy(updated)
      } finally {
        setGenerating(false)
      }
      return
    }

    // Остальные статусы — просто меняем
    setUpdating(true)
    await updateVacancyStatus(vacancy.id, nextStatus)
    await fetchVacancy(vacancy.id).then(setVacancy)
    setUpdating(false)
  }

  const handleCompanyReport = async () => {
    if (!vacancy?.id) return
    setLoadingReport(true)
    try {
      const { report } = await fetchCompanyReport(vacancy.id)
      setCompanyReport(report)
    } catch {
      setCompanyReport('⚠️ Failed to generate report. Try again.')
    } finally {
      setLoadingReport(false)
    }
  }

  const handleMatchAnalysis = async () => {
    if (!vacancy?.id) return
    setLoadingMatch(true)
    try {
      const { analysis } = await fetchMatchAnalysis(vacancy.id)
      setMatchAnalysis(analysis)
    } catch {
      setMatchAnalysis('⚠️ Failed to generate analysis. Try again.')
    } finally {
      setLoadingMatch(false)
    }
  }

  if (loading) return <div className="loading">Loading…</div>
  if (!vacancy) return <div className="error">Vacancy not found</div>

  const actions = STATUS_ACTIONS[vacancy.status] ?? []
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

      {/* Action buttons */}
      {actions.length > 0 && (
        <div className="action-bar">
          {actions.map(a => (
            <button
              key={a.next}
              className={`btn ${a.style}`}
              disabled={updating || generating}
              onClick={() => handleAction(a.next)}
            >
              {generating && a.next === 'in_progress'
                ? '⏳ Generating letter…'
                : a.label}
            </button>
          ))}
          {generating && (
            <span className="generating-hint">
              Researching company + writing cover letter — ~20 sec
            </span>
          )}
        </div>
      )}

      {/* Manual status override — откат или ручная корректировка */}
      <StatusOverride
        current={vacancy.status}
        disabled={updating || generating}
        onChange={async (s) => {
          setUpdating(true)
          await updateVacancyStatus(vacancy.id, s)
          await fetchVacancy(vacancy.id).then(setVacancy)
          setUpdating(false)
        }}
      />

      {/* Company Report */}
      <section className="section">
        <div className="ai-section-header">
          <h2>🏢 Company report</h2>
          {!companyReport && (
            <button
              className="btn btn-secondary"
              disabled={loadingReport}
              onClick={handleCompanyReport}
            >
              {loadingReport ? '⏳ Researching…' : '✨ Generate report'}
            </button>
          )}
        </div>
        {companyReport && (
          <>
            <div className="ai-report" dangerouslySetInnerHTML={{ __html: mdToHtml(companyReport) }} />
            <button className="override-toggle" onClick={() => { setCompanyReport(null) }}>
              🔄 Regenerate
            </button>
          </>
        )}
      </section>

      {/* Match Analysis */}
      <section className="section">
        <div className="ai-section-header">
          <h2>🎯 Match analysis</h2>
          {!matchAnalysis && (
            <button
              className="btn btn-secondary"
              disabled={loadingMatch}
              onClick={handleMatchAnalysis}
            >
              {loadingMatch ? '⏳ Analysing…' : '✨ How do I fit?'}
            </button>
          )}
        </div>
        {matchAnalysis && (
          <>
            <div className="ai-report" dangerouslySetInnerHTML={{ __html: mdToHtml(matchAnalysis) }} />
            <button className="override-toggle" onClick={() => { setMatchAnalysis(null) }}>
              🔄 Regenerate
            </button>
          </>
        )}
      </section>

      {vacancy.description && (
        <section className="section">
          <h2>Job description</h2>
          {/* dangerouslySetInnerHTML — описание с The Hub/LinkedIn приходит как HTML */}
          <div
            className="description"
            dangerouslySetInnerHTML={{ __html: vacancy.description }}
          />
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

const ALL_STATUSES = [
  'new', 'in_progress', 'applied', 'interview', 'offer', 'rejected', 'rejected_by_company',
]

function StatusOverride({
  current, disabled, onChange,
}: {
  current: string
  disabled: boolean
  onChange: (s: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState(current)

  // Sync если карточка обновилась снаружи
  if (selected !== current && !open) setSelected(current)

  return (
    <div className="status-override">
      {!open ? (
        <button className="override-toggle" onClick={() => setOpen(true)}>
          ✏️ Change status manually
        </button>
      ) : (
        <div className="override-row">
          <select
            value={selected}
            onChange={e => setSelected(e.target.value)}
            className="override-select"
            disabled={disabled}
          >
            {ALL_STATUSES.map(s => (
              <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
            ))}
          </select>
          <button
            className="btn btn-secondary"
            disabled={disabled || selected === current}
            onClick={() => { onChange(selected); setOpen(false) }}
          >
            Save
          </button>
          <button
            className="override-cancel"
            onClick={() => { setSelected(current); setOpen(false) }}
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  )
}

/** Минимальный markdown → HTML для отчётов от Claude. */
function mdToHtml(md: string): string {
  return md
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/^(?!<[hul])(.+)$/gm, '$1')
    .replace(/\n/g, ' ')
}
