/**
 * Клиент ИИ-ассистента: контракт — docs/openapi/assistant.yaml.
 * Ошибки приходят как {error: {code, message, retryable}, request_id}; их разбирает общий `request`.
 */
import { request } from './client'

export type PrivacyMode = 'local_only' | 'configured'
export type Scope = 'knowledge' | 'planning'
export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'expired'

export interface ProviderProfile {
  profile_id: number
  name: string
  protocol: string
  base_url: string
  model: string
  auth_type: string
  network_scope: 'internal' | 'external'
  credential_configured: boolean
  version: number
  capabilities?: Record<string, unknown>
  min_role?: 'viewer' | 'planner' | 'admin'
}

export interface ProviderProfileInput {
  name: string
  protocol: 'gemini' | 'ollama' | 'openai_compatible'
  base_url: string
  model: string
  auth_type: 'bearer' | 'header' | 'none'
  auth_header_name?: string | null
  api_key_ref?: string | null
  network_scope: 'internal' | 'external'
  min_role?: 'viewer' | 'planner' | 'admin'
  /** thinking=false выключает скрытые рассуждения модели: ответы быстрее. */
  capabilities?: { thinking?: boolean; json_mode?: boolean }
}

export interface Prompt {
  prompt_id: number
  version: number
  content: string
}

export interface Conversation {
  conversation_id: string
  title?: string
  scope: Scope
  context_revision: number
  provider_profile_id: number
  privacy_mode: PrivacyMode
  pi_id: string | null
  scenario_id: string | null
  run_id: number | null
  newer_run_available: boolean | null
}

export interface Recommendation {
  recommendation_id: string
  text: string
  stale_reasons?: string[]
  basis_status: 'verified_by_scenario' | 'proposal' | 'needs_data'
  freshness: 'current' | 'stale' | 'superseded'
  evidence_ids: string[]
  scenario_result_id?: string | null
  supersedes?: string | null
}

export interface Answer {
  status: 'answered' | 'needs_clarification' | 'insufficient_data'
  summary: string
  explanation: string
  recommendations: Recommendation[]
  clarification?: string | null
  evidence_ids: string[]
  fact_refs?: { evidence_id: string; field: string }[]
  degraded?: boolean
  entity_refs: { type: string; id: string; context_revision: number }[]
  context_revision: number
  newer_run_available: boolean | null
  limitations: string[]
  kb_revision?: string | null
  sources?: { chunk_id: string; path: string; heading: string; version: string }[]
}

export interface ChatMessage {
  message_id: string
  role: 'user' | 'assistant'
  text: string
  context_revision: number
  answer?: Answer
}

export interface ApiErrorBody {
  request_id: string
  error: { code: string; message: string; retryable: boolean; details?: Record<string, unknown> }
}

export interface Job {
  job_id: string
  status: JobStatus
  result?: Answer | Record<string, unknown>
  error: ApiErrorBody | null
}

export interface Evidence {
  evidence_id: string
  source_type: 'snapshot' | 'document' | 'scenario'
  source_ref: string
  payload: Record<string, unknown>
}

export interface KbStatus {
  revision: string | null
  documents: number
  embedding_model?: string | null
  embedding_digest?: string | null
  dimensions?: number | null
}

export type Measure =
  | { kind: 'hire'; role_id: number; team_id: string; rate: number; start_sprint: number; hiring_lag_sprints: number; skill_ids: number[] }
  | { kind: 'loan'; engineer_id: string; team_id: string; rate: number; start_sprint: number }
  | {
      kind: 'train'; trainee_id: string; mentor_id: string; role_id: number; team_id: string; rate: number
      start_sprint: number; training_sprints: number; mentor_rate: number; skill_ids: number[]
    }

const json = (method: string, body: unknown, extra?: Record<string, string>): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json', ...extra },
  body: JSON.stringify(body),
})

const A = '/assistant'

export const assistantApi = {
  profiles: () => request<{ profiles: ProviderProfile[] }>(`${A}/profiles`),
  createProfile: (input: ProviderProfileInput) => request<ProviderProfile>(`${A}/profiles`, json('POST', input)),
  /** Правка создаёт новую версию профиля; чаты переходят на неё. Пустая ссылка на ключ — прежняя остаётся. */
  updateProfile: (id: number, input: ProviderProfileInput) => request<ProviderProfile>(`${A}/profiles/${id}`, json('PUT', input)),
  /** Профиль выключается: прошлые ответы его помнят, чатам нужно выбрать другую модель. */
  deleteProfile: (id: number) => request<{ deleted: true; profile_id: number }>(`${A}/profiles/${id}`, { method: 'DELETE' }),
  checkProfile: (id: number) => request<Record<string, unknown>>(`${A}/profiles/${id}/check`, { method: 'POST' }),
  defaultPrompt: () => request<Prompt>(`${A}/prompts/default`),
  saveDefaultPrompt: (content: string) => request<Prompt>(`${A}/prompts/default`, json('PUT', { content })),
  myPrompt: () => request<Prompt>(`${A}/prompts/me`),
  saveMyPrompt: (content: string) => request<Prompt>(`${A}/prompts/me`, json('PUT', { content })),
  conversations: (cursor?: string) =>
    request<{ items: Conversation[]; next_cursor: string | null }>(`${A}/conversations${cursor ? `?cursor=${cursor}` : ''}`),
  createConversation: (input: {
    scope: Scope; provider_profile_id: number; privacy_mode: PrivacyMode; pi_id?: string; scenario_id?: string; run_id?: number
  }) => request<Conversation>(`${A}/conversations`, json('POST', input)),
  conversation: (id: string) => request<Conversation>(`${A}/conversations/${id}`),
  rename: (id: string, title: string) => request<Conversation>(`${A}/conversations/${id}/title`, json('PUT', { title })),
  remove: (id: string) => request<{ deleted: true; conversation_id: string }>(`${A}/conversations/${id}`, { method: 'DELETE' }),
  settings: (id: string, body: { provider_profile_id: number; privacy_mode: PrivacyMode }) =>
    request<Conversation>(`${A}/conversations/${id}/settings`, json('PUT', body)),
  bindContext: (id: string, body: { pi_id: string; scenario_id: string; run_id: number; expected_context_revision: number }) =>
    request<Conversation>(`${A}/conversations/${id}/context`, json('POST', body)),
  messages: (id: string, cursor?: string) =>
    request<{ items: ChatMessage[]; next_cursor: string | null }>(`${A}/conversations/${id}/messages${cursor ? `?cursor=${cursor}` : ''}`),
  send: (id: string, body: { text: string; expected_context_revision: number; expected_last_message_id: string | null }, key: string) =>
    request<{ job_id: string; status: JobStatus }>(`${A}/conversations/${id}/messages`, json('POST', body, { 'Idempotency-Key': key })),
  compare: (id: string, body: { expected_context_revision: number; alternatives: { measures: Measure[]; supersedes?: string }[] }, key: string) =>
    request<{ job_id: string; status: JobStatus }>(`${A}/conversations/${id}/scenarios/compare`, json('POST', body, { 'Idempotency-Key': key })),
  recommendations: (id: string) => request<{ recommendations: Recommendation[] }>(`${A}/conversations/${id}/recommendations`),
  job: (id: string) => request<Job>(`${A}/jobs/${id}`),
  cancelJob: (id: string) => request<Job>(`${A}/jobs/${id}/cancel`, { method: 'POST' }),
  evidence: (id: string) => request<Evidence>(`${A}/evidence/${id}`),
  kbStatus: () => request<KbStatus>(`${A}/kb/status`),
  kbReindex: () => request<{ job_id: string; status: JobStatus }>(`${A}/kb/reindex`, { method: 'POST' }),
}

/** Все сообщения чата: сервер отдаёт по 50 по курсору. */
export async function allMessages(id: string): Promise<ChatMessage[]> {
  const out: ChatMessage[] = []
  let cursor: string | undefined
  for (let i = 0; i < 40; i += 1) {
    const page = await assistantApi.messages(id, cursor)
    out.push(...page.items)
    if (!page.next_cursor) break
    cursor = page.next_cursor
  }
  return out
}

/** Опрашивает задание, пока оно не дойдёт до конечного состояния. */
export async function waitForJob(jobId: string, onStatus?: (s: JobStatus) => void, signal?: AbortSignal): Promise<Job> {
  for (;;) {
    const job = await assistantApi.job(jobId)
    onStatus?.(job.status)
    if (job.status !== 'queued' && job.status !== 'running') return job
    if (signal?.aborted) return job
    await new Promise((r) => setTimeout(r, 900))
  }
}

export const newKey = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `k-${Date.now()}-${Math.random().toString(16).slice(2)}`
