/**
 * Панель команды на звёздной карте: состав, фонд, бэклог, роли и совместители.
 * Это сокращённый вид; полный профиль с ёмкостью и компетенциями — на вкладке «Профили».
 */
import { Anchor, Badge, Drawer, Group, SimpleGrid, Stack, Table, Text } from '@mantine/core'
import { fmtHours, fmtSp, num } from '../../api/wire'
import { useTeamProfile } from '../../hooks/useViews'
import type { OrbitMapRow } from '../../types/views'
import { muted } from './darkStyles'

export function TeamDrawer({
  teamId,
  orbits,
  onClose,
  onSelectEngineer,
}: {
  teamId: string | null
  orbits: OrbitMapRow[]
  onClose: () => void
  onSelectEngineer: (id: string) => void
}) {
  const profileQ = useTeamProfile()
  const profile = (profileQ.data?.items ?? []).find((r) => r.team_id === teamId)
  const members = orbits.filter((o) => teamId !== null && o.teams.includes(teamId))
  const partTimers = members.filter((o) => num(o.total_capacity_rate) < 1 || o.teams.length > 1)

  return (
    <Drawer
      opened={teamId !== null}
      onClose={onClose}
      position="right"
      size="md"
      title={teamId && <span style={{ fontWeight: 700, fontFamily: 'var(--font-heading)', fontSize: 20 }}>{teamId}</span>}
      styles={{
        content: { background: 'var(--field)', color: 'var(--star)' },
        header: { background: 'var(--field)', color: 'var(--star)', borderBottom: '1px solid var(--sm-border)' },
        close: { color: 'var(--star)' },
      }}
    >
      {teamId && (
        <Stack gap="md" pt="sm">
          {profile ? (
            <SimpleGrid cols={2} spacing="xs">
              <Stat label="Людей" value={`${profile.members}`} />
              <Stat label="FTE" value={fmtSp(profile.fte)} />
              <Stat label="ЧЧ в спринт" value={fmtHours(profile.hours_per_sprint)} />
              <Stat label="Живой бэклог" value={`${profile.live_tasks} задач, ${fmtSp(profile.live_sp)} SP`} />
            </SimpleGrid>
          ) : (
            <Text size="sm" style={muted}>Профиль команды загружается…</Text>
          )}

          {profile && (
            <>
              <Section title={`Роли в команде: ${profile.roles_present.length}`}>
                <Group gap={6}>
                  {profile.roles_present.map((r) => <Badge key={r} color="teal" variant="light">{r}</Badge>)}
                </Group>
              </Section>
              {profile.roles_missing.length > 0 && (
                <Section title={`Нужны бэклогу, но отсутствуют: ${profile.roles_missing.length}`}>
                  <Group gap={6}>
                    {profile.roles_missing.map((r) => <Badge key={r} color="red" variant="light">{r}</Badge>)}
                  </Group>
                </Section>
              )}
            </>
          )}

          <Section title={`Состав: ${members.length}`}>
            <Table verticalSpacing={4} fz="sm">
              <Table.Thead>
                <Table.Tr><Table.Th>Инженер</Table.Th><Table.Th>Роль</Table.Th><Table.Th ta="right">Ставка</Table.Th></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {members.map((m) => (
                  <Table.Tr key={m.engineer_id} onClick={() => onSelectEngineer(m.engineer_id)} style={{ cursor: 'pointer' }}>
                    <Table.Td className="mono">{m.engineer_id}</Table.Td>
                    <Table.Td>{m.role_name}, {m.grade}</Table.Td>
                    <Table.Td ta="right" className="mono">
                      {fmtSp(m.total_capacity_rate)}{m.teams.length > 1 ? ' ◆' : ''}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            <Text size="sm" style={muted}>Нажмите на инженера, чтобы открыть его панель.</Text>
          </Section>

          {partTimers.length > 0 && (
            <Section title={`Совместители: ${partTimers.length}`}>
              <Text size="sm" style={muted}>Не на полную ставку или в двух командах сразу (◆ в списке выше).</Text>
              {partTimers.map((m) => (
                <Text key={m.engineer_id} size="sm">
                  <span className="mono">{m.engineer_id}</span>: {m.teams.join(' и ')}
                </Text>
              ))}
            </Section>
          )}

          <Anchor size="sm" href={`#/profiles?team=${encodeURIComponent(teamId)}`}>Полный профиль команды (ёмкость, компетенции)</Anchor>
        </Stack>
      )}
    </Drawer>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ borderLeft: '3px solid var(--sm-border)', paddingLeft: 10 }}>
      <Text size="sm" style={muted}>{label}</Text>
      <Text fw={700} className="mono">{value}</Text>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ border: '1px solid var(--sm-border)', borderRadius: 8, padding: '10px 12px' }}>
      <Text fw={700} mb={6} style={{ fontFamily: 'var(--font-heading)' }}>{title}</Text>
      <Stack gap={6}>{children}</Stack>
    </div>
  )
}
