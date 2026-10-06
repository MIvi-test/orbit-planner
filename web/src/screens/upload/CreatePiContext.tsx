import { useState } from 'react'
import { Alert, Button, FileInput, Group, Paper, Stack, Text, TextInput, Title } from '@mantine/core'
import { createPiContext, selectPiContext } from '../../api/client'

export function CreatePiContext() {
  const [piId, setPiId] = useState('')
  const [scenarioId, setScenarioId] = useState('main')
  const [startDate, setStartDate] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function create() {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const context = await createPiContext(file, piId.trim(), scenarioId.trim(), startDate)
      selectPiContext(context)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setBusy(false)
    }
  }

  return (
    <Paper p="lg" withBorder>
      <Stack gap="sm">
        <Title order={3}>Новый PI или сценарий</Title>
        <Text size="sm" c="dimmed">Создайте отдельный набор данных и план. Существующие PI сохранятся.</Text>
        <Group grow align="start">
          <TextInput label="PI" placeholder="PI-2027-Q1" value={piId} onChange={(event) => setPiId(event.currentTarget.value)} required />
          <TextInput label="Сценарий" value={scenarioId} onChange={(event) => setScenarioId(event.currentTarget.value)} required />
          <TextInput label="Начало PI" type="date" value={startDate} onChange={(event) => setStartDate(event.currentTarget.value)} required />
        </Group>
        <FileInput label="Датасет .xlsx" accept=".xlsx,.xlsm" value={file} onChange={setFile} required />
        {error && <Alert color="red" title="PI не создан">{error}</Alert>}
        <Button onClick={create} loading={busy} disabled={!file || !piId.trim() || !scenarioId.trim() || !startDate}>
          Создать PI и построить план
        </Button>
      </Stack>
    </Paper>
  )
}
