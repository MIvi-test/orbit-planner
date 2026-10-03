/**
 * Тонкий клиент над `/api/*`. Один маршрут читает все витрины
 * (GET /api/views/{view}), три маршрута пишут (docs/SCHEMA.md §4).
 */
import { authHeaders, notifyUnauthorized } from './auth'

const BASE = '/api'

export class ApiError extends Error {
  readonly status: number
  readonly body: unknown

  constructor(status: number, message: string, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

/** Сервер недоступен вовсе (503, сеть, DNS) — отличается от ошибки данных. */
export class ServiceUnavailableError extends ApiError {}

async function parseErrorBody(res: Response): Promise<unknown> {
  const text = await res.text().catch(() => '')
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

function messageFrom(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'message' in body) {
    const m = (body as { message?: unknown }).message
    if (typeof m === 'string') return m
  }
  return fallback
}

export function postJson<T>(path: string, payload: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  })
}

/** 401 — токена нет или он неверен: приложение покажет экран входа. */
function failOnUnauthorized(res: Response): void {
  // `/me` сам является проверкой входа: его 401 обрабатывает AuthProvider, а событие
  // перезапрашивало бы `me` по кругу и не давало запросу завершиться.
  if (res.status === 401 && !res.url.endsWith('/api/me')) notifyUnauthorized()
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { ...authHeaders(), ...(init?.headers as Record<string, string> | undefined) },
    })
  } catch (err) {
    throw new ServiceUnavailableError(0, 'сеть недоступна или сервер не отвечает', {
      error: 'network_error',
      message: String(err),
    })
  }
  if (!res.ok) {
    failOnUnauthorized(res)
    const body = await parseErrorBody(res)
    const message = messageFrom(body, res.statusText)
    if (res.status === 503) throw new ServiceUnavailableError(res.status, message, body)
    throw new ApiError(res.status, message, body)
  }
  return (await res.json()) as T
}

/** Конверт ответа `GET /api/views/{view}` (docs/UI_SPEC.md §0). */
export interface ViewEnvelope<T> {
  view: string
  kind: 'view' | 'table'
  screen: string
  note: string
  run_id: number | null
  run_column: string | null
  run_default: boolean
  as_of: string
  order: string[]
  limit: number
  offset: number
  count: number
  returned: number
  truncated: boolean
  has_more: boolean
  columns: string[]
  items: T[]
}

export interface ViewParams {
  runId?: number
  limit?: number
  offset?: number
  order?: string
}

function buildQuery(params: ViewParams): string {
  const q = new URLSearchParams()
  if (params.runId !== undefined) q.set('run_id', String(params.runId))
  if (params.limit !== undefined) q.set('limit', String(params.limit))
  if (params.offset !== undefined) q.set('offset', String(params.offset))
  if (params.order) q.set('order', params.order)
  const s = q.toString()
  return s ? `?${s}` : ''
}

/** `GET /api/views/{name}` — строки витрины как есть плюс конверт. */
export function fetchView<T>(name: string, params: ViewParams = {}): Promise<ViewEnvelope<T>> {
  return request<ViewEnvelope<T>>(`/views/${name}${buildQuery(params)}`)
}

export interface AbsenceScenario {
  run_id: number
  engineer_id: string
  assumptions: string
  affected_tasks: Array<{
    task_id: string
    prodf_id: string
    previous_end_sprint: number
    scenario_end_sprint: number | null
    delay_sprints: number | null
    decision: string
    reason: string | null
  }>
  affected_chain: Array<{ blocking: string; blocked: string }>
  lost_initiatives: string[]
  extra_deferred_hh: string
  scenario_reasons: Record<string, number>
}

export function fetchAbsenceScenario(engineerId: string, runId: number): Promise<AbsenceScenario> {
  const query = new URLSearchParams({ engineer_id: engineerId, run_id: String(runId) })
  return request<AbsenceScenario>(`/scenarios/absence?${query}`)
}

export interface ViewSource {
  name: string
  kind: 'view' | 'table'
  screen: string
  run_column: string | null
  order: string[]
  orderable: string[]
  note: string
}

export interface ViewCatalog {
  count: number
  limit_default: number
  limit_max: number
  items: ViewSource[]
}

/** `GET /api/views` — справочник витрин (контракт из живого сервера). */
export function fetchCatalog(): Promise<ViewCatalog> {
  return request<ViewCatalog>('/views')
}

export interface HealthResponse {
  status?: 'ok'
  dsn?: string
  server_version?: string
  dbname?: string
  tables?: number
  views?: number
}

/** `GET /api/me` — кто вошёл и с какой ролью (ADR-027). */
export interface MeResponse {
  name: string
  role: 'viewer' | 'planner' | 'admin'
  source: 'env' | 'db' | 'anonymous'
  auth: 'required' | 'off'
}

export function fetchMe(): Promise<MeResponse> {
  return request<MeResponse>('/me')
}

/** Шаблон факта: ссылка `<a download>` не передаёт заголовок авторизации, поэтому — через fetch. */
export async function downloadTemplate(sprintNo?: number): Promise<void> {
  const query = sprintNo ? `?sprint=${sprintNo}` : ''
  const res = await fetch(`${BASE}/actuals/template${query}`, { headers: authHeaders() })
  if (!res.ok) {
    failOnUnauthorized(res)
    const body = await parseErrorBody(res)
    throw new ApiError(res.status, messageFrom(body, res.statusText), body)
  }
  const blob = await res.blob()
  const disposition = res.headers.get('Content-Disposition') ?? ''
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `actuals_sprint_${sprintNo ?? ''}.csv`
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}

/** Файл отправляется телом POST, без multipart (сервер — только stdlib). */
async function postFile<T>(path: string, file: File, extraQuery: Record<string, string> = {}): Promise<T> {
  const q = new URLSearchParams({ filename: file.name, ...extraQuery })
  let res: Response
  try {
    res = await fetch(`${BASE}${path}?${q.toString()}`, { method: 'POST', body: file, headers: authHeaders() })
  } catch (err) {
    throw new ServiceUnavailableError(0, 'сеть недоступна или сервер не отвечает', {
      error: 'network_error',
      message: String(err),
    })
  }
  const body = (await res.text().then((t) => (t ? JSON.parse(t) : null))) as T
  if (!res.ok) {
    failOnUnauthorized(res)
    const message = messageFrom(body, res.statusText)
    if (res.status === 503) throw new ServiceUnavailableError(res.status, message, body)
    throw new ApiError(res.status, message, body)
  }
  return body
}

export { request, postFile }
