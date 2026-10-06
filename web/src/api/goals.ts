import { postJson } from './client'
import type { PlanRunSummary } from '../types/views'

export function confirmTaskGoal(
  taskId: string, closureCode: string, goalCode: string | null, confirmedBy: string, note: string,
): Promise<{ confirmation_id: number; plan: PlanRunSummary }> {
  return postJson('/tasks/goal-confirmation', {
    task_id: taskId, closure_code: closureCode, goal_code: goalCode,
    confirmed_by: confirmedBy, note,
  })
}

/** Задать (value) или снять (null) явный бизнес-приоритет инициативы; план пересчитывается. */
export function setInitiativePriority(
  prodfId: string, value: number | null, note: string,
): Promise<{ prodf_id: string; business_priority: number | null; plan: PlanRunSummary }> {
  return postJson('/initiatives/priority', { prodf_id: prodfId, business_priority: value, note })
}

