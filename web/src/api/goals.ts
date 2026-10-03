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
