/**
 * Выбор прогона планировщика. В поле — коротко («Прогон 1, спринт 0»),
 * подробности (текущий ли, итог, стек) — в раскрывающемся списке.
 * По умолчанию выбран «текущий» (последний удачный).
 */
import { Badge, Group, Select, Stack, Text, Tooltip } from '@mantine/core'
import { useRun } from '../../hooks/useRun'

const outcomeLabels: Record<string, string> = {
  completed: 'Всё завершено',
  planned: 'Всё в квартале',
  partial: 'Часть перенесена',
  nothing_scheduled: 'Нет задач в плане',
}

interface Detail {
  current: boolean
  outcome: string | null
  stackUnverified: boolean
  status: string
}

export function RunSelect() {
  const { runs, runId, defaultRunId, isDefault, setRunId, isLoading } = useRun()

  const details = new Map<string, Detail>()
  const options = runs.map((r) => {
    const params = r.params && typeof r.params === 'object' && !Array.isArray(r.params) ? r.params : null
    const outcome = params?.business_outcome
    const skill = params?.skill_validation
    const stackUnverified =
      !!skill && typeof skill === 'object' && !Array.isArray(skill) && skill.status === 'unverified'
    const value = String(r.run_id)
    details.set(value, {
      current: r.run_id === defaultRunId,
      outcome: typeof outcome === 'string' ? (outcomeLabels[outcome] ?? null) : null,
      stackUnverified,
      status: r.status,
    })
    return { value, label: `Прогон ${r.run_id}, спринт ${r.as_of_sprint}` }
  })

  return (
    <Tooltip
      label={isDefault ? 'Текущий прогон: последний удачный' : 'Исторический план; справочные экраны показывают текущие данные'}
      position="bottom"
    >
      <Select
        aria-label="Прогон планировщика"
        size="sm"
        w={210}
        placeholder="Прогон"
        data={options}
        value={runId !== null ? String(runId) : null}
        onChange={(v) => setRunId(v ? Number(v) : null)}
        disabled={isLoading || runs.length === 0}
        allowDeselect={false}
        comboboxProps={{ width: 380, position: 'bottom-end' }}
        renderOption={({ option }) => {
          const d = details.get(option.value)
          return (
            <Stack gap={2} style={{ flex: 1 }}>
              <Group justify="space-between" wrap="nowrap">
                <Text fw={600}>{option.label}</Text>
                {d?.current && <Badge color="teal" variant="light">Текущий</Badge>}
                {d && d.status !== 'ok' && <Badge color="red" variant="light">{d.status}</Badge>}
              </Group>
              {(d?.outcome || d?.stackUnverified) && (
                <Text size="sm" c="dimmed">
                  {[d.outcome, d.stackUnverified ? 'Стек не подтверждён' : null].filter(Boolean).join(', ')}
                </Text>
              )}
            </Stack>
          )
        }}
        styles={{
          input: {
            fontWeight: 600,
            ...(isDefault ? {} : { borderColor: 'var(--mantine-color-yellow-6)', borderWidth: 2 }),
          },
        }}
      />
    </Tooltip>
  )
}
