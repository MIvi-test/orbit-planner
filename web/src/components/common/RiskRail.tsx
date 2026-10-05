/**
 * Вертикальная линейка риска (docs/UI_DESIGN.md §4): цвет не единственный
 * носитель смысла — слово печатается рядом, а не подразумевается цветом.
 */
import { Badge, Group } from '@mantine/core'
import type { ReactNode } from 'react'

export type RiskLevel = 'critical' | 'warning' | 'ok'

export const RISK_COLOR: Record<RiskLevel, string> = {
  critical: 'var(--stamp)',
  warning: 'var(--wax-text)',
  ok: 'var(--route-text)',
}

export function levelFromAlert(level: 'red' | 'yellow' | 'orange'): RiskLevel {
  if (level === 'red') return 'critical'
  if (level === 'yellow' || level === 'orange') return 'warning'
  return 'ok'
}

export function RiskRail({
  level,
  label,
  children,
}: {
  level: RiskLevel
  label: string
  children: ReactNode
}) {
  return (
    <Group gap="md" wrap="nowrap" align="flex-start">
      <div style={{ flex: 1, minWidth: 0 }}>{children}</div>
      <Badge
        variant="light"
        size="lg"
        style={{
          color: RISK_COLOR[level],
          background: `color-mix(in srgb, ${RISK_COLOR[level]} 14%, transparent)`,
          textTransform: 'none',
          flexShrink: 0,
        }}
      >
        {label}
      </Badge>
    </Group>
  )
}
