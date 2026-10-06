/**
 * Кто вошёл (ADR-027). `GET /api/me` отвечает и при отключённой авторизации
 * (`auth: 'off'`, роль admin), поэтому экран входа появляется ровно тогда, когда
 * сервер потребовал токен и ответил 401.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, fetchMe, type MeResponse } from '../api/client'
import { UNAUTHORIZED_EVENT, clearToken, roleAllows, type Role } from '../api/auth'

interface AuthValue {
  me: MeResponse | undefined
  isLoading: boolean
  needsLogin: boolean
  /** Сервер заблокировал вход с этого адреса на минуту (слишком много неверных токенов). */
  rateLimited: boolean
  /** Хватает ли роли для действия. При выключенной авторизации — всегда да. */
  can: (needed: Role) => boolean
  logout: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['me'], queryFn: fetchMe, retry: false, staleTime: 60_000 })

  // Любой запрос, получивший 401 (токен отозвали), возвращает на экран входа.
  useEffect(() => {
    const onUnauthorized = () => queryClient.invalidateQueries({ queryKey: ['me'] }, { cancelRefetch: false })
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [queryClient])

  const logout = useCallback(() => {
    clearToken()
    // Данные прежнего пользователя не должны остаться в кэше; запрос `me` оставляем:
    // его повтор вернёт 401 и покажет экран входа.
    queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' })
    queryClient.invalidateQueries({ queryKey: ['me'] })
  }, [queryClient])

  // React Query на время повторного запроса сбрасывает ошибку (status → pending). Без
  // «залипания» экран входа на этот миг заменился бы загрузчиком и потерял своё
  // сообщение об ошибке; пока нет успешного ответа, остаёмся на экране входа.
  const rateLimited = query.error instanceof ApiError && query.error.status === 429
  const unauthorized = (query.error instanceof ApiError && query.error.status === 401) || rateLimited
  const lockedRef = useRef(false)
  if (unauthorized) lockedRef.current = true
  else if (query.data) lockedRef.current = false
  const needsLogin = unauthorized || (lockedRef.current && !query.data)

  const value = useMemo<AuthValue>(() => {
    return {
      me: query.data,
      isLoading: query.isPending && !needsLogin,
      needsLogin,
      rateLimited,
      can: (needed) => roleAllows(query.data?.role, needed),
      logout,
    }
  }, [query.data, query.isPending, needsLogin, rateLimited, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth() вызван вне <AuthProvider>')
  return ctx
}
