import { useEffect } from 'react'
import { L } from '../../components/imperium/L'
import { Accordion, Anchor, Badge, Group, Paper, Popover, SimpleGrid, Skeleton, Stack, Table, Text, Title, UnstyledButton } from '@mantine/core'
import { IconChevronDown } from '@tabler/icons-react'
import { useHashQuery } from '../../hooks/useHashRoute'
import { fmtHours, fmtSp } from '../../api/wire'
import { AsOfLabel } from '../../components/common/AsOfLabel'
import { QueryError } from '../../components/common/QueryError'
import { useOrbitMap, usePlanTeamCapacity, useTeamCapacitySp, useTeamProfile } from '../../hooks/useViews'
import { useRun } from '../../hooks/useRun'
import { num } from '../../api/wire'
import type { OrbitMapRow, PlanTeamCapacityRow, TeamCapacitySpRow, TeamProfileRow } from '../../types/views'

export function ProfilesScreen() {
  const query = useTeamProfile()
  const orbitQ = useOrbitMap()
  const focusTeam = useHashQuery().get('team')
  const { runId } = useRun()
  const capacity = usePlanTeamCapacity(runId)
  const basis = useTeamCapacitySp()
  const capacityByTeam = new Map((capacity.data?.items ?? []).map((item) => [item.team_id, item]))
  const basisByTeam = new Map((basis.data?.items ?? []).map((item) => [item.team_id, item]))

  // Переход со звёздной карты: прокручиваем к нужной команде.
  const loaded = !query.isPending
  useEffect(() => {
    if (!focusTeam || !loaded) return
    document.getElementById(`team-${focusTeam}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [focusTeam, loaded])

  if (query.isPending) {
    return (
      <Stack gap="md">
        <Title order={2}><L>Профили</L></Title>
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          <Skeleton height={360} />
          <Skeleton height={360} />
        </SimpleGrid>
      </Stack>
    )
  }

  if (query.error) {
    return (
      <Stack gap="md">
        <Title order={2}><L>Профили</L></Title>
        <QueryError error={query.error} title="Не удалось загрузить профили команд" />
      </Stack>
    )
  }

  const rows = query.data?.items ?? []
  const engineers = orbitQ.data?.items ?? []
  return (
    <Stack gap="lg">
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
            <TeamProfile key={row.team_id} row={row} capacity={capacityByTeam.get(row.team_id)} basis={basisByTeam.get(row.team_id)} focused={focusTeam === row.team_id} engineers={engineers} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  )
}

function TeamProfile({ row, capacity, basis, focused, engineers }: { row: TeamProfileRow; capacity?: PlanTeamCapacityRow; basis?: TeamCapacitySpRow; focused: boolean; engineers: OrbitMapRow[] }) {
  const partTimers = engineers.filter((e) => e.teams.includes(row.team_id) && (num(e.total_capacity_rate) < 1 || e.teams.length > 1))
  return (
    <Paper withBorder p="lg" id={`team-${row.team_id}`} style={focused ? { outline: '3px solid var(--mantine-primary-color-filled)', outlineOffset: 2 } : undefined}>
      <Stack gap="lg">
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={3}>{row.team_id}</Title>
            <Text size="sm" c="dimmed">
              {row.members} человек, {fmtSp(row.fte)} FTE
            </Text>
            <Anchor size="sm" href="#/starmap">Показать на звёздной карте</Anchor>
          </div>
          {row.part_time_members > 0 && (
            <Popover position="bottom-end" shadow="md" withArrow>
              <Popover.Target>
                <UnstyledButton aria-label="Показать совместителей команды">
                  <Badge variant="outline" color="gray" size="lg" style={{ cursor: 'pointer', textTransform: 'none' }} rightSection={<IconChevronDown size={14} />}>
                    Совместители: {row.part_time_members}
                  </Badge>
                </UnstyledButton>
              </Popover.Target>
              <Popover.Dropdown>
                <Text size="sm" c="dimmed" mb={6}>Работают в команде не на полную ставку или сразу в двух командах</Text>
                {partTimers.length === 0 ? (
                  <Text size="sm">Список недоступен: нет данных об орбитах.</Text>
                ) : (
                  <Table verticalSpacing={4} fz="sm">
                    <Table.Thead>
                      <Table.Tr><Table.Th>Инженер</Table.Th><Table.Th>Роль</Table.Th><Table.Th ta="right">Ставка</Table.Th><Table.Th>Команды</Table.Th></Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {partTimers.map((e) => (
                        <Table.Tr key={e.engineer_id}>
                          <Table.Td className="mono">{e.engineer_id}</Table.Td>
                          <Table.Td>{e.role_name}, {e.grade}</Table.Td>
                          <Table.Td ta="right" className="mono">{fmtSp(e.total_capacity_rate)}</Table.Td>
                          <Table.Td>{e.teams.join(', ')}</Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                )}
              </Popover.Dropdown>
            </Popover>
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
