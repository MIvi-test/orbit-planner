/**
 * Причина решения — готовый текст (docs/UI_DESIGN.md §8): `reason_text`
 * показывается как есть, не пересказывается и не сокращается.
 */
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { Badge, Button, Drawer, Group, List, Select, Stack, Table, Text, TextInput } from '@mantine/core'
import type { PlanAssignmentDetailRow, PlanDependencyBoundRow, PlanGoalOutcomeRow, PlanRoleDemandSnapshotRow, PlanTaskProgressRow, PlanTaskScheduleRow, TaskStateRow, TaskRow } from '../../types/views'
import { fmtHours, fmtSp, isNegative } from '../../api/wire'
import { confirmTaskGoal } from '../../api/goals'
import { useRun } from '../../hooks/useRun'
import { useAuth } from '../../hooks/useAuth'

const DECISION_LABEL: Record<string, string> = {
  in_quarter: 'В квартале',
  deferred_next_pi: 'Перенесена',
  cancelled: 'Рекомендована к отмене',
}

const DECISION_COLOR: Record<string, string> = {
  in_quarter: 'var(--route-text)',
  deferred_next_pi: 'var(--wax-text)',
  cancelled: 'var(--stamp)',
}

export function TaskDetailDrawer({
  task,
  state,
  roleDemand,
  progress,
  dependencyBound,
  goalOutcome,
  schedule,
  assignments,
  onClose,
}: {
  task: TaskRow | null
  state: TaskStateRow | undefined
  roleDemand: PlanRoleDemandSnapshotRow[]
  progress: PlanTaskProgressRow[]
  dependencyBound: PlanDependencyBoundRow | undefined
  goalOutcome: PlanGoalOutcomeRow | undefined
  schedule: PlanTaskScheduleRow | undefined
  assignments: PlanAssignmentDetailRow[]
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const { isDefault, setRunId } = useRun()
  const { me, can } = useAuth()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [closureCode, setClosureCode] = useState<string | null>('ACHIEVED')
  const [goalCode, setGoalCode] = useState<string | null>(null)
  const [confirmedBy, setConfirmedBy] = useState('')
  const [confirmationNote, setConfirmationNote] = useState('')
  const [confirmBusy, setConfirmBusy] = useState(false)

  async function saveConfirmation() {
    if (!task || !closureCode) return
    setConfirmBusy(true)
    try {
      const result = await confirmTaskGoal(task.task_id, closureCode,
        closureCode === 'ACHIEVED' ? goalCode : null,
        // При включённой авторизации сервер подставляет вошедшего пользователя сам.
        me?.auth === 'required' ? me.name : confirmedBy, confirmationNote)
      await queryClient.invalidateQueries()
      setRunId(result.plan.run_id)
      setConfirmOpen(false)
      notifications.show({ color: 'teal', title: 'Бизнес результат подтверждён',
        message: `План пересчитан: прогон ${result.plan.run_id}.` })
    } catch (error) {
      notifications.show({ color: 'red', title: 'Не удалось подтвердить результат',
        message: error instanceof Error ? error.message : String(error) })
    } finally {
      setConfirmBusy(false)
    }
  }

  return (
    <Drawer
      opened={task !== null}
      onClose={onClose}
      position="right"
      size="md"
      title={
        task && (
          <Group gap="xs">
            <Text fw={600} className="mono">
              {task.task_id}
            </Text>
            {schedule && (
              <Badge
                variant="light"
                styles={{ root: { color: DECISION_COLOR[schedule.decision], background: 'transparent', border: `1px solid ${DECISION_COLOR[schedule.decision]}` } }}
              >
                {DECISION_LABEL[schedule.decision] ?? schedule.decision}
              </Badge>
            )}
          </Group>
        )
      }
    >
      {task && (
        <Stack gap="md">
          <div>
            <Text fw={500}>{task.summary}</Text>
            <Text size="sm" c="dimmed">
              {task.prodf_id} · {task.team_id} · {fmtSp(task.estimation_sp)} SP
            </Text>
          </div>

          {schedule?.reason_text && (
            <Stack gap={4}>
              <Text size="sm" fw={500}>
                Почему это решение
              </Text>
              <Text size="sm">{schedule.reason_text}</Text>
            </Stack>
          )}

          {dependencyBound && dependencyBound.earliest_start_sprint > 1 && (
            <Text size="sm" c="dimmed">
              По зависимостям этого прогона старт возможен не раньше спринта {dependencyBound.earliest_start_sprint}.
            </Text>
          )}

          {goalOutcome && (
            <Stack gap={4}>
              <Text size="sm" fw={500}>Цель и результат</Text>
              <Text size="sm">Исходная цель исполнителя: {goalOutcome.result_executor ?? 'не указана'}
                {goalOutcome.requested_goal_label ? ` · ${goalOutcome.requested_goal_label}` : ''}</Text>
              <Text size="sm">Цель заказчика: {goalOutcome.result_customer ?? 'не указана'}</Text>
              <Text size="sm">Предложение плана: {goalOutcome.proposal_action === 'recommend_cancel'
                ? 'рекомендовать отмену, без согласия заказчика'
                : goalOutcome.proposed_goal_label ?? 'решение не требуется'}</Text>
              <Text size="sm">Подтверждённый результат: {goalOutcome.confirmed_closure_label ?? 'не подтверждён'}
                {goalOutcome.confirmed_goal_label ? ` · ${goalOutcome.confirmed_goal_label}` : ''}</Text>
              {isDefault && can('planner') && goalOutcome.status === 'Done' && (
                <>
                  <Button size="xs" variant="subtle" onClick={() => setConfirmOpen(!confirmOpen)}>
                    Подтвердить или исправить бизнес результат
                  </Button>
                  {confirmOpen && (
                    <Stack gap="xs">
                      <Select label="Итог" value={closureCode} onChange={setClosureCode}
                        data={[{ value: 'ACHIEVED', label: 'Цель достигнута' },
                          { value: 'NOT_ACHIEVED', label: 'Цель не достигнута' },
                          { value: 'CANCELLED_BY_CUSTOMER', label: 'Отменено заказчиком' }]} />
                      {closureCode === 'ACHIEVED' && <Select label="Достигнутый этап" value={goalCode}
                        onChange={setGoalCode} data={[1, 2, 3, 4, 5, 6].map((n) => ({ value: `R${n}`, label: `R${n}` }))} />}
                      {me?.auth === 'off'
                        ? <TextInput label="Кто подтвердил" value={confirmedBy}
                            onChange={(event) => setConfirmedBy(event.currentTarget.value)} />
                        : <Text size="xs" c="dimmed">Подтверждает: {me?.name}</Text>}
                      <TextInput label="Основание" value={confirmationNote}
                        onChange={(event) => setConfirmationNote(event.currentTarget.value)} />
                      <Button size="xs" loading={confirmBusy} onClick={saveConfirmation}>Сохранить подтверждение</Button>
                    </Stack>
                  )}
                </>
              )}
            </Stack>
          )}

          {state && (
            <Stack gap={4}>
              <Text size="sm" fw={500}>
                Состояние на момент прогона
              </Text>
              <Text size="sm" c="dimmed">
                {state.status} · остаток: {fmtHours(state.remaining_hh)} и {fmtSp(state.remaining_sp)} SP
                {task.estimated_hh_declared !== null && task.estimated_hh_matrix_total !== null && task.estimated_hh_declared !== task.estimated_hh_matrix_total && (
                  <>
                    {' '}
                    · оценка спорная: столбец матрицы {task.estimated_hh_effective} ЧЧ, в
                    исходнике {task.estimated_hh_declared} ЧЧ
                  </>
                )}
              </Text>
            </Stack>
          )}

          {roleDemand.length > 0 && (
            <Stack gap={4}>
              <Text size="sm" fw={500}>Остаток по ролям на момент прогона</Text>
              {roleDemand.map((row) => (
                <Text key={row.role_id} size="sm">{row.role_name}: {fmtHours(row.needed_hours)}</Text>
              ))}
            </Stack>
          )}

          {progress.length > 0 && (
            <Stack gap={4}>
              <Text size="sm" fw={500}>Работа по спринтам</Text>
              <Text size="xs" c="dimmed">SP — отдельный бюджет команды; перевод SP в часы не применяется. Результат достигается после последнего спринта с часами или SP.</Text>
              {progress.map((row) => (
                <Text key={row.sprint_no} size="sm">
                  Спринт {row.sprint_no}: {fmtHours(row.assigned_hours)}, {fmtSp(row.sp)} SP
                  {row.progress_basis === 'team_sp_only' ? ' · только бюджет SP команды' : ''}
                  {row.progress_basis === 'engineer_hours_only' ? ' · только работа инженеров' : ''}
                </Text>
              ))}
            </Stack>
          )}

          {assignments.length > 0 && (
            <Stack gap={4}>
              <Text size="sm" fw={500}>
                Кем закрыто
              </Text>
              <Table.ScrollContainer minWidth={360}>
                <Table verticalSpacing={4} fz="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Спринт</Table.Th>
                      <Table.Th>Инженер</Table.Th>
                      <Table.Th>Роль</Table.Th>
                      <Table.Th>Часы</Table.Th>
                      <Table.Th>Заём</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {assignments
                      .slice()
                      .sort((a, b) => a.sprint_no - b.sprint_no)
                      .map((a, i) => (
                        <Table.Tr key={i}>
                          <Table.Td className="mono">{a.sprint_no}</Table.Td>
                          <Table.Td className="mono">{a.engineer_id}</Table.Td>
                          <Table.Td>{a.served_role}</Table.Td>
                          <Table.Td className="tabular">{a.hours}</Table.Td>
                          <Table.Td>
                            {a.is_loan ? (
                              <Text size="xs" c="var(--wax-text)">
                                {a.home_team_id} → {a.serving_team_id}
                              </Text>
                            ) : (
                              '—'
                            )}
                          </Table.Td>
                        </Table.Tr>
                      ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </Stack>
          )}

          {schedule?.reason_details && typeof schedule.reason_details === 'object' && (
            <ReasonDetails details={schedule.reason_details as Record<string, unknown>} />
          )}
        </Stack>
      )}
    </Drawer>
  )
}

function ReasonDetails({ details }: { details: Record<string, unknown> }) {
  const shortages = details.shortages
  const missingRoles = details.missing_roles
  const spBySprint = details.sp_by_sprint as Record<string, string> | undefined

  return (
    <Stack gap={8}>
      {Array.isArray(missingRoles) && missingRoles.length > 0 && (
        <Stack gap={2}>
          <Text size="sm" fw={500}>
            Роли, которых нет в штате
          </Text>
          <List size="sm">
            {missingRoles.map((m: { role: string; hours: string }, i: number) => (
              <List.Item key={i}>
                {m.role} — {fmtHours(m.hours)}
              </List.Item>
            ))}
          </List>
        </Stack>
      )}
      {Array.isArray(shortages) && shortages.length > 0 && (
        <Stack gap={2}>
          <Text size="sm" fw={500}>
            Не хватило часов
          </Text>
          <List size="sm">
            {shortages.map((s: { role: string; need_hh: string; free_hh: string }, i: number) => (
              <List.Item key={i}>
                {s.role}: нужно {fmtHours(s.need_hh)}, свободно {fmtHours(s.free_hh)}
              </List.Item>
            ))}
          </List>
        </Stack>
      )}
      {spBySprint && Object.keys(spBySprint).length > 1 && (
        <Stack gap={2}>
          <Text size="sm" fw={500}>
            Story Points по спринтам
          </Text>
          <Text size="sm" className="tabular">
            {Object.entries(spBySprint)
              .map(([sprint, sp]) => `спринт ${sprint}: ${isNegative(sp) ? sp : sp} SP`)
              .join(' · ')}
          </Text>
        </Stack>
      )}
    </Stack>
  )
}
