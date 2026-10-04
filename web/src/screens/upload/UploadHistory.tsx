import { useState } from 'react'
import { Button, Stack, Table, Text, Title } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { downloadPlanSnapshot, downloadUploadRevision, fetchUploadRevisions } from '../../api/client'
import { useActualUploads } from '../../hooks/useViews'
import { QueryState } from '../../components/common/QueryState'
import { num } from '../../api/wire'

function formatUploadedAt(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export function UploadHistory() {
  const query = useActualUploads()
  const revisions = useQuery({ queryKey: ['upload-revisions'], queryFn: fetchUploadRevisions })
  const [downloadError, setDownloadError] = useState('')
  const download = async (id: number) => {
    setDownloadError('')
    try { await downloadUploadRevision(id) }
    catch (error) { setDownloadError(error instanceof Error ? error.message : 'Не удалось скачать редакцию') }
  }
  const snapshot = async (id: number) => {
    setDownloadError('')
    try { await downloadPlanSnapshot(id) }
    catch (error) { setDownloadError(error instanceof Error ? error.message : 'Не удалось скачать снимок') }
  }

  return (
    <Stack gap="sm">
      <Title order={3}>История загрузок факта</Title>
      <QueryState
        query={query}
        skeletonRows={2}
        isEmpty={(e) => e.items.length === 0}
        emptyTitle="Факт ещё не загружали"
        emptyBody="После загрузки датасета здесь появится история загрузок факта по спринтам."
      >
        {(envelope) => (
          <Table.ScrollContainer minWidth={480}>
            <Table verticalSpacing="xs">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Спринт</Table.Th>
                  <Table.Th>Загружен</Table.Th>
                  <Table.Th>Файл</Table.Th>
                  <Table.Th>Итог</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {envelope.items.map((row) => (
                  <Table.Tr key={row.upload_id}>
                    <Table.Td className="mono">{row.sprint_no}</Table.Td>
                    <Table.Td>{formatUploadedAt(row.uploaded_at)}</Table.Td>
                    <Table.Td>
                      <Text size="sm" className="mono">
                        {row.source_file}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">
                        {row.summary.done} выполнено · {row.summary.in_progress} в работе ·{' '}
                        {num(row.summary.hours).toFixed(0)} ЧЧ
                      </Text>
                      {row.summary.warnings.length > 0 && (
                        <Text size="xs" c="var(--wax-text)">
                          {row.summary.warnings.join('; ')}
                        </Text>
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </QueryState>
      <Title order={4}>Редакции исходных файлов</Title>
      <Text size="xs" c="dimmed">Заменённые файлы сохраняются. Чтобы восстановить редакцию факта, скачайте её и загрузите снова для соответствующего спринта; последующие отчёты также доступны здесь.</Text>
      {revisions.isError && <Text size="sm" c="red">Не удалось получить редакции загрузок.</Text>}
      {downloadError && <Text size="sm" c="red">{downloadError}</Text>}
      {(revisions.data?.items ?? []).length > 0 && <Table.ScrollContainer minWidth={480}><Table verticalSpacing="xs">
        <Table.Thead><Table.Tr><Table.Th>Редакция</Table.Th><Table.Th>Период</Table.Th><Table.Th>Файл</Table.Th><Table.Th>Статус</Table.Th><Table.Th /></Table.Tr></Table.Thead>
        <Table.Tbody>{(revisions.data?.items ?? []).map((item) => <Table.Tr key={item.revision_id}>
          <Table.Td className="mono">{item.revision_id}</Table.Td>
          <Table.Td>{item.kind === 'dataset' ? 'Датасет' : `Спринт ${item.sprint_no}`}</Table.Td>
          <Table.Td>{item.source_file}</Table.Td>
          <Table.Td>{item.superseded_by ? `заменена №${item.superseded_by}` : 'активная'}</Table.Td>
          <Table.Td><Button variant="subtle" size="compact-xs" onClick={() => void download(item.revision_id)}>Файл</Button>
            {item.snapshot_available && <Button variant="subtle" size="compact-xs" onClick={() => void snapshot(item.revision_id)}>Снимок KPI</Button>}
          </Table.Td>
        </Table.Tr>)}</Table.Tbody>
      </Table></Table.ScrollContainer>}
    </Stack>
  )
}
