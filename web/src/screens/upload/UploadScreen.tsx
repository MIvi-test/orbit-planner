import { Alert, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { DatasetDropzone } from './DatasetDropzone'
import { ActualsDropzone } from './ActualsDropzone'
import { UploadHistory } from './UploadHistory'
import { useRun } from '../../hooks/useRun'
import { useAuth } from '../../hooks/useAuth'
import { CreatePiContext } from './CreatePiContext'

export function UploadScreen({ onOpenPlan }: { onOpenPlan: () => void }) {
  const { setRunId } = useRun()
  const { can } = useAuth()
  const openResult = (runId: number) => {
    setRunId(runId)
    onOpenPlan()
  }
  return (
    <Stack gap="xl">
      <div>
        <Title order={2}>Загрузка данных</Title>
        <Text c="dimmed" mt={4}>
          Загрузите выданный датасет — план построится автоматически. Раз в две
          недели загружайте факт закрытого спринта: сервис пересчитает
          остаток плана.
        </Text>
      </div>

      {!can('planner') && (
        <Alert color="gray" title="Режим просмотра">
          У вашей роли нет права загружать данные. Попросите администратора выдать роль «планировщик».
        </Alert>
      )}
      {can('admin') && <CreatePiContext />}

      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
        {can('admin') && <DatasetDropzone onDone={openResult} />}
        {can('planner') && <ActualsDropzone onDone={openResult} />}
      </SimpleGrid>

      <UploadHistory />
    </Stack>
  )
}
