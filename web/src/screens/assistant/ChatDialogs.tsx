import { useEffect, useState } from 'react'
import { Alert, Button, Group, Modal, Text, TextInput } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { assistantApi, type Conversation } from '../../api/assistant'
import { AI_KEYS } from './hooks'

/** Переименование и удаление своего чата. Удаление необратимо: чат уходит вместе с историей и доказательствами. */
export function ChatDialogs({ renameTarget, deleteTarget, onClose, onDeleted }: {
  renameTarget: Conversation | null
  deleteTarget: Conversation | null
  onClose: () => void
  onDeleted: (id: string) => void
}) {
  const qc = useQueryClient()
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    setTitle(renameTarget?.title || '')
    setError(null)
  }, [renameTarget, deleteTarget])

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Modal opened={renameTarget !== null} onClose={onClose} title="Переименовать чат" centered>
        <TextInput autoFocus label="Название" value={title} maxLength={120} onChange={(e) => setTitle(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && title.trim() && renameTarget) void run(async () => { await assistantApi.rename(renameTarget.conversation_id, title.trim()); await qc.invalidateQueries({ queryKey: AI_KEYS.list }); await qc.invalidateQueries({ queryKey: AI_KEYS.conv(renameTarget.conversation_id) }) }) }} />
        {error && <Alert color="red" mt="sm">{error}</Alert>}
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={onClose}>Отмена</Button>
          <Button loading={busy} disabled={!title.trim()} onClick={() => renameTarget && void run(async () => {
            await assistantApi.rename(renameTarget.conversation_id, title.trim())
            await qc.invalidateQueries({ queryKey: AI_KEYS.list })
            await qc.invalidateQueries({ queryKey: AI_KEYS.conv(renameTarget.conversation_id) })
          })}>Сохранить</Button>
        </Group>
      </Modal>
      <Modal opened={deleteTarget !== null} onClose={onClose} title="Удалить чат?" centered>
        <Text size="sm">Чат «{deleteTarget?.title || 'Новый чат'}» будет удалён вместе с историей сообщений, рекомендациями и сохранёнными доказательствами. Это нельзя отменить.</Text>
        {error && <Alert color="red" mt="sm" title="Не удалось удалить">{error}</Alert>}
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={onClose}>Отмена</Button>
          <Button color="red" loading={busy} onClick={() => deleteTarget && void run(async () => {
            await assistantApi.remove(deleteTarget.conversation_id)
            await qc.invalidateQueries({ queryKey: AI_KEYS.list })
            onDeleted(deleteTarget.conversation_id)
          })}>Удалить</Button>
        </Group>
      </Modal>
    </>
  )
}
