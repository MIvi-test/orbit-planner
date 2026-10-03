import { Group, Paper, SimpleGrid, Stack, Text } from '@mantine/core'
import type { PlanTaskScheduleRow } from '../../types/views'

/** Что делать с причиной переноса: от диагноза — к действию (X-2). */
const ACTION: Record<string, { title: string; action: string }> = {
  ROLE_NOT_IN_STAFF: { title: 'Нет роли в штате', action: 'нанять или дообучить сотрудника (экран «Роли и ёмкость»)' },
  SKILL_UNAVAILABLE: { title: 'Нет подтверждённого стека', action: 'подтвердить стек задачи или усилить команду' },
  BLOCKED_BY_DEFERRED: { title: 'Ждёт блокирующую', action: 'разблокировать задачу-предшественника' },
  ETC_REQUIRED: { title: 'Нужен остаток работ', action: 'подтвердить ETC в факте спринта' },
  ROLE_HOURS_EXHAUSTED: { title: 'Не хватило часов', action: 'добавить ставку роли или сократить объём' },
  TEAM_SP_EXHAUSTED: { title: 'Не хватило ёмкости SP', action: 'пересогласовать объём или усилить команду' },
  GRAPH_HORIZON: { title: 'Цепочка за горизонтом', action: 'сократить цепочку зависимостей или перенести на следующий PI' },
  INITIATIVE_ATOMIC: { title: 'Инициатива целиком', action: 'решить, нужна ли частичная поставка' },
  PI_CLOSED: { title: 'Квартал завершён', action: 'остаток уходит в следующий PI' },
}

/** Сводка над Гантом: что в квартале, что не вошло, почему и что с этим делать. */
export function PlanSummary({ schedule }: { schedule: PlanTaskScheduleRow[] }) {
  const inQuarter = schedule.filter((s) => s.decision === 'in_quarter').length
  const reasons = new Map<string, number>()
  schedule.filter((s) => s.decision !== 'in_quarter').forEach((s) => {
    const code = s.reason_code ?? 'UNKNOWN'
    reasons.set(code, (reasons.get(code) ?? 0) + 1)
  })
  const ranked = [...reasons.entries()].sort((a, b) => b[1] - a[1])
  const out = schedule.length - inQuarter
  if (schedule.length === 0) return null
  return (
    <Paper withBorder p="md">
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="lg">
        <Stack gap={2}>
          <Text size="xs" c="dimmed">В квартале</Text>
          <Text fw={600} style={{ fontSize: 32, lineHeight: 1 }} className="mono">{inQuarter} <Text span size="sm" c="dimmed">из {schedule.length}</Text></Text>
        </Stack>
        <Stack gap={2}>
          <Text size="xs" c="dimmed">Не вошло ({out}) — почему</Text>
          {ranked.length === 0 ? <Text size="sm">Всё поместилось.</Text> : ranked.map(([code, n]) => (
            <Group key={code} gap={6} wrap="nowrap"><Text size="sm" className="mono">{n}</Text><Text size="sm">{ACTION[code]?.title ?? code}</Text></Group>
          ))}
        </Stack>
        <Stack gap={2}>
          <Text size="xs" c="dimmed">Что делать</Text>
          {ranked.length === 0 ? <Text size="sm">Действий не требуется.</Text> : ranked.slice(0, 3).map(([code]) => (
            <Text key={code} size="sm">• {ACTION[code]?.action ?? 'разобрать причину в карточке задачи'}</Text>
          ))}
        </Stack>
      </SimpleGrid>
    </Paper>
  )
}
