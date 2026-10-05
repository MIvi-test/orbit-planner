import { Group, Text } from '@mantine/core'
import { IconCalculator, IconPlugConnected } from '@tabler/icons-react'
import type { ReactNode } from 'react'
import { useRun } from '../../hooks/useRun'

function Stamp({ icon, title, value, color, hint }: { icon: ReactNode; title: string; value: string; color: string; hint: string }) {
  return (
    <div
      title={hint}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '4px 10px',
        borderRadius: 6,
        border: `1px dashed var(--mantine-color-${color}-6)`,
        color: `var(--mantine-color-${color}-light-color)`,
        background: `color-mix(in srgb, var(--mantine-color-${color}-6) 8%, transparent)`,
      }}
    >
      {icon}
      <div style={{ lineHeight: 1.2 }}>
        <Text size="xs" c="dimmed">
          {title}
        </Text>
        <Text size="sm" className="mono" c="inherit">
          {value}
        </Text>
      </div>
    </div>
  )
}

/** Время ответа API и момент расчёта — разные моменты: рисуем их двумя разными отметками. */
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
    <Group gap="sm" wrap="wrap">
      {run && (
        <Stamp
          color="blue"
          icon={<IconCalculator size={20} stroke={1.6} />}
          title={`Расчёт плана, факт по спринт ${Math.max(0, run.as_of_sprint - 1)}`}
          value={format(run.created_at)}
          hint="Когда планировщик построил этот прогон"
        />
      )}
      {iso && (
        <Stamp
          color="teal"
          icon={<IconPlugConnected size={20} stroke={1.6} />}
          title="Ответ API"
          value={format(iso)}
          hint="Когда сервер отдал эти данные интерфейсу"
        />
      )}
    </Group>
  )
}
