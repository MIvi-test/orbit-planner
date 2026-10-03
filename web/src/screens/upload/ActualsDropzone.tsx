/**
 * Загрузка факта спринта: POST /api/actuals?sprint=N. Заменяет факт этого
 * спринта и все более поздние — предупреждение показывается, только если
 * повторная загрузка что-то реально отменяет.
 */
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Dropzone } from '@mantine/dropzone'
import { Alert, Anchor, Group, List, Paper, Select, Skeleton, Stack, Text, Title } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useActualUploads, useSprints } from '../../hooks/useViews'
import { templateUrl, uploadActuals } from '../../api/uploads'
import { ApiError } from '../../api/client'
import type { UploadErrorPayload } from '../../types/views'

export function ActualsDropzone({ onDone }: { onDone: (runId: number) => void }) {
  const [busy, setBusy] = useState(false)
  const [selectedSprint, setSelectedSprint] = useState<number | null>(null)
  const [problems, setProblems] = useState<string[]>([])
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const sprints = useSprints()
  const uploads = useActualUploads()
  const sprintRows = sprints.data?.items ?? []
  const uploadRows = uploads.data?.items ?? []

  if (sprints.isPending || uploads.isPending) {
    return (
      <Paper p="lg" withBorder>
        <Skeleton height={140} />
      </Paper>
    )
  }

  if (sprints.isError || !sprintRows.length) {
    return (
      <Paper p="lg" withBorder>
        <Stack gap={4}>
          <Title order={3}>Факт спринта</Title>
          <Text size="sm" c="dimmed">
            Сначала загрузите датасет — без него не с чем сравнивать факт.
          </Text>
        </Stack>
      </Paper>
    )
  }

  const sprintCount = sprintRows.length
  const lastUploaded = Math.max(0, ...uploadRows.map((u) => u.sprint_no))
  const nextSprint = Math.min(lastUploaded + 1, sprintCount)
  const reportSprint = selectedSprint !== null && selectedSprint <= nextSprint
    ? selectedSprint : nextSprint
  const replacing = reportSprint <= lastUploaded

  async function handleFile(file: File) {
    setBusy(true)
    setProblems([])
    setErrorMessage(null)
    try {
      const result = await uploadActuals(file, reportSprint)
      await queryClient.invalidateQueries()
      notifications.show({
        color: result.plan.status !== 'ok' || result.summary.warnings.length ? 'yellow' : 'teal',
        title: `Факт спринта ${reportSprint} принят · прогон ${result.plan.run_id}`,
        message: (
          <Stack gap={2}>
            <Text size="sm">План: {result.plan.status}; {result.plan.in_quarter} задач в квартале,
              {' '}{result.plan.alerts} алертов, ошибок приёмки {result.plan.violations_error}.</Text>
            {result.replaced_sprints.length > 0 && (
              <Text size="sm">Заменён факт спринтов: {result.replaced_sprints.join(', ')}.</Text>
            )}
            {result.summary.warnings.map((warning, index) => (
              <Text size="sm" key={index}>{warning}</Text>
            ))}
          </Stack>
        ),
        autoClose: 12000,
      })
      onDone(result.plan.run_id)
    } catch (err) {
      if (err instanceof ApiError && err.body) {
        const body = err.body as Partial<UploadErrorPayload>
        setErrorMessage(body.message ?? err.message)
        setProblems(body.problems ?? [])
      } else {
        setErrorMessage(err instanceof Error ? err.message : String(err))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Paper p="lg" withBorder>
      <Stack gap="sm">
        <Title order={3}>Факт спринта</Title>
        <>
            <Select
              label="Отчётный спринт"
              description={replacing
                ? 'Исправление удалит отчёты и прогоны этого и более поздних спринтов.'
                : 'Следующий спринт для нового отчёта; прошлые спринты доступны для исправления.'}
              data={Array.from({ length: nextSprint }, (_, index) => ({
                value: String(index + 1), label: `Спринт ${index + 1}`,
              }))}
              value={String(reportSprint)}
              onChange={(value) => setSelectedSprint(value ? Number(value) : null)}
              allowDeselect={false}
            />
            <Group justify="space-between" wrap="wrap">
              <Text size="sm">
                {replacing ? 'Исправление' : 'Следующий отчёт'}: <b className="mono">спринт {reportSprint}</b> из {sprintCount}
              </Text>
              <Anchor href={templateUrl(reportSprint)} download size="sm">
                Скачать шаблон
              </Anchor>
            </Group>
            <Text size="xs" c="dimmed">
              completed_sp — новые подтверждённые SP только за этот спринт. Пусто означает,
              что прогресс по SP не подтверждён; часы не заменяют эту оценку.
            </Text>
            <Text size="xs" c="dimmed">
              В колонках дат пустая ячейка сохраняет прежнюю дату; CLEAR очищает её.
              Новая дата исправляет запись. Для повторного Done оставьте конец пустым,
              чтобы сохранить дату первого завершения.
            </Text>
            <Dropzone
              onDrop={(files) => files[0] && handleFile(files[0])}
              accept={['text/csv', '.csv', '.xlsx']}
              maxFiles={1}
              loading={busy}
              multiple={false}
            >
              <Stack align="center" gap={4} py="md" style={{ pointerEvents: 'none' }}>
                <Text fw={500}>Перетащите файл .csv или .xlsx сюда или нажмите</Text>
                <Text size="sm" c="dimmed">
                  заполненный шаблон факта спринта {reportSprint}
                </Text>
              </Stack>
            </Dropzone>
            {replacing && (
              <Text size="xs" c="var(--wax-text)">
                Загрузка заменит факт спринта {reportSprint} и удалит все более поздние отчёты и прогоны.
              </Text>
            )}
          </>
        {errorMessage && (
          <Alert color="red" variant="light" title="Факт не принят">
            <Text size="sm">{errorMessage}</Text>
            {problems.length > 0 && (
              <List size="sm" mt={6}>
                {problems.map((p, i) => (
                  <List.Item key={i}>{p}</List.Item>
                ))}
              </List>
            )}
          </Alert>
        )}
      </Stack>
    </Paper>
  )
}
