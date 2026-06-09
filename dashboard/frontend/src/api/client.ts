import axios, { AxiosError } from 'axios'

// Credentials хранятся в sessionStorage — сбрасываются при закрытии браузера
const getCredentials = () => ({
  username: sessionStorage.getItem('dash_user') ?? '',
  password: sessionStorage.getItem('dash_pass') ?? '',
})

export const setCredentials = (username: string, password: string) => {
  sessionStorage.setItem('dash_user', username)
  sessionStorage.setItem('dash_pass', password)
}

export const clearCredentials = () => {
  sessionStorage.removeItem('dash_user')
  sessionStorage.removeItem('dash_pass')
}

export const hasCredentials = () =>
  !!sessionStorage.getItem('dash_user') && !!sessionStorage.getItem('dash_pass')

const api = axios.create({ baseURL: '/api' })

// Подставляем Basic Auth в каждый запрос
api.interceptors.request.use((config) => {
  const { username, password } = getCredentials()
  if (username && password) {
    config.auth = { username, password }
  }
  return config
})

// 401 — сбрасываем credentials, страница перезагрузится на Login
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      clearCredentials()
      window.location.reload()
    }
    return Promise.reject(err)
  }
)

// --- Types ---

export interface Vacancy {
  id: number
  title: string
  company: string | null
  location: string | null
  city: string | null
  platform: string
  work_format: string
  status: string
  url: string
  posted_at: string | null
  fetched_at: string | null
}

export interface CoverLetter {
  id: number
  body: string
  version: number
  approved: boolean
  created_at: string | null
}

export interface VacancyDetail extends Vacancy {
  description: string | null
  cover_letters: CoverLetter[]
  company_report: string | null
  match_analysis: string | null
  notes: string | null
}

export interface Event {
  id: number
  title: string
  url: string
  event_type: string
  location: string | null
  event_date: string | null
  organizer: string | null
  description: string | null
  score: number
  status: string
  source: string
  fetched_at: string | null
}

export interface Stats {
  vacancies: Record<string, number>
  events: Record<string, number>
  platforms: Record<string, number>
}

// --- API calls ---

// Проверка credentials при логине — через чистый axios без interceptors,
// чтобы 401 не вызвал reload страницы до того как catch покажет ошибку.
export const verifyCredentials = async (username: string, password: string): Promise<boolean> => {
  try {
    await axios.get('/api/stats', { auth: { username, password } })
    return true
  } catch (err) {
    const e = err as AxiosError
    if (e.response?.status === 401) return false
    throw err  // сетевая ошибка — пробрасываем
  }
}

export const fetchStats = () => api.get<Stats>('/stats').then(r => r.data)

export const fetchVacancies = (params?: { status?: string; platform?: string }) =>
  api.get<Vacancy[]>('/vacancies', { params }).then(r => r.data)

export const fetchVacancy = (id: number) =>
  api.get<VacancyDetail>(`/vacancies/${id}`).then(r => r.data)

export const updateVacancyStatus = (id: number, status: string) =>
  api.patch(`/vacancies/${id}/status`, { status }).then(r => r.data)

// AI генерация — долгие запросы, таймаут 90 сек
const AI_TIMEOUT = 90_000

export const generateLetter = (id: number) =>
  api.post<{ body: string }>(`/vacancies/${id}/generate-letter`, {}, { timeout: AI_TIMEOUT }).then(r => r.data)

export const fetchCompanyReport = (id: number) =>
  api.post<{ report: string }>(`/vacancies/${id}/company-report`, {}, { timeout: AI_TIMEOUT }).then(r => r.data)

export const fetchMatchAnalysis = (id: number) =>
  api.post<{ analysis: string }>(`/vacancies/${id}/match-analysis`, {}, { timeout: AI_TIMEOUT }).then(r => r.data)

export const saveNotes = (id: number, notes: string) =>
  api.patch(`/vacancies/${id}/notes`, { notes }).then(r => r.data)

export const regenerateLetter = (id: number, comments: string | null) =>
  api.post<{ body: string }>(`/vacancies/${id}/regenerate-letter`, { comments }, { timeout: AI_TIMEOUT }).then(r => r.data)

export const fetchEvents = (params?: { status?: string }) =>
  api.get<Event[]>('/events', { params }).then(r => r.data)
