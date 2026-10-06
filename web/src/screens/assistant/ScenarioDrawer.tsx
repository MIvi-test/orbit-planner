import { useState } from 'react'
import { ActionIcon, Alert, Button, Drawer, Group, Menu, NumberInput, Select, Stack, Text } from '@mantine/core'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { useQueryClient } from '@tanstack/react-query'
import { assistantApi, newKey, waitForJob, type Answer, type Conversation, type Measure } from '../../api/assistant'
import type { ScreenId } from '../../hooks/useHashRoute'
import { useBusFactor, useOrbitMap, useTeams } from '../../hooks/useViews'
import { AI_KEYS } from './hooks'
import { AnswerCard } from './AnswerCard'

type Kind = Measure['kind']
const KIND_LABEL: Record<Kind, string> = { hire: 'Найм', loan: 'Перевод сотрудника', train: 'Обучение' }

function blank(kind: Kind): Measure {
  if (kind === 'hire') return { kind, role_id: 0, team_id: '', rate: 0.5, start_sprint: 2, hiring_lag_sprints: 1, skill_ids: [] }
  if (kind === 'loan') return { kind, engineer_id: '', team_id: '', rate: 0.5, start_sprint: 2 }
  return { kind, trainee_id: '', mentor_id: '', role_id: 0, team_id: '', rate: 0.5, start_sprint: 2, training_sprints: 1, mentor_rate: 0.1, skill_ids: [] }
}

function complete(m: Measure): boolean {
  if (m.kind === 'hire') return m.role_id > 0 && !!m.team_id
  if (m.kind === 'loan') return !!m.engineer_id && !!m.team_id
  return !!m.trainee_id && !!m.mentor_id && m.role_id > 0 && !!m.team_id
}

/** Сравнение кадровых мер: до трёх вариантов, в каждом до пяти мер (найм, перевод, обучение). Опубликованный план не меняется. */
export function ScenarioDrawer({ conv, opened, onClose, onEvidence, onNavigate }: {
  conv: Conversation
  opened: boolean
  onClose: () => void
  onEvidence: (id: string) => void
  onNavigate: (screen: ScreenId, query?: Record<string, string>) => void
}) {
  const qc = useQueryClient()
  const teams = useTeams().data?.items ?? []
  const engineers = useOrbitMap().data?.items ?? []
  const roles = useBusFactor().data?.items ?? []
  const teamData = teams.map((t) => ({ value: t.team_id, label: t.team_id }))
  const roleData = roles.map((r) => ({ value: String(r.role_id), label: r.role_name }))
  const engData = engineers.map((e) => ({ value: e.engineer_id, label: `${e.engineer_id} · ${e.role_name}` }))
  const [alts, setAlts] = useState<Measure[][]>([[blank('hire')]])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<Answer | Record<string, unknown> | null>(null)

  const patch = (a: number, i: number, p: Partial<Measure>) =>
    setAlts((s) => s.map((list, x) => (x === a ? list.map((m, y) => (y === i ? ({ ...m, ...p } as Measure) : m)) : list)))
  const valid = alts.every((list) => list.length > 0 && list.every(complete))

  const run = async () => {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const queued = await assistantApi.compare(conv.conversation_id, { expected_context_revision: conv.context_revision, alternatives: alts.map((measures) => ({ measures })) }, newKey())
      const job = await waitForJob(queued.job_id)
      if (job.status === 'completed' && job.result) setResult(job.result)
      else setError(job.error?.error.message ?? `Расчёт завершился со статусом «${job.status}».`)
      await Promise.all([qc.invalidateQueries({ queryKey: AI_KEYS.recs(conv.conversation_id) }), qc.invalidateQueries({ queryKey: AI_KEYS.messages(conv.conversation_id) })])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const field = (m: Measure, a: number, i: number) => (
    <Stack gap="xs">
      {(m.kind === 'hire' || m.kind === 'train') && (
        <Select label="Роль" data={roleData} searchable value={m.role_id ? String(m.role_id) : null} onChange={(v) => patch(a, i, { role_id: Number(v) })} />
      )}
      {m.kind === 'loan' && <Select label="Сотрудник" data={engData} searchable value={m.engineer_id || null} onChange={(v) => patch(a, i, { engineer_id: v ?? '' })} />}
      {m.kind === 'train' && (
        <Group grow>
          <Select label="Кого учим" data={engData} searchable value={m.trainee_id || null} onChange={(v) => patch(a, i, { trainee_id: v ?? '' })} />
          <Select label="Наставник" data={engData} searchable value={m.mentor_id || null} onChange={(v) => patch(a, i, { mentor_id: v ?? '' })} />
        </Group>
      )}
      <Group grow>
        <Select label="Команда" data={teamData} value={m.team_id || null} onChange={(v) => patch(a, i, { team_id: v ?? '' })} />
        <NumberInput label="Ставка" min={0.1} max={1} step={0.1} decimalScale={2} value={m.rate} onChange={(v) => patch(a, i, { rate: Number(v) || 0.5 })} />
        <NumberInput label="С какого спринта" min={1} max={6} value={m.start_sprint} onChange={(v) => patch(a, i, { start_sprint: Number(v) || 1 })} />
      </Group>
      {m.kind === 'hire' && <NumberInput label="Задержка найма, спринтов" min={0} max={6} value={m.hiring_lag_sprints} onChange={(v) => patch(a, i, { hiring_lag_sprints: Number(v) || 0 })} />}
      {m.kind === 'train' && (
        <Group grow>
          <NumberInput label="Спринтов обучения" min={1} max={6} value={m.training_sprints} onChange={(v) => patch(a, i, { training_sprints: Number(v) || 1 })} />
          <NumberInput label="Ставка наставника" min={0.05} max={1} step={0.05} decimalScale={2} value={m.mentor_rate} onChange={(v) => patch(a, i, { mentor_rate: Number(v) || 0.1 })} />
        </Group>
      )}
    </Stack>
  )

  return (
    <Drawer opened={opened} onClose={onClose} position="right" size="xl" title="Сравнить кадровые меры">
      <Stack gap="md">
        <Text size="sm" c="dimmed">Соберите до трёх вариантов. Помощник пересчитает план для каждого и для их сочетания, включая потери команд-доноров. Это гипотеза: опубликованный план не меняется.</Text>
        {alts.map((list, a) => (
          <div key={a} className="ai-alt">
            <Group justify="space-between" mb="xs">
              <Text fw={700}>Вариант {a + 1}</Text>
              {alts.length > 1 && <ActionIcon variant="subtle" color="red" aria-label="Удалить вариант" onClick={() => setAlts((s) => s.filter((_, x) => x !== a))}><IconTrash size={18} /></ActionIcon>}
            </Group>
            <Stack gap="md">
              {list.map((m, i) => (
                <div key={i} className="ai-measure">
                  <Group justify="space-between" mb={6}>
                    <Text size="sm" fw={600}>{KIND_LABEL[m.kind]}</Text>
                    {list.length > 1 && <ActionIcon variant="subtle" color="gray" aria-label="Убрать меру" onClick={() => setAlts((s) => s.map((l, x) => (x === a ? l.filter((_, y) => y !== i) : l)))}><IconTrash size={16} /></ActionIcon>}
                  </Group>
                  {field(m, a, i)}
                </div>
              ))}
              {list.length < 5 && (
                <Menu withinPortal>
                  <Menu.Target><Button size="compact-sm" variant="light" leftSection={<IconPlus size={14} />}>Добавить меру</Button></Menu.Target>
                  <Menu.Dropdown>
                    {(Object.keys(KIND_LABEL) as Kind[]).map((k) => (
                      <Menu.Item key={k} onClick={() => setAlts((s) => s.map((l, x) => (x === a ? [...l, blank(k)] : l)))}>{KIND_LABEL[k]}</Menu.Item>
                    ))}
                  </Menu.Dropdown>
                </Menu>
              )}
            </Stack>
          </div>
        ))}
        <Group justify="space-between">
          <Button variant="default" size="compact-sm" disabled={alts.length >= 3} leftSection={<IconPlus size={14} />} onClick={() => setAlts((s) => [...s, [blank('hire')]])}>Ещё вариант</Button>
          <Button onClick={() => void run()} loading={busy} disabled={!valid}>Рассчитать</Button>
        </Group>
        {error && <Alert color="red" title="Расчёт не выполнен">{error}</Alert>}
        {result && ('summary' in result
          ? <div className="ai-alt"><AnswerCard answer={result as Answer} onEvidence={onEvidence} onNavigate={onNavigate} /></div>
          : <pre className="mono ai-json">{JSON.stringify(result, null, 2)}</pre>)}
      </Stack>
    </Drawer>
  )
}
