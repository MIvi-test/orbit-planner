/**
 * Чтение значений так, как их реально шлёт сервер (docs/UI_SPEC.md §0.1).
 * `numeric` PostgreSQL приходит строкой — использовать `+row.x` нельзя.
 */
import type { NumericString } from '../types/views'

/** "140.00" → 140. Пусто/null → 0 — только там, где ноль осмыслен как значение. */
export function num(value: NumericString | null | undefined): number {
  if (value === null || value === undefined || value === '') return 0
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

/** Отрицательное значение по ЗНАКУ СТРОКИ, а не после parseFloat. */
export function isNegative(value: NumericString | null | undefined): boolean {
  return typeof value === 'string' && value.trim().startsWith('-')
}

/** Число ли это на самом деле: null, пусто и «не число» — отсутствие значения, а не ноль (DA-48). */
export function isNumeric(value: NumericString | number | null | undefined): boolean {
  if (value === null || value === undefined || value === '') return false
  return Number.isFinite(typeof value === 'number' ? value : Number(value))
}

/** Дефицит — строго больше нуля: полностью покрытая связка (gap = 0) проблемой не является (DA-48). */
export function isPositive(value: NumericString | null | undefined): boolean {
  return isNumeric(value) && num(value) > 0
}

/** Часы для показа: без хвостовых нулей после запятой. Нет значения — «—», а не «0 ЧЧ». */
export function fmtHours(value: NumericString | null | undefined): string {
  if (!isNumeric(value)) return '—'
  const rounded = Math.round(num(value) * 100) / 100
  return `${trimZeros(rounded)} ЧЧ`
}

/** Story Points: то же форматирование, без единицы. Нет значения — «—»: неизвестная ёмкость не равна нулевой. */
export function fmtSp(value: NumericString | number | null | undefined): string {
  if (!isNumeric(value)) return '—'
  const n = typeof value === 'number' ? value : num(value)
  return trimZeros(Math.round(n * 100) / 100)
}

/** Проценты KPI: всегда два знака, это привычная форма показателя. Нет значения — «н/д». */
export function fmtPercent(value: NumericString | null | undefined): string {
  return isNumeric(value) ? `${num(value).toFixed(2)}%` : 'н/д'
}

function trimZeros(n: number): string {
  const s = n.toFixed(2)
  return s.replace(/\.?0+$/, '') || '0'
}

/** ГГГГ-ММ-ДД → ДД.ММ. Короткая дата для тесных колонок ганта и лент. */
export function fmtDateShort(value: string | null | undefined): string {
  if (!value) return '—'
  const [, m, d] = value.split('-')
  return m && d ? `${d}.${m}` : value
}

/** ГГГГ-ММ-ДД → ДД.ММ.ГГГГ. */
export function fmtDate(value: string | null | undefined): string {
  if (!value) return '—'
  const [y, m, d] = value.split('-')
  return y && m && d ? `${d}.${m}.${y}` : value
}

/** Значение или тире — по правилу «null рисуется как «—», а не как 0». */
export function orDash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}
