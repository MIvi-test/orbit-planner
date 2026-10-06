import { useMemo } from 'react'
import { useRun } from '../../hooks/useRun'
import {
  usePlanAssignments,
  usePlanDependencyBounds,
  usePlanGoalOutcome,
  useInitiativeGoalProgress,
  usePlanRoleDemandSnapshot,
  usePlanSchedule,
  usePlanTaskSp,
  usePlanTaskProgress,
  useSprints,
  useTaskState,
  useTasks,
  useInitiatives,
} from '../../hooks/useViews'
import type {
  InitiativeRow,
  PlanAssignmentDetailRow,
  PlanTaskScheduleRow,
  PlanTaskSpRow,
  PlanDependencyBoundRow,
  PlanGoalOutcomeRow,
  PlanTaskProgressRow,
  PlanRoleDemandSnapshotRow,
  SprintRow,
  TaskStateRow,
  TaskRow,
} from '../../types/views'

export interface InitiativeGroup {
  prodf_id: string
  title: string
  priority_rung: number | null
  /** Явный бизнес-приоритет (главнее priority_rung датасета), ADR-032. */
  business_priority: number | null
  team_id: string
  tasks: TaskRow[]
}

export function usePlanData() {
  const { runId, runs } = useRun()

  const sprintsQ = useSprints()
  // Справочник задач содержит все задачи; остаток берём из снимка прогона.
  const tasksQ = useTasks()
  const stateQ = useTaskState(runId)
  const roleDemandQ = usePlanRoleDemandSnapshot(runId)
  const initiativesQ = useInitiatives()
  const scheduleQ = usePlanSchedule(runId)
  const boundsQ = usePlanDependencyBounds(runId)
  const goalsQ = usePlanGoalOutcome(runId)
  const initiativeGoalsQ = useInitiativeGoalProgress(runId)
  const spQ = usePlanTaskSp(runId)
  const progressQ = usePlanTaskProgress(runId)
  const assignQ = usePlanAssignments(runId)

  // Канонический базовый прогон: первый опубликованный, включая старый infeasible.
  const baselineRunId = useMemo(() => {
    const candidates = runs.filter((r) => r.as_of_sprint === 0 && (r.status === 'ok' || r.status === 'infeasible'))
    return candidates.length ? Math.min(...candidates.map((r) => r.run_id)) : null
  }, [runs])
  const baselineQ = usePlanSchedule(baselineRunId)

  const isPending =
    sprintsQ.isPending ||
    tasksQ.isPending ||
    stateQ.isPending ||
    roleDemandQ.isPending ||
    initiativesQ.isPending ||
    scheduleQ.isPending ||
    boundsQ.isPending ||
    goalsQ.isPending || initiativeGoalsQ.isPending ||
    spQ.isPending ||
    progressQ.isPending ||
    assignQ.isPending
  const isError =
    sprintsQ.isError || tasksQ.isError || stateQ.isError || roleDemandQ.isError || initiativesQ.isError || scheduleQ.isError || boundsQ.isError || goalsQ.isError || initiativeGoalsQ.isError || spQ.isError || progressQ.isError || assignQ.isError
  const firstError = sprintsQ.error ?? tasksQ.error ?? stateQ.error ?? roleDemandQ.error ?? initiativesQ.error ?? scheduleQ.error ?? boundsQ.error ?? goalsQ.error ?? initiativeGoalsQ.error ?? spQ.error ?? progressQ.error ?? assignQ.error

  const groups = useMemo<InitiativeGroup[]>(() => {
    const tasks = tasksQ.data?.items
    const initiatives = initiativesQ.data?.items
    if (!tasks || !initiatives) return []
    const initiativeByProdf = new Map<string, InitiativeRow>(initiatives.map((i) => [i.prodf_id, i]))
    const byProdf = new Map<string, TaskRow[]>()
    for (const task of tasks) {
      const list = byProdf.get(task.prodf_id) ?? []
      list.push(task)
      byProdf.set(task.prodf_id, list)
    }
    const result: InitiativeGroup[] = []
    for (const [prodf_id, group] of byProdf) {
      const initiative = initiativeByProdf.get(prodf_id)
      group.sort((a, b) => a.task_id.localeCompare(b.task_id))
      result.push({
        prodf_id,
        title: initiative?.title ?? prodf_id,
        priority_rung: initiative?.priority_rung ?? group[0]?.rung ?? null,
        business_priority: initiative?.business_priority ?? null,
        team_id: [...new Set(group.map((t) => t.team_id))].sort().join(', '),
        tasks: group,
      })
    }
    const effective = (g: InitiativeGroup) => g.business_priority ?? g.priority_rung ?? -1
    result.sort((a, b) => effective(b) - effective(a) || a.prodf_id.localeCompare(b.prodf_id))
    return result
  }, [tasksQ.data, initiativesQ.data])

  const scheduleByTask = useMemo(() => {
    const map = new Map<string, PlanTaskScheduleRow>()
    scheduleQ.data?.items.forEach((row) => map.set(row.task_id, row))
    return map
  }, [scheduleQ.data])

  const boundsByTask = useMemo(() => {
    const map = new Map<string, PlanDependencyBoundRow>()
    boundsQ.data?.items.forEach((row) => map.set(row.task_id, row))
    return map
  }, [boundsQ.data])

  const goalsByTask = useMemo(() => {
    const map = new Map<string, PlanGoalOutcomeRow>()
    goalsQ.data?.items.forEach((row) => map.set(row.task_id, row))
    return map
  }, [goalsQ.data])

  const baselineByTask = useMemo(() => {
    const map = new Map<string, PlanTaskScheduleRow>()
    baselineQ.data?.items.forEach((row) => map.set(row.task_id, row))
    return map
  }, [baselineQ.data])

  const spByTask = useMemo(() => {
    const map = new Map<string, PlanTaskSpRow[]>()
    spQ.data?.items.forEach((row) => {
      const list = map.get(row.task_id) ?? []
      list.push(row)
      map.set(row.task_id, list)
    })
    return map
  }, [spQ.data])

  const progressByTask = useMemo(() => {
    const map = new Map<string, PlanTaskProgressRow[]>()
    progressQ.data?.items.forEach((row) => map.set(row.task_id, [...(map.get(row.task_id) ?? []), row]))
    return map
  }, [progressQ.data])

  const assignmentsByTask = useMemo(() => {
    const map = new Map<string, PlanAssignmentDetailRow[]>()
    assignQ.data?.items.forEach((row) => {
      const list = map.get(row.task_id) ?? []
      list.push(row)
      map.set(row.task_id, list)
    })
    return map
  }, [assignQ.data])

  const stateByTask = useMemo(() => {
    const map = new Map<string, TaskStateRow>()
    stateQ.data?.items.forEach((row) => map.set(row.task_id, row))
    return map
  }, [stateQ.data])

  const roleDemandByTask = useMemo(() => {
    const map = new Map<string, PlanRoleDemandSnapshotRow[]>()
    roleDemandQ.data?.items.forEach((row) => map.set(row.task_id, [...(map.get(row.task_id) ?? []), row]))
    return map
  }, [roleDemandQ.data])

  return {
    isPending,
    isError,
    firstError,
    runId,
    asOf: scheduleQ.data?.as_of ?? null,
    sprints: sprintsQ.data?.items ?? ([] as SprintRow[]),
    groups,
    stateByTask,
    roleDemandByTask,
    scheduleByTask,
    boundsByTask,
    goalsByTask,
    initiativeGoals: initiativeGoalsQ.data?.items ?? [],
    baselineByTask,
    hasBaseline: baselineRunId !== null && baselineRunId !== runId,
    spByTask,
    progressByTask,
    assignmentsByTask,
  }
}
