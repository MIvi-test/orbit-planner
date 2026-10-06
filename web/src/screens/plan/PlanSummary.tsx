import { Group, Paper, Stack, Table, Text } from '@mantine/core'
import type { PlanTaskScheduleRow } from '../../types/views'

/** Что делать с причиной переноса: от диагноза — к действию (X-2). */
const ACTION: Record<string, { title: string; action: string }> = {
  ROLE_NOT_IN_STAFF: { title: 'Нет роли в штате', action: 'Нанять или дообучить сотрудника (экран «Роли и ёмкость»)' },
  SKILL_UNAVAILABLE: { title: 'Нет подтверждённого стека', action: 'Подтвердить стек задачи или усилить команду' },
  BLOCKED_BY_DEFERRED: { title: 'Ждёт блокирующую', action: 'Разблокировать задачу-предшественника' },
  ETC_REQUIRED: { title: 'Нужен остаток работ', action: 'Подтвердить ETC в факте спринта' },
  ROLE_HOURS_EXHAUSTED: { title: 'Не хватило часов', action: 'Добавить ставку роли или сократить объём' },
  TEAM_SP_EXHAUSTED: { title: 'Не хватило ёмкости SP', action: 'Пересогласовать объём или усилить команду' },
  GRAPH_HORIZON: { title: 'Цепочка за горизонтом', action: 'Сократить цепочку зависимостей или перенести на следующий PI' },
  INITIATIVE_ATOMIC: { title: 'Инициатива целиком', action: 'Решить, нужна ли частичная поставка' },
  PI_CLOSED: { title: 'Квартал завершён', action: 'Остаток уходит в следующий PI' },
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
  const share = inQuarter / schedule.length
  const tone = 'post'
  return (
    <Paper withBorder p="md">
      <Group align="stretch" gap="xl" wrap="wrap">
        <Stack
          gap={2}
          miw={190}
          p="md"
          style={{
            borderLeft: `5px solid var(--mantine-color-${tone}-6)`,
            background: `color-mix(in srgb, var(--mantine-color-${tone}-6) 10%, transparent)`,
            borderRadius: 4,
          }}
        >
          <Text size="sm" c="dimmed">В квартале</Text>
          <Text fw={600} style={{ fontSize: '2.2rem', lineHeight: 1 }} className="mono">
            {inQuarter} <Text span size="md" c="dimmed">из {schedule.length}</Text>
          </Text>
          <Text size="sm" c="dimmed">Не вошло: {out} ({Math.round(share * 100)}% в плане)</Text>
        </Stack>
        <div style={{ flex: 1, minWidth: 320 }}>
          <Text fw={600} mb={6}>Почему задачи не вошли в квартал</Text>
          {ranked.length === 0 ? (
            <Text>Всё поместилось, действий не требуется.</Text>
          ) : (
            <Table verticalSpacing={6} highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th w={90}>Задач</Table.Th>
                  <Table.Th>Причина</Table.Th>
                  <Table.Th>Что делать</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {ranked.map(([code, n]) => (
                  <Table.Tr key={code}>
                    <Table.Td className="mono" fw={600}>{n}</Table.Td>
                    <Table.Td>{ACTION[code]?.title ?? code}</Table.Td>
                    <Table.Td>{ACTION[code]?.action ?? 'Разобрать причину в карточке задачи'}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </div>
      </Group>
    </Paper>
  )
}
