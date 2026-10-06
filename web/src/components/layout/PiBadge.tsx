/**
 * Границы PI и фонд — читать из витрин, никогда не вычислять на фронте
 * (docs/UI_SPEC.md §3: «Считать фонд квартала арифметикой в коде фронта» —
 * запрещено).
 */
import { Badge, Group, Skeleton, Text } from '@mantine/core'
import { usePiFundFactor, useSprints } from '../../hooks/useViews'
import { fmtDate } from '../../api/wire'

export function PiBadge() {
  const pi = usePiFundFactor()
  const sprints = useSprints()

  if (pi.isPending || sprints.isPending) return <Skeleton height={16} width={200} />

  const fund = pi.data?.items[0]
  const rows = sprints.data?.items ?? []
  if (!fund || !rows.length) return null

  const start = rows[0]?.start_date
  const end = rows[rows.length - 1]?.end_date

  return (
    <Group gap={8} wrap="nowrap" style={{ whiteSpace: 'nowrap' }}>
      <Text size="sm" fw={600} className="mono">{fund.pi_id}</Text>
      <Text size="sm" c="dimmed" className="mono">{fmtDate(start)} – {fmtDate(end)}</Text>
      <Badge variant="light" color="gray" style={{ textTransform: 'none' }}>{rows.length} спр.</Badge>
    </Group>
  )
}
