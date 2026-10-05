import type { ReactNode } from 'react'
import { L } from '../../components/imperium/L'
import { Group, Paper, SimpleGrid, Skeleton, Stack, Table, Text, Title, Tooltip, UnstyledButton } from '@mantine/core'
import { useRun } from '../../hooks/useRun'
import type { ScreenId } from '../../hooks/useHashRoute'
import {
  useAlerts,
  useDqIssues,
  useKpiSnapshots,
  usePlanSchedule,
  useRoleDeficitEffective,
} from '../../hooks/useViews'
import { AsOfLabel } from '../../components/common/AsOfLabel'
import { PlanSummary } from '../plan/PlanSummary'
import { fmtHours, isPositive, num } from '../../api/wire'
import type { KpiCode, KpiSnapshotRow } from '../../types/views'

const ALERT_ROWS: [string, string][] = [
  ['deadline_miss', 'Срыв срока'],
  ['role_deficit', 'Нехватка роли'],
  ['cascade_shift', 'Сдвиг по цепочке зависимостей'],
]

const KPI_TITLE: Record<KpiCode, string> = {
  pi_predictability: 'Выполнение квартального плана',
  say_do_ratio: 'Выполнение плана спринта',
  bus_factor: 'Bus factor',
}

/** Значение KPI для плитки: последний факт, а если факта нет — последний прогноз. */
function pickKpi(rows: KpiSnapshotRow[], code: KpiCode): KpiSnapshotRow | null {
  const mine = rows.filter((r) => r.kpi_code === code && r.value != null)
  const byKind = (kind: string) =>
    mine.filter((r) => r.kind === kind).sort((a, b) => b.sprint_no - a.sprint_no)[0]
  return byKind('actual') ?? byKind('forecast') ?? null
}

function kpiTone(row: KpiSnapshotRow): 'green' | 'yellow' | 'red' {
  const v = num(row.value)
  const min = row.target_min != null ? num(row.target_min) : null
  const max = row.target_max != null ? num(row.target_max) : null
  if ((min != null && v < min) || (max != null && v > max)) return v < (min ?? v) * 0.8 ? 'red' : 'yellow'
  return 'green'
}


function Legend() {
  const items: [string, string, string][] = [
    ['red', 'Плохо', 'Ниже нормы или есть блокирующие проблемы'],
    ['yellow', 'Внимание', 'Есть отклонения, нужно разобраться'],
    ['green', 'В норме', 'Значение в пределах нормы'],
    ['gray', 'Нет данных', 'Показатель ещё не рассчитан'],
    ['post', 'Без оценки', 'Просто счётчик, норма не задана'],
  ]
  return (
    <Group gap={6} wrap="wrap" justify="flex-end">
      <Text size="sm" c="dimmed">Цвета:</Text>
      {items.map(([color, title, hint]) => (
        <Tooltip key={color} label={hint} withArrow>
          <Group
            gap={6}
            wrap="nowrap"
            px={10}
            py={3}
            style={{ border: '1px solid var(--mantine-color-default-border)', borderRadius: 999, cursor: 'help' }}
          >
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: `var(--mantine-color-${color}-6)`, display: 'inline-block' }} />
            <Text size="sm">{title}</Text>
          </Group>
        </Tooltip>
      ))}
    </Group>
  )
}

function Tile({
  label,
  value,
  unit,
  hint,
  color,
  onClick,
}: {
  label: string
  value: ReactNode
  /** Мелкая приписка рядом с числом («из 37», «%»): размер числа от неё не меняется. */
  unit?: ReactNode
  hint?: ReactNode
  color?: string
  onClick?: () => void
}) {
  const body = (
    <Paper
      withBorder
      p="md"
      h="100%"
      style={{
        borderLeft: color ? `5px solid var(--mantine-color-${color}-6)` : undefined,
        background: color ? `color-mix(in srgb, var(--mantine-color-${color}-6) 9%, var(--mantine-color-body))` : undefined,
      }}
    >
      <Stack gap={6} justify="space-between" h="100%">
        <Text size="sm" c="dimmed" style={{ minHeight: '2.6em', lineHeight: 1.3 }}>
          {label}
        </Text>
        <Group gap={6} align="baseline" wrap="nowrap" style={{ height: '2.8rem' }}>
          <Text fw={700} className="mono tabular" style={{ fontSize: '2.3rem', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>
            {value}
          </Text>
          {unit && (
            <Text size="md" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
              {unit}
            </Text>
          )}
        </Group>
        <Text size="sm" c="dimmed" style={{ minHeight: '1.3em' }}>
          {hint ?? '\u00a0'}
        </Text>
      </Stack>
    </Paper>
  )
  return onClick ? (
    <UnstyledButton onClick={onClick} className="tile-link" style={{ display: 'block', height: '100%' }}>
      {body}
    </UnstyledButton>
  ) : (
    body
  )
}

/** Сводка: главные цифры квартала на одном экране, с переходом в подробные разделы. */
export function SummaryScreen({ onNavigate }: { onNavigate: (id: ScreenId) => void }) {
  const { runId } = useRun()
  const kpiQ = useKpiSnapshots(runId)
  const alertsQ = useAlerts(runId)
  const scheduleQ = usePlanSchedule(runId)
  const deficitQ = useRoleDeficitEffective()
  const dqQ = useDqIssues()

  if ([kpiQ, alertsQ, scheduleQ].some((q) => q.isPending)) {
    return (
      <Stack gap="md">
        <Title order={2}><L>Сводка</L></Title>
        <Skeleton height={120} />
        <Skeleton height={240} />
      </Stack>
    )
  }

  const kpiRows = kpiQ.data?.items ?? []
  const alerts = alertsQ.data?.items ?? []
  const schedule = scheduleQ.data?.items ?? []
  const deficits = (deficitQ.data?.items ?? [])
    .filter((r) => isPositive(r.gap_hh))
    .sort((a, b) => num(b.gap_hh) - num(a.gap_hh))
  const dq = dqQ.data?.items ?? []
  const dqOpen = dq.filter((r) => r.review_status === 'open' || r.review_status === 'reopened')
  const dqBlocking = dqOpen.filter((r) => r.is_blocking).length

  const byType = (t: string) => alerts.filter((a) => a.alert_type === t).length
  const alertsOf = (t: string, level: string) => alerts.filter((a) => a.alert_type === t && a.level === level).length
  const red = alerts.filter((a) => a.level === 'red').length
  const kpis = (['pi_predictability', 'say_do_ratio', 'bus_factor'] as KpiCode[]).map((c) => ({
    code: c,
    row: pickKpi(kpiRows, c),
  }))
  const inQuarter = schedule.filter((s) => s.decision === 'in_quarter').length

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <div>
          <Title order={2}><L>Сводка</L></Title>
          <Text c="dimmed" mt={2}>
            Главное по кварталу: что в плане, что под угрозой и что нужно решить. Подробности — по плиткам и в разделах слева.
          </Text>
        </div>
        <AsOfLabel iso={alertsQ.data?.as_of ?? null} />
      </Group>

      <Stack gap="xs">
      <Legend />
      <SimpleGrid cols={{ base: 2, md: 3, xl: 6 }} spacing="md">
        <Tile
          label="Задач в квартале"
          value={schedule.length ? inQuarter : '—'}
          unit={schedule.length ? `из ${schedule.length}` : undefined}
          hint={schedule.length ? `Вошло в план: ${Math.round((inQuarter / schedule.length) * 100)}%` : 'Нет расписания'}
          color="post"
          onClick={() => onNavigate('plan')}
        />
        {kpis.map(({ code, row }) => (
          <Tile
            key={code}
            label={KPI_TITLE[code]}
            value={row ? (code === 'bus_factor' ? num(row.value) : Math.round(num(row.value))) : 'Н/д'}
            unit={row ? (code === 'bus_factor' ? 'чел.' : '%') : undefined}
            hint={row ? (row.kind === 'actual' ? 'Факт' : 'Прогноз') : 'Нет данных'}
            color={row ? kpiTone(row) : 'gray'}
            onClick={() => onNavigate('kpi')}
          />
        ))}
        <Tile
          label="Рисков в прогоне"
          value={alerts.length}
          hint={`Критичных: ${red}`}
          color={red > 0 ? 'red' : alerts.length > 0 ? 'yellow' : 'green'}
          onClick={() => onNavigate('risks')}
        />
        <Tile
          label="Вопросов к данным"
          value={dqOpen.length}
          hint={dqBlocking > 0 ? `Блокируют план: ${dqBlocking}` : 'Блокирующих нет'}
          color={dqBlocking > 0 ? 'red' : dqOpen.length > 0 ? 'yellow' : 'green'}
          onClick={() => onNavigate('data')}
        />
      </SimpleGrid>
      </Stack>

      <PlanSummary schedule={schedule} />

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
        <Paper withBorder p="md">
          <Group justify="space-between" mb="xs">
            <Title order={4}>Что под угрозой</Title>
            <UnstyledButton onClick={() => onNavigate('risks')} className="text-link">
              <Text size="sm" c="inherit">
                все риски →
              </Text>
            </UnstyledButton>
          </Group>
          {alerts.length === 0 ? (
            <Text c="dimmed">Рисков в этом прогоне нет.</Text>
          ) : (
            <Table verticalSpacing={6} highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Тип</Table.Th>
                  <Table.Th ta="right" w={90}>Всего</Table.Th>
                  <Table.Th ta="right" w={110}>Критичных</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {ALERT_ROWS.map(([type, title]) => (
                  <Table.Tr key={type}>
                    <Table.Td>{title}</Table.Td>
                    <Table.Td ta="right" className="mono">{byType(type)}</Table.Td>
                    <Table.Td ta="right" className="mono" c={alertsOf(type, 'red') ? 'red' : 'dimmed'}>
                      {alertsOf(type, 'red')}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Paper>

        <Paper withBorder p="md">
          <Group justify="space-between" mb="xs">
            <Title order={4}>Где не хватает людей</Title>
            <UnstyledButton onClick={() => onNavigate('roles')} className="text-link">
              <Text size="sm" c="inherit">
                роли и ёмкость →
              </Text>
            </UnstyledButton>
          </Group>
          {deficits.length === 0 ? (
            <Text c="dimmed">Дефицита по ролям нет.</Text>
          ) : (
            <Table verticalSpacing={6} highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Роль</Table.Th>
                  <Table.Th>Команда</Table.Th>
                  <Table.Th ta="right">Не хватает</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {deficits.slice(0, 8).map((r) => (
                  <Table.Tr key={`${r.team_id}-${r.role_name}`}>
                    <Table.Td>{r.role_name}</Table.Td>
                    <Table.Td className="mono">{r.team_id}</Table.Td>
                    <Table.Td ta="right" className="mono" c="red" fw={600}>−{fmtHours(r.gap_hh)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
          {deficits.length > 8 && (
            <Text size="sm" c="dimmed" mt={6}>и ещё {deficits.length - 8} — на экране «Роли и ёмкость»</Text>
          )}
        </Paper>
      </SimpleGrid>
    </Stack>
  )
}
