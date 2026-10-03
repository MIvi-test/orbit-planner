import { useState } from 'react'
import { Button, Select, Stack, Table, Text } from '@mantine/core'
import { fetchWorkforceScenario, type WorkforceResult } from '../../api/client'
import { useRun } from '../../hooks/useRun'
import type { BusFactorRow, TeamRow } from '../../types/views'

export function WorkforceScenarios({ roles, teams }: { roles: BusFactorRow[]; teams: TeamRow[] }) {
  const { runId, defaultRunId, runs } = useRun()
  const [role, setRole] = useState<string | null>(null)
  const [team, setTeam] = useState<string | null>(null)
  const [sprint, setSprint] = useState<string | null>(null)
  const [result, setResult] = useState<WorkforceResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const selectedRun = runs.find((item) => item.run_id === runId)
  const calendar = (selectedRun?.params as Record<string, unknown> | undefined)?.calendar as { sprint_count?: number } | undefined
  const count = calendar?.sprint_count ?? 6
  const earliest = Math.max(1, selectedRun?.as_of_sprint ?? 1)

  async function calculate() {
    if (!runId || !role || !team || !sprint) return
    setBusy(true)
    setError(null)
    try {
      setResult(await fetchWorkforceScenario(runId, Number(role), team, Number(sprint)))
    } catch (cause) {
      setResult(null)
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  return <Stack gap="sm">
    <Text size="xs" c="dimmed">Сравнение на одном входе: +0,5 ставки после найма, обучение с потерей времени наставника и перевод части ставки между командами. Гипотетический план не публикуется.</Text>
    <Select label="Роль" placeholder="Выберите роль" data={roles.filter((item) => Number(item.demand_hh) > 0).map((item) => ({ value: String(item.role_id), label: item.role_name }))} value={role} onChange={(value) => { setRole(value); setResult(null) }} searchable />
    <Select label="Команда" placeholder="Выберите команду" data={teams.map((item) => item.team_id)} value={team} onChange={(value) => { setTeam(value); setResult(null) }} />
    <Select label="Начало действия" data={Array.from({ length: Math.max(0, count - earliest + 1) }, (_, index) => ({ value: String(index + earliest), label: `Спринт ${index + earliest}` }))} value={sprint} onChange={(value) => { setSprint(value); setResult(null) }} />
    <Button disabled={runId !== defaultRunId || !role || !team || !sprint} loading={busy} onClick={calculate}>Сравнить меры</Button>
    {runId !== defaultRunId && <Text size="xs" c="dimmed">Сценарии доступны для текущего прогона.</Text>}
    {error && <Text size="sm" c="red">{error}</Text>}
    {result && <>
      <Text size="xs" c="dimmed">{result.assumptions} Предположенные навыки: {result.assumed_skill_ids.join(', ') || 'нет подтверждённых требований'}.</Text>
      <Text size="sm">Исходно в PI: {result.baseline_in_quarter} задач. Меры отсортированы по восстановленным инициативам, чистому выигрышу SP и выигрышу по срокам.</Text>
      <Table striped><Table.Thead><Table.Tr><Table.Th>Мера</Table.Th><Table.Th>Доступна с</Table.Th><Table.Th>Инициативы</Table.Th><Table.Th>SP</Table.Th><Table.Th>Срок</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>{result.ranked_measures.map((item, index) => <Table.Tr key={`${item.kind}-${index}`}>
          <Table.Td><Text size="sm" fw={500}>{item.label}</Text><Text size="xs" c="dimmed">{item.resource_cost}</Text></Table.Td>
          <Table.Td>{item.effective_sprint <= count ? `спринт ${item.effective_sprint}` : 'после PI'}</Table.Td>
          <Table.Td>{item.restored_initiatives.join(', ') || '—'}</Table.Td>
          <Table.Td>{item.net_sp_gain}</Table.Td>
          <Table.Td>{item.earlier_task_sprints} задачо-спринтов</Table.Td>
        </Table.Tr>)}</Table.Tbody>
      </Table>
      {result.ranked_measures.length === 0 && <Text size="sm" c="dimmed">Для этой роли и команды нет доступных кандидатов для обучения или перевода; наём показан, если он успеет в PI.</Text>}
    </>}
  </Stack>
}
