import { Tooltip } from '@mantine/core'
import { IconAlertTriangleFilled, IconCircleCheckFilled, IconLoader2 } from '@tabler/icons-react'
import { useHealth } from '../../hooks/useHealth'

/** Состояние API одной иконкой: галочка — в порядке, красный треугольник — недоступен. */
export function HealthBadge() {
  const health = useHealth()

  if (health.isPending) {
    return (
      <Tooltip label="Проверяю API…">
        <span className="health-chip" style={{ color: 'var(--mantine-color-gray-6)' }}>
          <IconLoader2 size={22} /> API
        </span>
      </Tooltip>
    )
  }
  if (health.isError) {
    return (
      <Tooltip label="API недоступен: база не отвечает, запустите run.sh или run.bat">
        <span className="health-chip" style={{ color: 'var(--mantine-color-red-6)' }}>
          <IconAlertTriangleFilled size={22} /> API
        </span>
      </Tooltip>
    )
  }
  return (
    <Tooltip
      label={
        health.data.server_version
          ? `API в порядке: PostgreSQL ${health.data.server_version}, ${health.data.tables} таблиц, ${health.data.views} вьюх`
          : 'API в порядке: база отвечает'
      }
    >
      <span className="health-chip" style={{ color: 'var(--mantine-color-teal-6)' }}>
        <IconCircleCheckFilled size={22} /> API
      </span>
    </Tooltip>
  )
}
