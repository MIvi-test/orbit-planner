import { Accordion, Badge, Group, Paper, SimpleGrid, Skeleton, Stack, Text, Title } from '@mantine/core'
import { fmtHours, fmtSp } from '../../api/wire'
import { AsOfLabel } from '../../components/common/AsOfLabel'
import { QueryError } from '../../components/common/QueryError'
import { usePlanTeamCapacity, useTeamCapacitySp, useTeamProfile } from '../../hooks/useViews'
import { useRun } from '../../hooks/useRun'
import { num } from '../../api/wire'
import type { PlanTeamCapacityRow, TeamCapacitySpRow, TeamProfileRow } from '../../types/views'

export function ProfilesScreen() {
  const query = useTeamProfile()
  const { runId } = useRun()
  const capacity = usePlanTeamCapacity(runId)
  const basis = useTeamCapacitySp()
  const capacityByTeam = new Map((capacity.data?.items ?? []).map((item) => [item.team_id, item]))
  const basisByTeam = new Map((basis.data?.items ?? []).map((item) => [item.team_id, item]))

  if (query.isPending) {
    return (
      <Stack gap="md" maw={1200}>
        <Title order={2}>Профили</Title>
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          <Skeleton height={360} />
          <Skeleton height={360} />
        </SimpleGrid>
      </Stack>
    )
  }

  if (query.error) {
    return (
      <Stack gap="md" maw={1200}>
        <Title order={2}>Профили</Title>
        <QueryError error={query.error} title="Не удалось загрузить профили команд" />
      </Stack>
    )
  }

  const rows = query.data?.items ?? []
  return (
    <Stack gap="lg" maw={1200}>
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <div>
          <Title order={2}>Профили команд</Title>
          <Text c="dimmed" size="sm" mt={2}>
            Состав, рабочий фонд, текущая нагрузка, роли и компетенции каждой команды.
          </Text>
        </div>
        <AsOfLabel iso={query.data?.as_of ?? null} />
      </Group>

      {rows.length === 0 ? (
        <Paper withBorder p="md">
          <Text c="dimmed">Профили появятся после загрузки состава команд и бэклога.</Text>
        </Paper>
      ) : (
        <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
          {rows.map((row) => (
            <TeamProfile key={row.team_id} row={row} capacity={capacityByTeam.get(row.team_id)} basis={basisByTeam.get(row.team_id)} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  )
}

function TeamProfile({ row, capacity, basis }: { row: TeamProfileRow; capacity?: PlanTeamCapacityRow; basis?: TeamCapacitySpRow }) {
  return (
    <Paper withBorder p="lg">
      <Stack gap="lg">
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={3}>{row.team_id}</Title>
            <Text size="sm" c="dimmed">
              {row.members} человек, {fmtSp(row.fte)} FTE
            </Text>
          </div>
          {row.part_time_members > 0 && (
            <Badge variant="outline" color="gray">совместители: {row.part_time_members}</Badge>
          )}
        </Group>

        <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs">
          <Stat label="ЧЧ / спринт" value={fmtHours(row.hours_per_sprint)} />
          <Stat label="Velocity (история)" value={nullableSp(row.avg_velocity)} />
          <Stat label={capacity ? 'SP / спринт (прогон)' : 'SP / спринт'} value={nullableSp(capacity?.available_sp_per_sprint ?? row.available_sp_per_sprint)} />
          <Stat label="SP / PI (история)" value={nullableSp(row.available_sp_per_pi)} />
        </SimpleGrid>
        <CapacityBasis capacity={capacity} basis={basis} />

        <div>
          <Text size="xs" c="dimmed">Живой бэклог</Text>
          <Group gap="lg" mt={4} wrap="wrap">
            <Text size="sm"><strong className="tabular">{row.live_tasks}</strong> задач</Text>
            <Text size="sm"><strong className="tabular">{fmtSp(row.live_sp)}</strong> SP</Text>
            <Text size="sm"><strong className="tabular">{fmtHours(row.live_hh)}</strong></Text>
          </Group>
        </div>

        <RoleBlock title={`Роли в команде: ${row.roles_present.length}`} roles={row.roles_present} tone="teal" />
        <RoleBlock
          title={`Нужны бэклогу, но отсутствуют: ${row.roles_missing.length}`}
          roles={row.roles_missing}
          tone="red"
          note="Это потребность текущих задач, а не признак неполного состава команды."
        />

        <Accordion variant="contained" radius={2}>
          <Accordion.Item value="skills">
            <Accordion.Control>
              <Group justify="space-between" pr="sm" wrap="nowrap">
                <Text size="sm" fw={500}>Компетенции</Text>
                <Text size="xs" c="dimmed">{row.skills_n} всего, уникальных {row.unique_skills.length}</Text>
              </Group>
            </Accordion.Control>
            <Accordion.Panel>
              {row.unique_skills.length > 0 ? (
                <Group gap={6}>
                  {row.unique_skills.map((skill) => <Badge key={skill} color="gray" variant="light">{skill}</Badge>)}
                </Group>
              ) : (
                <Text size="sm" c="dimmed">Уникальных компетенций нет.</Text>
              )}
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      </Stack>
    </Paper>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ borderLeft: '2px solid var(--line)', paddingLeft: 10 }}>
      <Text size="xs" c="dimmed">{label}</Text>
      <Text fw={600} className="mono">{value}</Text>
    </div>
  )
}

function RoleBlock({
  title,
  roles,
  tone,
  note,
}: {
  title: string
  roles: string[]
  tone: 'teal' | 'red'
  note?: string
}) {
  return (
    <div>
      <Text size="sm" fw={500}>{title}</Text>
      {note && <Text size="xs" c="dimmed" mb={6}>{note}</Text>}
      {roles.length > 0 ? (
        <Group gap={6} mt={6}>
          {roles.map((role) => <Badge key={role} color={tone} variant="light">{role}</Badge>)}
        </Group>
      ) : (
        <Text size="sm" c="dimmed" mt={4}>—</Text>
      )}
    </div>
  )
}

function nullableSp(value: string | null): string {
  return value === null ? '—' : fmtSp(value)
}

/** Откуда взялась ёмкость: сколько наблюдений, сколько из них факт этого квартала, насколько выборка шатка. */
function CapacityBasis({ capacity, basis }: { capacity?: PlanTeamCapacityRow; basis?: TeamCapacitySpRow }) {
  if (!capacity && !basis) return null
  const points = capacity ? capacity.history_points + capacity.observed_points : basis?.history_points ?? 0
  const observed = capacity?.observed_points ?? 0
  const stale = (basis?.history_age_days ?? 0) > 90
  const thin = points < 3
  const spread = basis?.velocity_stddev ? num(basis.velocity_stddev) : null
  return (
    <Stack gap={2}>
      <Text size="xs" c="dimmed">
        Ёмкость по {points} наблюдениям
        {observed > 0 ? ` (история ${capacity?.history_points}, факт текущего квартала ${observed})` : ' (история; пересчёты добавят закрытые спринты)'}
        {spread !== null ? ` · разброс истории ±${spread.toFixed(1)} SP` : ''}.
      </Text>
      {(stale || thin) && (
        <Text size="xs" c="orange.8">
          {stale ? `Последнее наблюдение истории — ${basis?.history_to}, ${basis?.history_age_days} дн. до начала квартала. ` : ''}
          {thin ? 'Выборка малая: оценка скорости шаткая.' : ''}
        </Text>
      )}
    </Stack>
  )
}
