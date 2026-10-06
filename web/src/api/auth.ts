/**
 * Токен доступа (ADR-027). По умолчанию живёт в sessionStorage — закрыли вкладку,
 * вошли заново; «запомнить» кладёт его в localStorage. Любой из хранилищ может
 * оказаться недоступным (приватный режим), поэтому обращения обёрнуты в try/catch.
 */
const KEY = 'pi-planner-token'

export const UNAUTHORIZED_EVENT = 'pi-planner:unauthorized'

function read(storage: () => Storage): string | null {
  try {
    return storage().getItem(KEY)
  } catch {
    return null
  }
}

export function getToken(): string | null {
  return read(() => window.sessionStorage) ?? read(() => window.localStorage)
}

export function setToken(token: string, remember: boolean): void {
  clearToken()
  try {
    ;(remember ? window.localStorage : window.sessionStorage).setItem(KEY, token)
  } catch {
    /* хранилище недоступно: токен живёт до перезагрузки только если приложение его передаст заново */
  }
}

export function clearToken(): void {
  for (const storage of [() => window.sessionStorage, () => window.localStorage]) {
    try {
      storage().removeItem(KEY)
    } catch {
      /* ignore */
    }
  }
}

export function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** Сообщить приложению, что сервер ответил 401: пора показать экран входа. */
export function notifyUnauthorized(): void {
  window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
}

export type Role = 'viewer' | 'planner' | 'admin'

const RANK: Record<Role, number> = { viewer: 0, planner: 1, admin: 2 }

export function roleAllows(role: Role | undefined, needed: Role): boolean {
  return role !== undefined && RANK[role] >= RANK[needed]
}

export const ROLE_LABEL: Record<Role, string> = {
  viewer: 'просмотр',
  planner: 'планировщик',
  admin: 'администратор',
}
