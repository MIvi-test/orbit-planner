import { Badge, Code, Drawer, Group, Skeleton, Stack, Table, Text } from '@mantine/core'
import { useEvidence } from './hooks'

const TYPE: Record<string, string> = { snapshot: 'Снимок данных', document: 'Документ', scenario: 'Расчёт сценария' }

function show(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/** Сохранённое доказательство ответа: откуда число, какой снимок и какие поля. */
export function EvidenceDrawer({ evidenceId, onClose }: { evidenceId: string | null; onClose: () => void }) {
  const q = useEvidence(evidenceId)
  return (
    <Drawer opened={evidenceId !== null} onClose={onClose} position="right" size="lg" title="Доказательство ответа">
      {q.isPending && <Skeleton height={160} />}
      {q.isError && <Text c="red">{q.error.message}</Text>}
      {q.data && (
        <Stack gap="md">
          <Group gap={8}>
            <Badge variant="light">{TYPE[q.data.source_type] ?? q.data.source_type}</Badge>
            <Code>{q.data.source_ref}</Code>
          </Group>
          <Table verticalSpacing={6} fz="sm">
            <Table.Thead><Table.Tr><Table.Th>Поле</Table.Th><Table.Th>Значение</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {Object.entries(q.data.payload).map(([k, v]) => (
                <Table.Tr key={k}><Table.Td className="mono">{k}</Table.Td><Table.Td style={{ wordBreak: 'break-word' }}>{show(v)}</Table.Td></Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          <Text size="xs" c="dimmed" className="mono">{q.data.evidence_id}</Text>
        </Stack>
      )}
    </Drawer>
  )
}
