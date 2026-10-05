import { useState } from 'react'
import { Badge, Button, Group, Paper, Stack, Table, Text, Title } from '@mantine/core'
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

  const revisionRows = revisions.data?.items ?? []
  return (
    <Stack gap="lg">
      <Paper withBorder p="md">
        <Stack gap="xs">
          <div>
            <Title order={3}>Загруженные отчёты по факту</Title>
            <Text c="dimmed" size="sm" mt={2}>
              Раз в спринт загружается отчёт о том, что реально сделано. Каждая строка — один такой файл: за какой спринт,
              когда загружен и сколько задач он закрыл. По ним пересчитываются остаток плана и KPI.
            </Text>
          </div>
          <QueryState
            query={query}
            skeletonRows={2}
            isEmpty={(e) => e.items.length === 0}
            emptyTitle="Факт ещё не загружали"
            emptyBody="После загрузки отчёта по спринту он появится в этой таблице."
          >
            {(envelope) => (
              <Table.ScrollContainer minWidth={640}>
                <Table striped highlightOnHover verticalSpacing="xs" withTableBorder>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th w={90}>Спринт</Table.Th>
                      <Table.Th>Загружен</Table.Th>
                      <Table.Th>Файл</Table.Th>
                      <Table.Th ta="right">Выполнено</Table.Th>
                      <Table.Th ta="right">В работе</Table.Th>
                      <Table.Th ta="right">ЧЧ</Table.Th>
                      <Table.Th>Предупреждения</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {envelope.items.map((row) => (
                      <Table.Tr key={row.upload_id}>
                        <Table.Td className="mono">{row.sprint_no}</Table.Td>
                        <Table.Td>{formatUploadedAt(row.uploaded_at)}</Table.Td>
                        <Table.Td className="mono">{row.source_file}</Table.Td>
                        <Table.Td ta="right" className="mono">{row.summary.done}</Table.Td>
                        <Table.Td ta="right" className="mono">{row.summary.in_progress}</Table.Td>
                        <Table.Td ta="right" className="mono">{num(row.summary.hours).toFixed(0)}</Table.Td>
                        <Table.Td>
                          {row.summary.warnings.length > 0 ? (
                            <Text size="sm" c="var(--wax-text)">{row.summary.warnings.join('; ')}</Text>
                          ) : (
                            <Text size="sm" c="dimmed">Нет</Text>
                          )}
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            )}
          </QueryState>
        </Stack>
      </Paper>

      <Paper withBorder p="md">
        <Stack gap="xs">
          <div>
            <Title order={3}>Архив исходных файлов</Title>
            <Text c="dimmed" size="sm" mt={2}>
              Если файл загрузили заново, прежняя версия не пропадает, а остаётся здесь со статусом «заменена». Чтобы
              вернуть старую версию, скачайте её и загрузите снова для нужного спринта.
            </Text>
          </div>
          {revisions.isError && <Text size="sm" c="red">Не удалось получить архив файлов.</Text>}
          {downloadError && <Text size="sm" c="red">{downloadError}</Text>}
          {revisionRows.length === 0 && !revisions.isError ? (
            <Text c="dimmed" size="sm">Пока нет сохранённых файлов.</Text>
          ) : (
            <Table.ScrollContainer minWidth={640}>
              <Table striped highlightOnHover verticalSpacing="xs" withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th w={110}>Версия №</Table.Th>
                    <Table.Th>Что загружено</Table.Th>
                    <Table.Th>Файл</Table.Th>
                    <Table.Th>Статус</Table.Th>
                    <Table.Th ta="right">Скачать</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {revisionRows.map((item) => (
                    <Table.Tr key={item.revision_id}>
                      <Table.Td className="mono">{item.revision_id}</Table.Td>
                      <Table.Td>{item.kind === 'dataset' ? 'Датасет' : `Факт, спринт ${item.sprint_no}`}</Table.Td>
                      <Table.Td className="mono">{item.source_file}</Table.Td>
                      <Table.Td>
                        <Badge variant="light" color={item.superseded_by ? 'gray' : 'green'}>
                          {item.superseded_by ? `Заменена версией №${item.superseded_by}` : 'Актуальная'}
                        </Badge>
                      </Table.Td>
                      <Table.Td ta="right">
                        <Group gap={4} justify="flex-end" wrap="nowrap">
                          <Button variant="light" size="compact-sm" onClick={() => void download(item.revision_id)}>Файл</Button>
                          {item.snapshot_available && (
                            <Button variant="light" size="compact-sm" onClick={() => void snapshot(item.revision_id)}>Снимок KPI</Button>
                          )}
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </Stack>
      </Paper>
    </Stack>
  )
}
