/**
 * Тонкий клиент над `/api/*`. Один маршрут читает все витрины
 * (GET /api/views/{view}), три маршрута пишут (docs/SCHEMA.md §4).
 */
import { authHeaders, notifyUnauthorized } from './auth'

const BASE = '/api'
const CONTEXT_KEY = 'pi-planner-context'

export interface PiContext {
  pi_id: string
  scenario_id: string
  schema_name: string
  dataset_version: string
  created_at: string | null
}

export function selectedPiContext(): Pick<PiContext, 'pi_id' | 'scenario_id'> | null {
  try {
    const raw = localStorage.getItem(CONTEXT_KEY)
    if (!raw) return null
    const value = JSON.parse(raw)
    return typeof value.pi_id === 'string' && typeof value.scenario_id === 'string' ? value : null
  } catch {
    return null
  }
}

export function selectPiContext(context: Pick<PiContext, 'pi_id' | 'scenario_id'> | null): void {
  if (context) localStorage.setItem(CONTEXT_KEY, JSON.stringify(context))
  else localStorage.removeItem(CONTEXT_KEY)
  window.location.reload()
}

export function contextHeaders(): Headers {
  const headers = new Headers()
  const selected = selectedPiContext()
  if (selected) {
    headers.set('X-PI-ID', selected.pi_id)
    headers.set('X-Scenario-ID', selected.scenario_id)
  }
  return headers
}

export function fetchPiContexts(): Promise<{ contexts: PiContext[] }> {
  return request('/pi-contexts')
}

export function fetchSkillReviews<T>(): Promise<T> {
  return request<T>('/tasks/skill-review')
}

export interface UploadRevision {
  revision_id: number; kind: 'dataset' | 'actuals'; pi_id: string; sprint_no: number | null
  source_file: string; source_sha256: string; superseded_by: number | null; recorded_at: string
  snapshot_available: boolean
}

export function fetchUploadRevisions(): Promise<{ items: UploadRevision[] }> {
  return request('/upload-revisions')
}

export async function downloadUploadRevision(id: number): Promise<void> {
  const headers = contextHeaders()
  new Headers(authHeaders()).forEach((value, key) => headers.set(key, value))
  const response = await fetch(`${BASE}/upload-revisions/file?id=${id}`, { headers })
  if (!response.ok) {
    failOnUnauthorized(response)
    const body = await parseErrorBody(response)
    throw new ApiError(response.status, messageFrom(body, response.statusText), body)
  }
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `revision-${id}`
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = name; document.body.appendChild(link); link.click(); link.remove()
  URL.revokeObjectURL(url)
}

export async function downloadPlanSnapshot(id: number): Promise<void> {
  const headers = contextHeaders()
  new Headers(authHeaders()).forEach((value, key) => headers.set(key, value))
  const response = await fetch(`${BASE}/upload-revisions/snapshot?id=${id}`, { headers })
  if (!response.ok) {
    failOnUnauthorized(response)
    const body = await parseErrorBody(response)
    throw new ApiError(response.status, messageFrom(body, response.statusText), body)
  }
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url; link.download = `plan-snapshot-${id}.json`; document.body.appendChild(link); link.click(); link.remove()
  URL.revokeObjectURL(url)
}

export function fetchQualifications<T>(engineerId: string): Promise<T> {
  return request<T>(`/engineers/qualifications?engineer_id=${encodeURIComponent(engineerId)}`)
}

export function createPiContext(file: File, piId: string, scenarioId: string, startDate: string): Promise<PiContext & { plan: { run_id: number } }> {
  return postFile('/pi-contexts', file, { pi_id: piId, scenario_id: scenarioId, start_date: startDate })
}

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
  if (body && typeof body === 'object') {
    const m = (body as { message?: unknown }).message
    if (typeof m === 'string') return m
    // Ответы помощника: {error: {code, message, retryable}, request_id}
    const nested = (body as { error?: unknown }).error
    if (nested && typeof nested === 'object') {
      const nm = (nested as { message?: unknown }).message
      if (typeof nm === 'string') return nm
    }
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
    const headers = contextHeaders()
    new Headers(authHeaders()).forEach((value, key) => headers.set(key, value))
    new Headers(init?.headers).forEach((value, key) => headers.set(key, value))
    res = await fetch(`${BASE}${path}`, { ...init, headers })
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

export interface SensitivityScenario {
  kind: string
  label: string
  in_quarter: number
  deferred: number
  delayed_tasks: Array<{
    task_id: string
    previous_end_sprint: number
    scenario_end_sprint: number | null
    decision: string
  }>
}

export interface SensitivityResult {
  run_id: number
  method: string
  baseline: { in_quarter: number; deferred: number }
  scenarios: SensitivityScenario[]
}

export function fetchSensitivity(runId: number): Promise<SensitivityResult> {
  return request<SensitivityResult>(`/scenarios/sensitivity?run_id=${runId}`)
}

export interface PlanQualityResult {
  run_id: number
  completed_value: { tasks: number; sp: string }
  partial_initiatives: Array<{ prodf_id: string; total: number; planned: number }>
  dependency_wait: { tasks: number; earliest_wait_sprints: number }
  deferred_commitments: { tasks: number; sp: string }
  unplanned_completed_sp: string
  scarce_unused_roles: Array<{ role: string; demand_hh: string; supply_hh: string; unused_hh: string }>
  people_switches: Array<{ task_id: string; role_id: number; before: string[]; after: string[] }>
  mode_comparison: {
    modes: Record<string, { complete_initiatives: number; complete_initiative_sp: string; partial_initiatives: number; planned_tasks: number }>
    upper_bound_sp: string
    method: string
    order_search: {
      status: string; reason?: string; permutations?: number; method?: string
      best_by_mode?: Record<string, { complete_initiative_sp: string; order: string[] }>
    }
  }
  method: string
}

export function fetchPlanQuality(runId: number): Promise<PlanQualityResult> {
  return request<PlanQualityResult>(`/plan-quality?run_id=${runId}`)
}

export interface TaskTrace {
  run: { run_id: number; algorithm: string; params: Record<string, unknown>; actuals_upload_id: number | null }
  state: { status: string; remaining_hh: string; remaining_sp: string }
  decision: { decision: string; reason_text: string; reason_details: Record<string, unknown> } | null
  role_demands: Array<{ role_id: number; role_name: string; needed_hours: string }>
  assignments: Array<{ sprint_no: number; role_id: number; engineer_id: string; home_team_id: string; hours: string; available_hours: string | null }>
  dependency_bound: { earliest_start_sprint: number } | null
  source_batch: { source_file: string; source_sha256: string; config_sha256: string | null; etl_version: string } | null
  source_available: boolean
  source_records: Array<{ entity: string; entity_id: string; field_name: string; source_sheet: string; source_cell: string; raw_value: string | null; normalized_value: string | null; rule_version: string }>
}

export function fetchTaskTrace(runId: number, taskId: string): Promise<TaskTrace> {
  const query = new URLSearchParams({ run_id: String(runId), task_id: taskId })
  return request<TaskTrace>(`/tasks/trace?${query}`)
}

export interface WorkforceMeasure {
  kind: 'hire' | 'train' | 'loan'
  label: string
  effective_sprint: number
  resource_cost: string
  restored_initiatives: string[]
  gained_tasks: string[]
  lost_tasks: string[]
  net_sp_gain: string
  earlier_task_sprints: number
  in_quarter: number
}

export interface WorkforceResult {
  run_id: number
  role_id: number
  team_id: string
  start_sprint: number
  assumptions: string
  assumed_skill_ids: number[]
  baseline_in_quarter: number
  ranked_measures: WorkforceMeasure[]
}

export function fetchWorkforceScenario(runId: number, roleId: number, teamId: string, startSprint: number): Promise<WorkforceResult> {
  const query = new URLSearchParams({ run_id: String(runId), role_id: String(roleId), team_id: teamId, start_sprint: String(startSprint) })
  return request<WorkforceResult>(`/scenarios/workforce?${query}`)
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
  const headers = contextHeaders()
  new Headers(authHeaders()).forEach((value, key) => headers.set(key, value))
  const res = await fetch(`${BASE}/actuals/template${query}`, { headers })
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
  let pendingKey: string | null = null
  try {
    const headers = contextHeaders()
    new Headers(authHeaders()).forEach((value, key) => headers.set(key, value))
    if (path === '/dataset' || path === '/actuals') {
      const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
      const sha = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
      pendingKey = `upload:${headers.get('X-PI-ID') ?? 'default'}:${headers.get('X-Scenario-ID') ?? 'main'}:${path}:${q.toString()}:${sha}`
      const key = sessionStorage.getItem(pendingKey) ?? crypto.randomUUID()
      sessionStorage.setItem(pendingKey, key)
      headers.set('Idempotency-Key', key)
    }
    res = await fetch(`${BASE}${path}?${q.toString()}`, { method: 'POST', body: file, headers })
  } catch (err) {
    throw new ServiceUnavailableError(0, 'сеть недоступна или сервер не отвечает', {
      error: 'network_error',
      message: String(err),
    })
  }
  const body = (await res.text().then((t) => (t ? JSON.parse(t) : null))) as T
  if (pendingKey && res.status < 500) sessionStorage.removeItem(pendingKey)
  if (!res.ok) {
    failOnUnauthorized(res)
    const message = messageFrom(body, res.statusText)
    if (res.status === 503) throw new ServiceUnavailableError(res.status, message, body)
    throw new ApiError(res.status, message, body)
  }
  return body
}

export { request, postFile }
