import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  draftOutreachMessage,
  fetchCompanyReport,
  fetchMatchAnalysis,
  fetchVacancy,
  findOutreachContacts,
  generateLetter,
  regenerateLetter,
  saveNotes,
  updateOutreachStatus,
  updateVacancyStatus,
  type OutreachContact,
  type VacancyDetail,
} from '../api/client'
import StatusBadge from '../components/StatusBadge'

const ROLE_LABELS: Record<string, string> = {
  tech_lead:       '🧑‍💻 Tech lead',
  hiring_manager:  '🧑‍💼 Hiring manager',
  hr:              '👥 HR / Talent',
  other:           '👤 Other',
}

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
  const [generatingLetter, setGeneratingLetter] = useState(false)
  const [companyReport, setCompanyReport] = useState<string | null>(null)
  const [loadingReport, setLoadingReport] = useState(false)
  const [matchAnalysis, setMatchAnalysis] = useState<string | null>(null)
  const [loadingMatch, setLoadingMatch] = useState(false)
  const [notes, setNotes] = useState<string>('')
  const [notesSaved, setNotesSaved] = useState(false)
  const [savingNotes, setSavingNotes] = useState(false)
  const [regenComments, setRegenComments] = useState('')
  const [showRegen, setShowRegen] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [outreachContacts, setOutreachContacts] = useState<OutreachContact[]>([])
  const [findingContacts, setFindingContacts] = useState(false)
  const [draftingContactId, setDraftingContactId] = useState<number | null>(null)
  const [editedDrafts, setEditedDrafts] = useState<Record<number, string>>({})
  const [copiedContactId, setCopiedContactId] = useState<number | null>(null)
  const nav = useNavigate()

  useEffect(() => {
    if (!id) return
    fetchVacancy(Number(id)).then(v => {
      setVacancy(v)
      setCompanyReport(v.company_report)
      setMatchAnalysis(v.match_analysis)
      setNotes(v.notes ?? '')
      setOutreachContacts(v.outreach_contacts)
      setLoading(false)
    })
  }, [id])

  // Все переходы по статусу — мгновенно, без AI.
  // Letter generation вынесена отдельно в handleGenerateLetter (SRP).
  const handleAction = async (nextStatus: string) => {
    if (!vacancy?.id) return
    setUpdating(true)
    try {
      await updateVacancyStatus(vacancy.id, nextStatus)
      const updated = await fetchVacancy(vacancy.id)
      setVacancy(updated)
    } finally {
      setUpdating(false)
    }
  }

  // AI-пайплайн: research + cover letter — отдельная кнопка в секции письма.
  // Не блокирует смену статуса (can mark applied without letter).
  const handleGenerateLetter = async () => {
    if (!vacancy?.id) return
    setGeneratingLetter(true)
    try {
      await generateLetter(vacancy.id)
      const updated = await fetchVacancy(vacancy.id)
      setVacancy(updated)
    } finally {
      setGeneratingLetter(false)
    }
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

  const handleSaveNotes = async () => {
    if (!vacancy?.id) return
    setSavingNotes(true)
    await saveNotes(vacancy.id, notes)
    setSavingNotes(false)
    setNotesSaved(true)
    setTimeout(() => setNotesSaved(false), 2000)
  }

  const handleRegenerate = async () => {
    if (!vacancy?.id) return
    setRegenerating(true)
    try {
      await regenerateLetter(vacancy.id, regenComments || null)
      const updated = await fetchVacancy(vacancy.id)
      setVacancy(updated)
      setRegenComments('')
      setShowRegen(false)
    } finally {
      setRegenerating(false)
    }
  }

  // Outreach: находим людей в компании, черновик и статус — по каждому контакту отдельно.
  // Тот же decoupled-паттерн, что у Cover letter (SRP): поиск не тянет за собой draft.
  const handleFindContacts = async () => {
    if (!vacancy?.id) return
    setFindingContacts(true)
    try {
      const contacts = await findOutreachContacts(vacancy.id)
      setOutreachContacts(contacts)
    } finally {
      setFindingContacts(false)
    }
  }

  const handleDraftMessage = async (contactId: number) => {
    setDraftingContactId(contactId)
    try {
      const { message } = await draftOutreachMessage(contactId)
      setOutreachContacts(prev => prev.map(c =>
        c.id === contactId ? { ...c, message_draft: message, status: 'drafted' } : c
      ))
      setEditedDrafts(prev => ({ ...prev, [contactId]: message }))
    } finally {
      setDraftingContactId(null)
    }
  }

  const handleCopyMessage = (contactId: number) => {
    const text = editedDrafts[contactId] ?? ''
    navigator.clipboard.writeText(text)
    setCopiedContactId(contactId)
    setTimeout(() => setCopiedContactId(null), 2000)
  }

  const handleContactStatus = async (contactId: number, status: string) => {
    await updateOutreachStatus(contactId, status)
    setOutreachContacts(prev => prev.map(c => c.id === contactId ? { ...c, status } : c))
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
              disabled={updating}
              onClick={() => handleAction(a.next)}
            >
              {updating ? '⏳…' : a.label}
            </button>
          ))}
        </div>
      )}

      {/* Manual status override — откат или ручная корректировка */}
      <StatusOverride
        current={vacancy.status}
        disabled={updating}
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

      {/* Notes */}
      <section className="section">
        <h2>📝 My notes</h2>
        <textarea
          className="notes-textarea"
          value={notes}
          onChange={e => { setNotes(e.target.value); setNotesSaved(false) }}
          placeholder="Your thoughts about this company, role, or application…"
          rows={6}
        />
        <div className="notes-footer">
          <button
            className="btn btn-secondary"
            disabled={savingNotes}
            onClick={handleSaveNotes}
          >
            {savingNotes ? 'Saving…' : notesSaved ? '✓ Saved' : 'Save notes'}
          </button>
        </div>
      </section>

      {vacancy.description && (
        <section className="section">
          <h2>Job description</h2>
          <div
            className="description"
            dangerouslySetInnerHTML={{ __html: descriptionToHtml(vacancy.description) }}
          />
        </section>
      )}

      <section className="section">
        <div className="ai-section-header">
          <h2>✉️ Cover letter {letter && <span className="muted">v{letter.version}</span>}</h2>
          {/* Кнопка Generate — только когда нет письма и вакансия в работе.
              Паттерн идентичен Company report / Match analysis (SRP). */}
          {!letter && ['in_progress', 'letter_sent', 'new'].includes(vacancy.status) && (
            <button
              className="btn btn-primary"
              disabled={generatingLetter}
              onClick={handleGenerateLetter}
            >
              {generatingLetter ? '⏳ Generating…' : '✨ Generate cover letter'}
            </button>
          )}
        </div>
        {generatingLetter && (
          <span className="generating-hint">
            Researching company + writing cover letter — ~20 sec
          </span>
        )}

        {letter ? (
          <>
            <pre className="cover-letter">{letter.body}</pre>

            {/* Regenerate with feedback */}
            {!showRegen ? (
              <button className="override-toggle" onClick={() => setShowRegen(true)}>
                ✏️ Regenerate with feedback
              </button>
            ) : (
              <div className="regen-block">
                <textarea
                  className="notes-textarea"
                  value={regenComments}
                  onChange={e => setRegenComments(e.target.value)}
                  placeholder="What to change? e.g. 'Make the opening more specific to their product', 'Mention Go experience more prominently', 'Shorter, under 250 words'…"
                  rows={4}
                />
                <div className="regen-actions">
                  <button
                    className="btn btn-primary"
                    disabled={regenerating}
                    onClick={handleRegenerate}
                  >
                    {regenerating ? '⏳ Regenerating…' : '✨ Regenerate'}
                  </button>
                  <button
                    className="override-cancel"
                    onClick={() => { setShowRegen(false); setRegenComments('') }}
                  >
                    Cancel
                  </button>
                  {regenerating && (
                    <span className="generating-hint">~15 sec</span>
                  )}
                </div>
              </div>
            )}
          </>
        ) : (
          !generatingLetter && (
            <div className="empty">No cover letter yet</div>
          )
        )}
      </section>

      {/* Outreach — находим людей в компании, готовим черновик LinkedIn-сообщения.
          Denis всегда отправляет сам из LinkedIn UI: здесь только Find + Draft + Copy,
          никакой автоматической отправки. */}
      <section className="section">
        <div className="ai-section-header">
          <h2>🤝 Outreach contacts</h2>
          {outreachContacts.length === 0 && (
            <button
              className="btn btn-secondary"
              disabled={findingContacts}
              onClick={handleFindContacts}
            >
              {findingContacts ? '⏳ Searching…' : '🔍 Find contacts'}
            </button>
          )}
        </div>
        {findingContacts && (
          <span className="generating-hint">
            Searching public web + LinkedIn for tech leads / HR at this company — ~15 sec
          </span>
        )}

        {outreachContacts.length === 0 ? (
          !findingContacts && <div className="empty">No contacts found yet</div>
        ) : (
          <div className="outreach-list">
            {outreachContacts.map(contact => (
              <div key={contact.id} className="outreach-card">
                <div className="outreach-card-header">
                  <div>
                    <strong>{contact.full_name}</strong>
                    {contact.headline && <div className="muted">{contact.headline}</div>}
                  </div>
                  <div className="outreach-card-badges">
                    <span className="badge badge-gray">
                      {ROLE_LABELS[contact.role_category] ?? contact.role_category}
                    </span>
                    <StatusBadge value={contact.status} />
                  </div>
                </div>
                <a
                  href={contact.linkedin_url}
                  target="_blank"
                  rel="noreferrer"
                  className="apply-link"
                >
                  Open LinkedIn profile ↗
                </a>

                {contact.message_draft ? (
                  <>
                    <textarea
                      className="notes-textarea"
                      value={editedDrafts[contact.id] ?? contact.message_draft}
                      onChange={e => setEditedDrafts(prev => ({ ...prev, [contact.id]: e.target.value }))}
                      rows={3}
                    />
                    <div className="outreach-card-actions">
                      <button className="btn btn-secondary" onClick={() => handleCopyMessage(contact.id)}>
                        {copiedContactId === contact.id ? '✓ Copied' : '📋 Copy'}
                      </button>
                      <button className="override-toggle" onClick={() => handleDraftMessage(contact.id)}>
                        🔄 Regenerate
                      </button>
                      {contact.status !== 'sent' && (
                        <button
                          className="btn btn-primary"
                          onClick={() => handleContactStatus(contact.id, 'sent')}
                        >
                          ✅ Mark sent
                        </button>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="outreach-card-actions">
                    <button
                      className="btn btn-primary"
                      disabled={draftingContactId === contact.id}
                      onClick={() => handleDraftMessage(contact.id)}
                    >
                      {draftingContactId === contact.id ? '⏳ Drafting…' : '✍️ Draft message'}
                    </button>
                    {contact.status !== 'skipped' && (
                      <button
                        className="override-cancel"
                        onClick={() => handleContactStatus(contact.id, 'skipped')}
                      >
                        ❌ Skip
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
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

/**
 * Если описание plain text (LinkedIn, Remotive) - конвертируем в HTML.
 * Если уже содержит HTML-теги (The Hub) - возвращаем как есть.
 */
function descriptionToHtml(text: string): string {
  if (/<[a-z][\s\S]*?>/i.test(text)) return text
  return text
    .split(/\n{2,}/)
    .map(para => `<p>${para.replace(/\n/g, '<br>')}</p>`)
    .join('')
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
