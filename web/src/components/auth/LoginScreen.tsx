import { useState } from 'react'
import { Alert, Button, Center, Checkbox, Paper, PasswordInput, Stack, Text, Title } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { setToken, clearToken } from '../../api/auth'
import { ApiError, fetchMe } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'

/** Экран входа по токену доступа (ADR-027). Токен выдаёт администратор сервиса. */
export function LoginScreen() {
  const queryClient = useQueryClient()
  const { rateLimited } = useAuth()
  const [token, setTokenValue] = useState('')
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const value = token.trim()
    if (!value) return
    setBusy(true)
    setError(null)
    setToken(value, remember)
    try {
      await fetchMe()
      await queryClient.invalidateQueries()
    } catch (err) {
      clearToken()
      if (err instanceof ApiError && err.status === 401) setError('Токен не подошёл. Проверьте его или запросите новый.')
      else if (err instanceof ApiError && err.status === 429) setError('Слишком много попыток. Подождите минуту.')
      else setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Center mih="100vh" px="md">
      <Paper withBorder p="xl" maw={440} w="100%">
        <form onSubmit={submit}>
          <Stack gap="md">
            <div>
              <Title order={2}>PI-Planner</Title>
              <Text c="dimmed" size="sm" mt={4}>
                Войдите по токену доступа. Его выдаёт администратор сервиса.
              </Text>
            </div>
            {(error || rateLimited) && (
              <Alert color="red" role="alert">
                {error ?? 'Слишком много неверных попыток. Подождите минуту и повторите.'}
              </Alert>
            )}
            <PasswordInput
              label="Токен доступа"
              value={token}
              onChange={(e) => setTokenValue(e.currentTarget.value)}
              autoComplete="off"
              data-autofocus
              required
            />
            <Checkbox
              label="Запомнить на этом устройстве"
              checked={remember}
              onChange={(e) => setRemember(e.currentTarget.checked)}
            />
            <Button type="submit" loading={busy} disabled={!token.trim()}>
              Войти
            </Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  )
}
