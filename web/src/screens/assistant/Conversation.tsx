import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Alert, Badge, Button, Group, Loader, Stack, Text } from '@mantine/core'
import { IconPlayerStop, IconRefresh, IconSparkles, IconUser } from '@tabler/icons-react'
import { useQueryClient } from '@tanstack/react-query'
import { assistantApi, newKey, waitForJob, type ApiErrorBody, type ChatMessage, type Conversation as Conv, type JobStatus } from '../../api/assistant'
import type { ScreenId } from '../../hooks/useHashRoute'
import { useRun } from '../../hooks/useRun'
import { useLabel } from '../../theme/imperiumLabels'
import { AI_KEYS, useMessages } from './hooks'
import { AnswerCard } from './AnswerCard'
import { EmptyHero } from './EmptyHero'
import { Composer } from './Composer'

const STATUS_TEXT: Record<string, string> = {
  queued: 'Вопрос в очереди…',
  running: 'Ассистент думает…',
}

/** Лента сообщений и поле ввода. Ответы приходят заданием: отправка → опрос → сохранённое сообщение. */
export function ConversationView({
  conv,
  onEvidence,
  onNavigate,
  autoSend,
  onAutoSent,
  toolbar,
}: {
  conv: Conv
  onEvidence: (id: string) => void
  onNavigate: (screen: ScreenId, query?: Record<string, string>) => void
  /** Вопрос, который нужно отправить сразу после открытия нового пустого чата (клик по примеру). */
  autoSend?: string | null
  onAutoSent?: () => void
  /** Панель под полем ввода: тема чата и модель. */
  toolbar?: ReactNode
}) {
  const qc = useQueryClient()
  const label = useLabel()
  const { runs, setRunId } = useRun()
  const messages = useMessages(conv.conversation_id)
  const [pending, setPending] = useState<{ text: string; status: JobStatus } | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [failure, setFailure] = useState<{ message: string; retryable: boolean; text: string } | null>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const items: ChatMessage[] = messages.data ?? []
  const busy = pending !== null
  const latestRun = runs.length ? Math.max(...runs.map((r) => r.run_id)) : null

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [items.length, pending?.status, failure])

  const refresh = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: AI_KEYS.messages(conv.conversation_id) }),
      qc.invalidateQueries({ queryKey: AI_KEYS.conv(conv.conversation_id) }),
      qc.invalidateQueries({ queryKey: AI_KEYS.recs(conv.conversation_id) }),
      qc.invalidateQueries({ queryKey: AI_KEYS.list }),
    ])
  }

  const send = async (raw: string) => {
    const value = raw.trim()
    if (!value || busy) return
    setFailure(null)
    setPending({ text: value, status: 'queued' })
    try {
      const lastId = items.length ? items[items.length - 1].message_id : null
      const queued = await assistantApi.send(conv.conversation_id, { text: value, expected_context_revision: conv.context_revision, expected_last_message_id: lastId }, newKey())
      setJobId(queued.job_id)
      await qc.invalidateQueries({ queryKey: AI_KEYS.messages(conv.conversation_id) })
      const job = await waitForJob(queued.job_id, (status) => setPending((p) => (p ? { ...p, status } : p)))
      if (job.status !== 'completed') {
        const err: ApiErrorBody['error'] | undefined = job.error?.error
        setFailure({
          message: err?.message ?? (job.status === 'cancelled' ? 'Ответ отменён.' : job.status === 'expired' ? 'Время ожидания ответа истекло.' : 'Не удалось получить ответ.'),
          retryable: err?.retryable ?? job.status === 'expired',
          text: value,
        })
      }
    } catch (e) {
      setFailure({ message: e instanceof Error ? e.message : String(e), retryable: true, text: value })
    } finally {
      setJobId(null)
      setPending(null)
      await refresh()
    }
  }

  const cancel = async () => {
    if (jobId) await assistantApi.cancelJob(jobId).catch(() => undefined)
  }

  useEffect(() => {
    if (autoSend && !messages.isPending && items.length === 0 && !busy) {
      onAutoSent?.()
      void send(autoSend)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSend, messages.isPending])

  const empty = !messages.isPending && items.length === 0 && !pending
  return (
    <div className="ai-chat">
      {conv.newer_run_available && latestRun !== null && conv.run_id !== null && latestRun > conv.run_id && (
        <Alert color="yellow" variant="light" title="Появился более новый прогон" mb="sm">
          <Group justify="space-between" wrap="nowrap">
            <Text size="sm">Чат опирается на прогон {conv.run_id}; доступен прогон {latestRun}. Прежние рекомендации могут устареть.</Text>
            <Button size="compact-sm" onClick={() => {
              const r = runs.find((x) => x.run_id === latestRun)
              if (!r || conv.pi_id === null || conv.scenario_id === null) return
              void assistantApi.bindContext(conv.conversation_id, { pi_id: conv.pi_id, scenario_id: conv.scenario_id, run_id: latestRun, expected_context_revision: conv.context_revision }).then(async () => { setRunId(latestRun); await refresh() })
            }}>Обновить контекст</Button>
          </Group>
        </Alert>
      )}
      <div className="ai-thread" data-empty={empty || undefined}>
        {messages.isPending && <Group justify="center" py="xl"><Loader size="sm" /></Group>}
        {messages.isError && <Alert color="red" title="Не удалось загрузить сообщения">{messages.error.message}</Alert>}
        {empty && <EmptyHero planning={conv.scope === 'planning'} disabled={busy} onPick={(q) => void send(q)} />}
        {items.map((m, i) => {
          // Вопрос без ответа (сбой модели или отмена прошлой сессии): показываем это, а у последнего — повтор.
          const orphan = m.role === 'user' && items[i + 1]?.role !== 'assistant' && !(i === items.length - 1 && (pending || failure))
          return (
          <div key={m.message_id} className="ai-msg" data-role={m.role}>
            <div className="ai-msg__avatar" aria-hidden="true">{m.role === 'user' ? <IconUser size={18} /> : <IconSparkles size={18} />}</div>
            <div className="ai-msg__body">
              {m.role === 'assistant' && m.answer
                ? <AnswerCard answer={m.answer} onEvidence={onEvidence} onNavigate={onNavigate} />
                : <Text className="ai-answer__text">{m.text}</Text>}
              {m.role === 'assistant' && m.context_revision < conv.context_revision && (
                <Badge mt={8} size="xs" color="gray" variant="outline">Контекст прежней версии</Badge>
              )}
              {orphan && (
                <Group gap={6} mt={4} justify="flex-end">
                  <Text size="xs" c="dimmed">Ответ не получен</Text>
                  {i === items.length - 1 && <Button size="compact-xs" variant="subtle" leftSection={<IconRefresh size={12} />} disabled={busy} onClick={() => void send(m.text)}>Повторить</Button>}
                </Group>
              )}
            </div>
          </div>
          )
        })}
        {pending && (
          <>
            {!items.some((m) => m.role === 'user' && m.text === pending.text) && (
              <div className="ai-msg" data-role="user"><div className="ai-msg__avatar"><IconUser size={18} /></div><div className="ai-msg__body"><Text className="ai-answer__text">{pending.text}</Text></div></div>
            )}
            <div className="ai-msg" data-role="assistant">
              <div className="ai-msg__avatar ai-msg__avatar--busy"><IconSparkles size={18} /></div>
              <div className="ai-msg__body ai-thinking">
                <span className="ai-dots" aria-hidden="true"><i /><i /><i /></span>
                <Text size="sm" c="dimmed">{label(STATUS_TEXT[pending.status] ?? 'Готовлю ответ…')}</Text>
                {jobId && <Button size="compact-xs" variant="subtle" color="gray" leftSection={<IconPlayerStop size={13} />} onClick={() => void cancel()}>Остановить</Button>}
              </div>
            </div>
          </>
        )}
        {failure && (
          <Alert color="red" title="Ответ не получен" icon={<IconRefresh size={18} />}>
            <Stack gap={6}>
              <Text size="sm">{failure.message}</Text>
              {failure.retryable && <Button size="compact-sm" variant="light" onClick={() => void send(failure.text)}>Повторить вопрос</Button>}
            </Stack>
          </Alert>
        )}
        <div ref={endRef} />
      </div>
      <Composer busy={busy} onSend={(t) => void send(t)} toolbar={toolbar}
        placeholder={conv.scope === 'planning' ? 'Спросите про этот прогон…' : 'Спросите, как устроена система…'} />
    </div>
  )
}
