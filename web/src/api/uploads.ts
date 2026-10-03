/**
 * Три маршрута записи (docs/SCHEMA.md §4). Тело запроса — сам файл,
 * без multipart: `fetch(url, {method:'POST', body: file})`.
 */
import { postFile, postJson } from './client'
import type { ActualsUploadResult, DatasetUploadResult, PlanRunSummary } from '../types/views'

/** POST /api/dataset — xlsx датасета. Стирает прежние прогоны и факт. */
export function uploadDataset(file: File): Promise<DatasetUploadResult> {
  return postFile<DatasetUploadResult>('/dataset', file)
}

/** POST /api/actuals?sprint=N — факт спринта N. Заменяет факт N и все более поздние. */
export function uploadActuals(file: File, sprintNo: number, confirmComplete: boolean): Promise<ActualsUploadResult> {
  return postFile<ActualsUploadResult>('/actuals', file, {
    sprint: String(sprintNo), confirm_complete: String(confirmComplete),
  })
}

export function reviewActualRole(taskId: string, roleId: number, remainingHours: number, reason: string): Promise<{ plan: PlanRunSummary }> {
  return postJson('/actuals/role-review', {
    task_id: taskId, role_id: roleId, remaining_hours: remainingHours, reason,
  })
}

/** GET /api/actuals/template?sprint=N — CSV-шаблон для скачивания браузером. */
export function templateUrl(sprintNo?: number): string {
  return sprintNo ? `/api/actuals/template?sprint=${sprintNo}` : '/api/actuals/template'
}
