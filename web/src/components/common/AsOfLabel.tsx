import { Text } from '@mantine/core'
import { useRun } from '../../hooks/useRun'

/** Время ответа API и момент расчёта — разные моменты. */
export function AsOfLabel({ iso }: { iso: string | null }) {
  const { runs, runId } = useRun()
  const run = runs.find((item) => item.run_id === runId)
  if (!iso && !run) return null
  const format = (value: string) => {
    const d = new Date(value)
    return Number.isNaN(d.getTime())
      ? value
      : d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  }
  return (
    <Text size="xs" c="dimmed" className="mono">
      {run && <>Расчёт {format(run.created_at)} · факт по спринт {Math.max(0, run.as_of_sprint - 1)}<br /></>}
      {iso && <>Ответ API {format(iso)}</>}
    </Text>
  )
}
