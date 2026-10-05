import { useMemo, useState } from 'react'
import { Badge, Button, Group, Menu, Paper, SegmentedControl, Select, Skeleton, Stack, Table, Text, TextInput, Title } from '@mantine/core'
import { IconDownload } from '@tabler/icons-react'
import { exportRows, type ExportColumn, type ExportFormat } from '../../utils/exportData'
import type { DqIssueRow } from '../../types/views'
import { useDqIssues } from '../../hooks/useViews'
import { QueryError } from '../../components/common/QueryError'

const COLOR = { error: 'red', warning: 'orange', info: 'gray' } as const
const WORD = { error: 'Блокирует', warning: 'Предупреждение', info: 'Информация' } as const

/** Качество исходных данных (NEW-06): весь журнал находок с фильтрами, а не один пример на правило. */
const REVIEW_WORD: Record<string, string> = { open: 'Открыта', acknowledged: 'Принята', resolved: 'Решена', reopened: 'Открыта снова' }

const EXPORT_COLUMNS: ExportColumn<DqIssueRow>[] = [
  { header: 'Серьёзность', value: (r) => WORD[r.severity] },
  { header: 'Блокирует план', value: (r) => (r.is_blocking ? 'Да' : 'Нет') },
  { header: 'Правило', value: (r) => r.rule_code },
  { header: 'Сущность', value: (r) => r.entity },
  { header: 'Идентификатор', value: (r) => r.entity_id },
  { header: 'Что найдено', value: (r) => r.detail },
  { header: 'Статус разбора', value: (r) => REVIEW_WORD[r.review_status] ?? r.review_status },
  { header: 'Кто разобрал', value: (r) => r.reviewer },
  { header: 'Комментарий', value: (r) => r.review_note },
]

export function DataQualityScreen() {
  const query = useDqIssues()
  const [severity, setSeverity] = useState('all')
  const [rule, setRule] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const rows = query.data?.items ?? []
  const rules = useMemo(() => [...new Set(rows.map((r) => r.rule_code))].sort(), [rows])
  const shown = rows.filter(
    (r) =>
      (severity === 'all' || r.severity === severity) &&
      (rule === null || r.rule_code === rule) &&
      (!search || `${r.entity_id ?? ''} ${r.detail}`.toLowerCase().includes(search.toLowerCase())),
  )
  const count = (s: string) => rows.filter((r) => r.severity === s).length

  if (query.isPending) return <Stack><Title order={2}>Данные</Title><Skeleton height={300} /></Stack>
  if (query.error) return <Stack><Title order={2}>Данные</Title><QueryError error={query.error} title="Не удалось загрузить журнал качества данных" /></Stack>

  return (
    <Stack gap="md">
      <div>
        <Title order={2}>Качество данных</Title>
        <Text c="dimmed" size="sm" mt={2}>
          Находки ETL по загруженному датасету. Блокирующие ошибки не дают построить план; предупреждения и информация —
          материал для разбора и вопросов заказчику.
        </Text>
      </div>
      <Group gap="sm" wrap="wrap">
        <SegmentedControl value={severity} onChange={setSeverity} data={[
          { value: 'all', label: `Все ${rows.length}` },
          { value: 'error', label: `Блокирующие ${count('error')}` },
          { value: 'warning', label: `Предупреждения ${count('warning')}` },
          { value: 'info', label: `Информация ${count('info')}` },
        ]} />
        <Select placeholder="Правило" data={rules} value={rule} onChange={setRule} clearable searchable w={260} />
        <TextInput placeholder="Поиск по сущности и тексту" value={search} onChange={(e) => setSearch(e.currentTarget.value)} w={280} />
        <Menu position="bottom-end" withinPortal>
          <Menu.Target>
            <Button variant="light" leftSection={<IconDownload size={18} />} ml="auto" disabled={shown.length === 0}>
              Выгрузить ({shown.length})
            </Button>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Label>Выгружается то, что видно по фильтрам</Menu.Label>
            {(['csv', 'xlsx', 'json'] as ExportFormat[]).map((f) => (
              <Menu.Item key={f} onClick={() => void exportRows(shown, EXPORT_COLUMNS, f, 'качество-данных')}>
                {f === 'csv' ? 'CSV (таблица, открывается в Excel)' : f === 'xlsx' ? 'XLSX (Excel)' : 'JSON'}
              </Menu.Item>
            ))}
          </Menu.Dropdown>
        </Menu>
      </Group>
      <Paper withBorder p={0} style={{ overflow: 'auto' }}>
        <Table striped verticalSpacing={6}>
          <Table.Thead><Table.Tr><Table.Th>Серьёзность</Table.Th><Table.Th>Правило</Table.Th><Table.Th>Сущность</Table.Th><Table.Th>Что найдено</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {shown.map((r) => (
              <Table.Tr key={r.issue_id}>
                <Table.Td><Badge color={COLOR[r.severity]} variant="light" size="sm">{WORD[r.severity]}</Badge></Table.Td>
                <Table.Td className="mono">{r.rule_code}</Table.Td>
                <Table.Td className="mono">{r.entity}{r.entity_id ? ` · ${r.entity_id}` : ''}</Table.Td>
                <Table.Td>{r.detail}</Table.Td>
              </Table.Tr>
            ))}
            {shown.length === 0 && <Table.Tr><Table.Td colSpan={4}><Text c="dimmed" size="sm">Находок по этому отбору нет.</Text></Table.Td></Table.Tr>}
          </Table.Tbody>
        </Table>
      </Paper>
    </Stack>
  )
}
