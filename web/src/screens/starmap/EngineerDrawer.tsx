/**
 * «Где отсутствие одного сотрудника создаёт риск» (ТЗ, docs/UI_DESIGN.md
 * §5.4): задачи текущего плана без замены, компетенции-одиночки, ёмкость по
 * спринтам. `hours_own` уже умножен на множитель спринта — не пересчитываем.
 */
import { Drawer, Stack, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import type { EngineerAbsenceRiskRow, OrbitMapRow, SatelliteCapacityRow } from '../../types/views'
import { fetchAbsenceScenario } from '../../api/client'
import { useRun } from '../../hooks/useRun'
import { fmtHours, num } from '../../api/wire'
import { LEVEL_COLOR, LEVEL_WORD, shortTeam, starLevel } from './risk'
import { muted } from './darkStyles'

export function EngineerDrawer({
  orbit,
  absence,
  capacity,
  onClose,
}: {
  orbit: OrbitMapRow | null
  absence: EngineerAbsenceRiskRow | undefined
  capacity: SatelliteCapacityRow[]
  onClose: () => void
}) {
  const level = orbit ? starLevel(orbit, absence) : 'ok'
  const { runId } = useRun()
  const scenarioQ = useQuery({
    queryKey: ['absence-scenario', runId, orbit?.engineer_id ?? null],
    queryFn: () => fetchAbsenceScenario(orbit!.engineer_id, runId!),
    enabled: orbit !== null && runId !== null,
  })
  const bySprint = new Map<number, SatelliteCapacityRow[]>()
  capacity.forEach((c) => bySprint.set(c.sprint_no, [...(bySprint.get(c.sprint_no) ?? []), c]))
  const sprints = [...bySprint.keys()].sort((a, b) => a - b)

  return (
    <Drawer
      opened={orbit !== null}
      onClose={onClose}
      position="right"
      size="md"
      title={orbit && <span className="mono" style={{ fontWeight: 600 }}>{orbit.engineer_id}</span>}
      styles={{
        content: { background: 'var(--field)', color: 'var(--star)' },
        header: { background: 'var(--field)', color: 'var(--star)', borderBottom: '1px solid rgba(127,166,217,0.2)' },
        close: { color: 'var(--star)' },
      }}
    >
      {orbit && (
        <Stack gap="md" pt="sm">
          <div>
            <Text fw={500}>{orbit.role_name}</Text>
            <Text size="sm" style={muted}>
              {orbit.grade} · {orbit.teams.map(shortTeam).join(' и ')}
              {orbit.teams.length > 1 ? ' — ставка поделена между двумя командами' : ''}
            </Text>
          </div>

          <div style={{ borderLeft: `4px solid ${LEVEL_COLOR[level]}`, paddingLeft: 10 }}>
            <Text size="sm" fw={600} style={{ color: LEVEL_COLOR[level] }}>
              {LEVEL_WORD[level]}
            </Text>
            <Text size="sm">
              {absence?.risk ?? orbit.risk}. Специалистов этой роли в компании:{' '}
              <b className="mono">{absence?.role_bus_factor ?? orbit.bus_factor}</b>.
            </Text>
          </div>

          <Block title="Сценарий отсутствия до конца PI">
            {scenarioQ.isPending && <Text size="sm" style={muted}>Пересчитываем план без инженера…</Text>}
            {scenarioQ.isError && (
              <Text size="sm" style={muted}>
                Сценарий недоступен: {scenarioQ.error instanceof Error ? scenarioQ.error.message : 'ошибка расчёта'}.
              </Text>
            )}
            {scenarioQ.data && (
              <Stack gap={6}>
                <Text size="sm" style={muted}>{scenarioQ.data.assumptions}</Text>
                {scenarioQ.data.affected_tasks.length === 0 ? (
                  <Text size="sm">В этом пересчёте сроки и решения задач не ухудшились.</Text>
                ) : (
                  <>
                    <Text size="sm">
                      Затронуто задач: <b>{scenarioQ.data.affected_tasks.length}</b>; дополнительно
                      перенесено <b>{fmtHours(scenarioQ.data.extra_deferred_hh)}</b>.
                    </Text>
                    {scenarioQ.data.affected_tasks.map((task) => (
                      <Text size="sm" key={task.task_id}>
                        <span className="mono">{task.task_id}</span>: {task.scenario_end_sprint === null
                          ? 'вне квартала'
                          : `сдвиг окончания на ${task.delay_sprints} спринт(а)`}.
                      </Text>
                    ))}
                    {scenarioQ.data.affected_chain.length > 0 && (
                      <Text size="sm">Затронутая цепочка: {scenarioQ.data.affected_chain
                        .map((edge) => `${edge.blocking} → ${edge.blocked}`).join(', ')}.</Text>
                    )}
                    {scenarioQ.data.lost_initiatives.length > 0 && (
                      <Text size="sm">Теряют завершение в PI: {scenarioQ.data.lost_initiatives.join(', ')}.</Text>
                    )}
                  </>
                )}
              </Stack>
            )}
          </Block>

          {absence && absence.tasks_backup_unverified.length > 0 && (
            <Text size="sm" style={muted}>
              Стек ещё не подтверждён для задач: {absence.tasks_backup_unverified.join(', ')}.
              Доступность замены по ним оценивает сценарий выше.
            </Text>
          )}

          {absence && absence.unique_critical_skills.length > 0 && (
            <Block title="Компетенции, которые не подхватит никто">
              <Tags items={absence.unique_critical_skills} color="var(--flare)" />
            </Block>
          )}
          {absence && absence.unique_skills.length > absence.unique_critical_skills.length && (
            <Block title="Компетенции только у него">
              <Tags
                items={absence.unique_skills.filter((s) => !absence.unique_critical_skills.includes(s))}
                color="var(--ember)"
              />
            </Block>
          )}

          <Block title={`Заявленный стек (${orbit.skills.length})`}>
            <Tags items={orbit.skills} color="var(--orbit)" />
          </Block>

          {sprints.length > 0 && (
            <Block title="Ёмкость по спринтам">
              <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }} className="tabular">
                <thead>
                  <tr style={muted}>
                    <th style={th}>Спринт</th>
                    {orbit.teams.map((t) => (
                      <th key={t} style={th}>
                        {shortTeam(t)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sprints.map((s) => (
                    <tr key={s}>
                      <td style={td} className="mono">
                        {s}
                      </td>
                      {orbit.teams.map((t) => {
                        const cell = bySprint.get(s)?.find((c) => c.team_id === t)
                        return (
                          <td key={t} style={td} className="mono">
                            {cell ? `${num(cell.hours_own)} ЧЧ` : '—'}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Block>
          )}
        </Stack>
      )}
    </Drawer>
  )
}

const th: React.CSSProperties = { textAlign: 'left', fontWeight: 500, padding: '4px 6px', borderBottom: '1px solid rgba(127,166,217,0.25)' }
const td: React.CSSProperties = { padding: '4px 6px', borderBottom: '1px solid rgba(127,166,217,0.12)' }

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Stack gap={6}>
      <Text size="sm" fw={500}>
        {title}
      </Text>
      {children}
    </Stack>
  )
}

function Tags({ items, color }: { items: string[]; color: string }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {items.map((s) => (
        <span key={s} style={{ fontSize: 12, padding: '2px 8px', border: `1px solid ${color}`, borderRadius: 2 }}>
          {s}
        </span>
      ))}
    </div>
  )
}
