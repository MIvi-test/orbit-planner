import { useEffect, useState } from 'react'
import { Alert, Button, Group, MultiSelect, Select, Stack, Switch, Text, TextInput } from '@mantine/core'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchSkillReviews, postJson } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'

interface ReviewRow {
  task_id: string; role_id: number; role_name: string; status: string
  source_text: string | null; reviewed_by: string | null; reviewed_at: string | null; skill_ids: number[]
}
interface SkillRow { skill_id: number; skill_name: string }
interface ReviewList { roles: ReviewRow[]; skills: SkillRow[] }

export function SkillReview() {
  const { me, can } = useAuth()
  const client = useQueryClient()
  const query = useQuery<ReviewList>({ queryKey: ['skill-reviews'], queryFn: fetchSkillReviews<ReviewList> })
  const [selected, setSelected] = useState<string | null>(null)
  const [skills, setSkills] = useState<string[]>([])
  const [source, setSource] = useState('')
  const [reviewer, setReviewer] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const rows = query.data?.roles ?? []
  const row = rows.find((item) => `${item.task_id}:${item.role_id}` === selected)
  useEffect(() => {
    setSkills(row?.skill_ids.map(String) ?? [])
    setSource(row?.source_text ?? '')
    setConfirmed(row?.status === 'confirmed')
  }, [row?.task_id, row?.role_id, row?.status, row?.source_text, query.data])

  const save = async () => {
    if (!row) return
    setBusy(true); setMessage('')
    try {
      const result = await postJson<{ plan: { run_id: number } }>('/tasks/skill-review', {
        task_id: row.task_id, role_id: row.role_id, skill_ids: skills.map(Number),
        source_text: source, confirmed, reviewed_by: me?.auth === 'required' ? me.name : reviewer,
      })
      await client.invalidateQueries()
      setMessage(`Разметка сохранена; построен прогон ${result.plan.run_id}.`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось сохранить разметку')
    } finally { setBusy(false) }
  }

  return <Stack gap="sm">
    <Text fw={600}>Требования задачи к стеку</Text>
    <Text size="xs" c="dimmed">Отсутствие проверки остаётся неизвестным. Подтверждённый пустой список означает, что ограничений по технологиям нет.</Text>
    {query.isError && <Alert color="red">{query.error instanceof Error ? query.error.message : 'Ошибка загрузки'}</Alert>}
    <Select label="Задача и роль" searchable data={rows.map((item) => ({
      value: `${item.task_id}:${item.role_id}`,
      label: `${item.task_id} · ${item.role_name} · ${item.status === 'confirmed' ? 'подтверждено' : item.status === 'proposed' ? 'черновик' : 'неизвестно'}`,
    }))} value={selected} onChange={setSelected} />
    {row && <>
      <MultiSelect label="Нужные технологии" searchable data={(query.data?.skills ?? []).map((item) => ({ value: String(item.skill_id), label: item.skill_name }))}
        value={skills} onChange={setSkills} disabled={!can('planner')} />
      <TextInput label="Источник требования" placeholder="Ссылка или цитата из карточки задачи" value={source} onChange={(event) => setSource(event.currentTarget.value)} disabled={!can('planner')} />
      {me?.auth !== 'required' && <TextInput label="Кто проверил" value={reviewer} onChange={(event) => setReviewer(event.currentTarget.value)} disabled={!can('planner')} />}
      <Group><Switch label="Подтверждаю полный набор требований" checked={confirmed} onChange={(event) => setConfirmed(event.currentTarget.checked)} disabled={!can('planner')} />
        <Button onClick={save} loading={busy} disabled={!can('planner') || !source.trim() || (me?.auth !== 'required' && !reviewer.trim())}>Сохранить и пересчитать</Button></Group>
    </>}
    {message && <Text size="sm">{message}</Text>}
  </Stack>
}
