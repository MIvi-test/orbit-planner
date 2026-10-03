import { useMemo } from 'react'
import { useRun } from '../../hooks/useRun'
import {
  usePlanAssignments,
  usePlanRoleDemandSnapshot,
  usePlanSchedule,
  usePlanTaskSp,
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
  PlanRoleDemandSnapshotRow,
  SprintRow,
  TaskStateRow,
  TaskRow,
} from '../../types/views'

export interface InitiativeGroup {
  prodf_id: string
  title: string
  priority_rung: number | null
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
  const spQ = usePlanTaskSp(runId)
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
    spQ.isPending ||
    assignQ.isPending
  const isError =
    sprintsQ.isError || tasksQ.isError || stateQ.isError || roleDemandQ.isError || initiativesQ.isError || scheduleQ.isError || spQ.isError || assignQ.isError
  const firstError = sprintsQ.error ?? tasksQ.error ?? stateQ.error ?? roleDemandQ.error ?? initiativesQ.error ?? scheduleQ.error ?? spQ.error ?? assignQ.error

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
        team_id: group[0]?.team_id ?? '',
        tasks: group,
      })
    }
    result.sort((a, b) => (b.priority_rung ?? -1) - (a.priority_rung ?? -1) || a.prodf_id.localeCompare(b.prodf_id))
    return result
  }, [tasksQ.data, initiativesQ.data])

  const scheduleByTask = useMemo(() => {
    const map = new Map<string, PlanTaskScheduleRow>()
    scheduleQ.data?.items.forEach((row) => map.set(row.task_id, row))
    return map
  }, [scheduleQ.data])

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
    baselineByTask,
    hasBaseline: baselineRunId !== null && baselineRunId !== runId,
    spByTask,
    assignmentsByTask,
  }
}
