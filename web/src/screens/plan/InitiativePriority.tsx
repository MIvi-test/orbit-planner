import { useState } from 'react'
import { ActionIcon, Button, Group, Modal, NumberInput, Stack, Text, TextInput, Tooltip } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useQueryClient } from '@tanstack/react-query'
import { setInitiativePriority } from '../../api/goals'
import { useRun } from '../../hooks/useRun'

/**
 * Явный бизнес-приоритет инициативы (ADR-032): главнее priority_rung датасета и любой стратегии.
 * Сохранение пересчитывает план, поэтому доступно роли planner и выше.
 */
export function InitiativePriority({
  prodfId,
  datasetRung,
  business,
}: {
  prodfId: string
  datasetRung: number | null
  business: number | null
}) {
  const queryClient = useQueryClient()
  const { setRunId } = useRun()
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState<number | string>(business ?? datasetRung ?? '')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  async function save(clear: boolean) {
    setBusy(true)
    try {
      const result = await setInitiativePriority(prodfId, clear ? null : Number(value), note)
      await queryClient.invalidateQueries()
      setRunId(result.plan.run_id)
      setOpen(false)
      notifications.show({
        color: 'teal',
        title: clear ? 'Бизнес-приоритет снят' : 'Бизнес-приоритет задан',
        message: `План пересчитан: прогон ${result.plan.run_id}.`,
      })
    } catch (error) {
      notifications.show({
        color: 'red',
        title: 'Не удалось сохранить приоритет',
        message: error instanceof Error ? error.message : String(error),
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Tooltip label={business !== null ? `Задан бизнесом: ${business} (датасет: ${datasetRung ?? '—'})` : 'Задать бизнес-приоритет'}>
        <ActionIcon
          variant="subtle"
          size="sm"
          color={business !== null ? 'orange' : 'gray'}
          aria-label={`Приоритет инициативы ${prodfId}`}
          onClick={(event) => {
            event.stopPropagation()
            setOpen(true)
          }}
        >
          ✎
        </ActionIcon>
      </Tooltip>
      <Modal opened={open} onClose={() => setOpen(false)} title={`Приоритет ${prodfId}`} size="sm">
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            В датасете: {datasetRung ?? '—'} (максимум rung задач). Явный приоритет главнее и берётся в той же
            шкале; после сохранения план пересчитывается.
          </Text>
          <NumberInput label="Приоритет" value={value} onChange={setValue} min={0} max={1000} allowDecimal={false} />
          <TextInput label="Основание" value={note} onChange={(e) => setNote(e.currentTarget.value)}
            description="Обязательно: по нему потом объясняют порядок работ" />
          <Group justify="space-between">
            <Button variant="subtle" color="gray" loading={busy} disabled={business === null} onClick={() => save(true)}>
              Снять
            </Button>
            <Button loading={busy} disabled={value === '' || !note.trim()} onClick={() => save(false)}>
              Сохранить
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  )
}
