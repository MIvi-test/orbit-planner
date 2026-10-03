/**
 * Тонкий клиент над `/api/*`. Один маршрут читает все витрины
 * (GET /api/views/{view}), три маршрута пишут (docs/SCHEMA.md §4).
 */
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, init)
  } catch (err) {
    throw new ServiceUnavailableError(0, 'сеть недоступна или сервер не отвечает', {
      error: 'network_error',
      message: String(err),
    })
  }
  if (!res.ok) {
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
  dsn: string
  server_version: string
  dbname: string
  tables: number
  views: number
}

export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}

/** Файл отправляется телом POST, без multipart (сервер — только stdlib). */
async function postFile<T>(path: string, file: File, extraQuery: Record<string, string> = {}): Promise<T> {
  const q = new URLSearchParams({ filename: file.name, ...extraQuery })
  let res: Response
  try {
    res = await fetch(`${BASE}${path}?${q.toString()}`, { method: 'POST', body: file })
  } catch (err) {
    throw new ServiceUnavailableError(0, 'сеть недоступна или сервер не отвечает', {
      error: 'network_error',
      message: String(err),
    })
  }
  const body = (await res.text().then((t) => (t ? JSON.parse(t) : null))) as T
  if (!res.ok) {
    const message = messageFrom(body, res.statusText)
    if (res.status === 503) throw new ServiceUnavailableError(res.status, message, body)
    throw new ApiError(res.status, message, body)
  }
  return body
}

export { request, postFile }
