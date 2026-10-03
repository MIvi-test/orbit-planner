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
  ToDo: 'не начата',
  InProgress: 'в работе',
  Done: 'выполнена',
  Deferred: 'отложена',
  Cancelled: 'отменена',
}

export const ALERT_WORD: Record<AlertType, string> = {
  deadline_miss: 'срыв квартала',
  cascade_shift: 'сдвиг цепочки',
  role_deficit: 'нехватка роли',
}

export const LEVEL_COLOR: Record<AlertLevel, string> = {
  red: 'var(--stamp)',
  yellow: 'var(--wax)',
  orange: 'var(--wax-text)',
}

export const CHANGE_WORD: Record<DiffChangeType, string> = {
  unchanged: 'без изменений',
  newly_planned: 'вошла в квартал',
  newly_deferred: 'перенесена впервые',
  newly_cancelled: 'отменена',
  decision_changed: 'изменено решение',
  shifted_later: 'сдвинута позже',
  shifted_earlier: 'сдвинута раньше',
  start_changed: 'изменён старт',
  assignment_changed: 'изменены назначения',
  sp_changed: 'изменены доли SP',
  reason_changed: 'изменена причина решения',
  completed: 'выполнена',
}

export const CAUSE_WORD: Record<Exclude<DiffCause, null>, string> = {
  own_slip: 'сама не закрылась в срок',
  carry_over: 'работа продолжается в прежний срок',
  dependency: 'сдвинулась блокирующая',
  unknown: 'причина не установлена',
  completed: 'выполнена по факту',
}

/** `deviation` приходит готовой строкой из `v_sprint_deviation` — здесь только тон. */
export function deviationTone(deviation: string): RiskLevel {
  if (deviation === 'не закрыта в срок') return 'critical'
  if (deviation === 'по плану' || deviation === 'в срок' || deviation === 'раньше плана') return 'ok'
  return 'warning'
}
