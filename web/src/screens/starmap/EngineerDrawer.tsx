/**
 * «Где отсутствие одного сотрудника создаёт риск» (ТЗ, docs/UI_DESIGN.md
 * §5.4): задачи текущего плана без замены, компетенции-одиночки, ёмкость по
 * спринтам. `hours_own` уже умножен на множитель спринта — не пересчитываем.
 */
import { useState } from 'react'
import { Button, Drawer, Group, NumberInput, Select, Stack, Text, TextInput } from '@mantine/core'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { EngineerAbsenceRiskRow, OrbitMapRow, PlanAssignmentDetailRow, SatelliteCapacityRow } from '../../types/views'
import { fetchAbsenceScenario, fetchQualifications, postJson } from '../../api/client'
import { useRun } from '../../hooks/useRun'
import { useAuth } from '../../hooks/useAuth'
import { fmtHours, num } from '../../api/wire'
import { LEVEL_COLOR, LEVEL_WORD, shortTeam, starLevel } from './risk'
import { muted } from './darkStyles'

export function EngineerDrawer({
  orbit,
  absence,
  capacity,
  assignments,
  onClose,
}: {
  orbit: OrbitMapRow | null
  absence: EngineerAbsenceRiskRow | undefined
  capacity: SatelliteCapacityRow[]
  assignments: PlanAssignmentDetailRow[]
  onClose: () => void
}) {
  const level = orbit ? starLevel(orbit, absence) : 'ok'
  const { can, me } = useAuth()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<{ team: string; sprint: number; rate: number } | null>(null)
  const [source, setSource] = useState('')
  const [saveError, setSaveError] = useState('')
  const [busy, setBusy] = useState(false)
  const [roleId, setRoleId] = useState<string | null>(null)
  const [validFrom, setValidFrom] = useState('')
  const [qualificationSource, setQualificationSource] = useState('')
  const [reviewer, setReviewer] = useState('')
  const [qualificationMessage, setQualificationMessage] = useState('')
  const { runId } = useRun()
  const scenarioQ = useQuery({
    queryKey: ['absence-scenario', runId, orbit?.engineer_id ?? null],
    queryFn: () => fetchAbsenceScenario(orbit!.engineer_id, runId!),
    enabled: orbit !== null && runId !== null,
  })
  const qualificationsQ = useQuery<{ roles: Array<{ role_id: number; canonical_name: string }>; qualifications: Array<{
    role_id: number; role_name: string; valid_from: string; valid_until: string | null; source_text: string
  }> }>({
    queryKey: ['engineer-qualifications', orbit?.engineer_id ?? null],
    queryFn: () => fetchQualifications(orbit!.engineer_id), enabled: orbit !== null,
  })
  const bySprint = new Map<number, SatelliteCapacityRow[]>()
  capacity.forEach((c) => bySprint.set(c.sprint_no, [...(bySprint.get(c.sprint_no) ?? []), c]))
  const sprints = [...bySprint.keys()].sort((a, b) => a - b)

  const saveAvailability = async () => {
    if (!orbit || !editing) return
    setBusy(true); setSaveError('')
    try {
      await postJson('/engineers/availability', {
        engineer_id: orbit.engineer_id, team_id: editing.team, sprint_no: editing.sprint,
        available_rate: editing.rate, source_text: source,
      })
      await queryClient.invalidateQueries()
      setEditing(null); setSource('')
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Не удалось сохранить доступность')
    } finally { setBusy(false) }
  }

  const saveQualification = async () => {
    if (!orbit || !roleId) return
    setBusy(true); setQualificationMessage('')
    try {
      await postJson('/engineers/qualifications', {
        engineer_id: orbit.engineer_id, role_id: Number(roleId), valid_from: validFrom,
        source_text: qualificationSource, confirmed_by: me?.auth === 'required' ? me.name : reviewer,
      })
      await queryClient.invalidateQueries({ queryKey: ['engineer-qualifications', orbit.engineer_id] })
      setQualificationMessage('Квалификация сохранена. Разрешения на замещение роли это не даёт.')
      setQualificationSource('')
    } catch (error) {
      setQualificationMessage(error instanceof Error ? error.message : 'Не удалось сохранить квалификацию')
    } finally { setBusy(false) }
  }

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

          <Block title="Подтверждённые дополнительные квалификации">
            <Text size="xs" style={muted}>Датированная квалификация не разрешает назначать человека на другую роль без отдельного правила замещения.</Text>
            {qualificationsQ.data?.qualifications.map((item) => <Text key={`${item.role_id}-${item.valid_from}`} size="sm">
              {item.role_name}: с {item.valid_from}{item.valid_until ? ` по ${item.valid_until}` : ''} · {item.source_text}
            </Text>)}
            {can('planner') && <>
              <Select label="Дополнительная роль" searchable value={roleId} onChange={setRoleId}
                data={(qualificationsQ.data?.roles ?? []).map((item) => ({ value: String(item.role_id), label: item.canonical_name }))} />
              <TextInput type="date" label="Действует с" value={validFrom} onChange={(event) => setValidFrom(event.currentTarget.value)} />
              <TextInput label="Основание подтверждения" value={qualificationSource} onChange={(event) => setQualificationSource(event.currentTarget.value)} />
              {me?.auth !== 'required' && <TextInput label="Кто подтвердил" value={reviewer} onChange={(event) => setReviewer(event.currentTarget.value)} />}
              <Button size="xs" loading={busy} disabled={!roleId || !validFrom || !qualificationSource.trim() || (me?.auth !== 'required' && !reviewer.trim())}
                onClick={saveQualification}>Подтвердить квалификацию</Button>
              {qualificationMessage && <Text size="xs">{qualificationMessage}</Text>}
            </>}
          </Block>

          {sprints.length > 0 && (
            <Block title="Фонд и план по спринтам">
              <Text size="xs" style={muted}>Свободно = фонд − назначения выбранного прогона. Факт часов по инженеру не собирается; эти числа не являются фактом.</Text>
              <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }} className="tabular">
                <thead>
                  <tr style={muted}>
                    <th style={th}>Спринт</th>
                    {orbit.teams.map((t) => (
                      <th key={t} style={th}>
                        {shortTeam(t)}: фонд / план / свободно
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
                        const planned = assignments
                          .filter((a) => a.sprint_no === s && a.home_team_id === t)
                          .reduce((sum, a) => sum + num(a.hours), 0)
                        const available = cell ? num(cell.hours_own) : null
                        return (
                          <td key={t} style={td} className="mono">
                            {available === null ? '—' : `${available} / ${planned} / ${available - planned} ЧЧ`}
                            {cell && can('planner') && <Button variant="subtle" size="compact-xs" onClick={() => {
                              setEditing({ team: t, sprint: s, rate: num(cell.capacity_rate) }); setSource(''); setSaveError('')
                            }}>Изменить</Button>}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              {editing && <Stack gap="xs">
                <Text size="xs">{shortTeam(editing.team)}, спринт {editing.sprint}. Изменение ставки пересчитает план.</Text>
                <NumberInput label="Доступная ставка" min={0} max={1} step={0.1} decimalScale={2} value={editing.rate}
                  onChange={(value) => setEditing({ ...editing, rate: Number(value) })} />
                <TextInput label="Источник изменения" placeholder="Отпуск, дата выхода, согласованное перераспределение" value={source}
                  onChange={(event) => setSource(event.currentTarget.value)} />
                <Group><Button onClick={saveAvailability} loading={busy} disabled={!source.trim()}>Сохранить и пересчитать</Button>
                  <Button variant="subtle" onClick={() => setEditing(null)}>Отмена</Button></Group>
                {saveError && <Text size="sm" c="red">{saveError}</Text>}
              </Stack>}
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
