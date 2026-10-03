import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Badge, Button, Group, Modal, ScrollArea, Select, Stack, Table, Text, Textarea, TextInput } from '@mantine/core'
import { reviewDqIssue } from '../../api/dataQuality'
import type { DqIssueReviewRow, DqIssueRow } from '../../types/views'
import { useAuth } from '../../hooks/useAuth'

const STATUS: Record<string, string> = {
  open: 'Не разобрана', acknowledged: 'Принята к сведению',
  resolved: 'Исправлена', reopened: 'Открыта повторно',
}

export function DataQualityWorkbench({ issues, reviews }: {
  issues: DqIssueRow[]; reviews: DqIssueReviewRow[]
}) {
  const queryClient = useQueryClient()
  const { me, can } = useAuth()
  const [rule, setRule] = useState<string | null>(null)
  const [severity, setSeverity] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [entity, setEntity] = useState('')
  const [selected, setSelected] = useState<DqIssueRow | null>(null)
  const [decision, setDecision] = useState<DqIssueReviewRow['decision']>('acknowledged')
  const [reviewer, setReviewer] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const rules = useMemo(() => [...new Set(issues.map((item) => item.rule_code))].sort(), [issues])
  const filtered = issues.filter((item) =>
    (!rule || item.rule_code === rule)
    && (!severity || item.severity === severity)
    && (!status || item.review_status === status)
    && (!entity || `${item.entity} ${item.entity_id ?? ''} ${item.detail}`.toLowerCase().includes(entity.toLowerCase())),
  )
  const history = selected ? reviews.filter((item) => item.issue_id === selected.issue_id) : []

  async function submit() {
    if (!selected) return
    setBusy(true)
    setError(null)
    try {
      await reviewDqIssue(selected.issue_id, decision,
        me?.auth === 'required' ? me.name : reviewer, note)
      await queryClient.invalidateQueries({ queryKey: ['view'] })
      setSelected(null)
      setNote('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Stack gap="sm">
      <Group gap="xs" grow>
        <Select label="Правило" placeholder="Все" clearable data={rules} value={rule} onChange={setRule} />
        <Select label="Уровень" placeholder="Все" clearable data={['error', 'warning', 'info']} value={severity} onChange={setSeverity} />
        <Select label="Решение" placeholder="Все" clearable data={Object.entries(STATUS).map(([value, label]) => ({ value, label }))} value={status} onChange={setStatus} />
        <TextInput label="Задача, роль или деталь" value={entity} onChange={(event) => setEntity(event.currentTarget.value)} />
      </Group>
      <Text size="xs" c="dimmed">Показано {filtered.length} из {issues.length} находок. Блокирующие ошибки выделены красным. Исходная запись ETL сохраняется после решения.</Text>
      <ScrollArea type="auto" h={390}>
        <Table striped highlightOnHover stickyHeader miw={900}>
          <Table.Thead><Table.Tr><Table.Th>Правило</Table.Th><Table.Th>Объект</Table.Th><Table.Th>Деталь</Table.Th><Table.Th>Состояние</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>
            {filtered.map((item) => (
              <Table.Tr key={item.issue_id}>
                <Table.Td><Badge color={item.is_blocking ? 'red' : item.severity === 'warning' ? 'yellow' : 'gray'} variant="light">{item.rule_code}</Badge></Table.Td>
                <Table.Td className="mono">{item.entity}{item.entity_id ? ` / ${item.entity_id}` : ''}</Table.Td>
                <Table.Td><Text size="xs">{item.detail}</Text></Table.Td>
                <Table.Td>{STATUS[item.review_status]}</Table.Td>
                <Table.Td><Button size="xs" variant="subtle" disabled={!can('planner')} onClick={() => { setSelected(item); setError(null) }}>Разобрать</Button></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>
      <Modal opened={selected !== null} onClose={() => setSelected(null)} title={selected ? `Находка #${selected.issue_id}` : ''} size="lg">
        {selected && <Stack gap="sm">
          <Text size="sm">{selected.detail}</Text>
          <Text size="xs" c="dimmed">{selected.entity} / {selected.entity_id ?? 'без ID'} · {selected.rule_code}</Text>
          <Text fw={600} size="sm">История решений</Text>
          {history.length === 0 && <Text size="xs" c="dimmed">Решений пока нет.</Text>}
          {history.map((item) => <Text key={item.review_id} size="xs">{new Date(item.reviewed_at).toLocaleString('ru-RU')} · {STATUS[item.decision]} · {item.reviewer}: {item.note}</Text>)}
          <Select label="Новое решение" data={[{ value: 'acknowledged', label: STATUS.acknowledged }, { value: 'resolved', label: STATUS.resolved }, { value: 'reopened', label: STATUS.reopened }]} value={decision} onChange={(value) => value && setDecision(value as DqIssueReviewRow['decision'])} />
          <TextInput label="Кто рассмотрел" value={me?.auth === 'required' ? me.name : reviewer}
            onChange={(event) => setReviewer(event.currentTarget.value)} disabled={me?.auth === 'required'} maxLength={120} />
          <Textarea label="Обоснование" value={note} onChange={(event) => setNote(event.currentTarget.value)} maxLength={2000} minRows={2} />
          {error && <Text c="red" size="sm">{error}</Text>}
          <Button loading={busy} disabled={!(me?.auth === 'required' || reviewer.trim()) || !note.trim()} onClick={submit}>Сохранить решение</Button>
        </Stack>}
      </Modal>
    </Stack>
  )
}
