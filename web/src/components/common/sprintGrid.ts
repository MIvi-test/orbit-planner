/**
 * Шесть колонок спринтов — несущая сетка интерфейса (docs/UI_DESIGN.md §1):
 * одна и та же логика колонок на плане, рисках и KPI, чтобы взгляд
 * переносился между экранами без перенастройки.
 */
export function sprintGridTemplate(
  count: number,
  labelWidth = 'minmax(260px, 340px)',
  tailWidth = '64px',
): string {
  return `${labelWidth} repeat(${Math.max(count, 1)}, minmax(88px, 1fr)) ${tailWidth}`
}
