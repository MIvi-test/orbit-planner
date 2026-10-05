/**
 * Слова ленты рисков. Цвет никогда не единственный носитель смысла
 * (docs/UI_DESIGN.md §9): рядом с линейкой риска печатается слово, а не
 * подразумевается оттенком. Сами сообщения брать из `alerts.message` и
 * `v_plan_diff.explanation` — они уже написаны по-русски (docs/UI_SPEC.md §8.2),
 * здесь только короткие подписи-теги.
 */
import type { RiskLevel } from '../../components/common/RiskRail'
import type {
  AlertLevel,
  AlertType,
  DiffCause,
  DiffChangeType,
  TaskStateStatus,
} from '../../types/views'

/** Статусы задачи приходят из базы английскими — показываем по-русски. */
export const STATUS_WORD: Record<TaskStateStatus, string> = {
  ToDo: 'Не начата',
  InProgress: 'В работе',
  Done: 'Выполнена',
  Deferred: 'Отложена',
  Cancelled: 'Отменена',
}

export const ALERT_WORD: Record<AlertType, string> = {
  deadline_miss: 'Срыв квартала',
  cascade_shift: 'Сдвиг цепочки',
  role_deficit: 'Нехватка роли',
}

export const LEVEL_COLOR: Record<AlertLevel, string> = {
  red: 'var(--stamp)',
  yellow: 'var(--wax)',
  orange: 'var(--wax-text)',
}

export const CHANGE_WORD: Record<DiffChangeType, string> = {
  unchanged: 'Без изменений',
  newly_planned: 'Вошла в квартал',
  newly_deferred: 'Перенесена впервые',
  newly_cancelled: 'Отменена',
  decision_changed: 'Изменено решение',
  shifted_later: 'Сдвинута позже',
  shifted_earlier: 'Сдвинута раньше',
  start_changed: 'Изменён старт',
  assignment_changed: 'Изменены назначения',
  sp_changed: 'Изменены доли SP',
  reason_changed: 'Изменена причина решения',
  completed: 'Выполнена',
}

export const CAUSE_WORD: Record<Exclude<DiffCause, null>, string> = {
  own_slip: 'Сама не закрылась в срок',
  carry_over: 'Работа продолжается в прежний срок',
  dependency: 'Сдвинулась блокирующая',
  unknown: 'Причина не установлена',
  completed: 'Выполнена по факту',
}

/** `deviation` приходит готовой строкой из `v_sprint_deviation` — здесь только тон. */
export function deviationTone(deviation: string): RiskLevel {
  if (deviation === 'не закрыта в срок') return 'critical'
  if (deviation === 'по плану' || deviation === 'в срок' || deviation === 'раньше плана') return 'ok'
  return 'warning'
}
