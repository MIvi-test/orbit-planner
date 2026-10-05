/**
 * Темы интерфейса. Mantine знает только светлую и тёмную схему, поэтому
 * «Розовая» (светлая) и «Кровавая» (тёмная) — это схема + атрибут
 * `data-app-theme` на <html>, под который в tokens.css переопределены цвета.
 */
export type AppTheme = 'light' | 'dark' | 'pinkie' | 'dracula'

export const THEMES: { value: AppTheme; label: string; scheme: 'light' | 'dark' }[] = [
  { value: 'light', label: 'Светлая', scheme: 'light' },
  { value: 'dark', label: 'Тёмная', scheme: 'dark' },
  { value: 'pinkie', label: 'Розовая', scheme: 'light' },
  { value: 'dracula', label: 'Кровавая', scheme: 'dark' },
]

const KEY = 'pi-planner-app-theme'

export function storedTheme(): AppTheme | null {
  try {
    const v = window.localStorage.getItem(KEY)
    return THEMES.some((t) => t.value === v) ? (v as AppTheme) : null
  } catch {
    return null
  }
}

/** Ставит атрибут и запоминает выбор; цветовую схему Mantine переключает вызывающий. */
export function applyAppTheme(theme: AppTheme) {
  const root = document.documentElement
  if (theme === 'pinkie' || theme === 'dracula') root.setAttribute('data-app-theme', theme)
  else root.removeAttribute('data-app-theme')
  try {
    window.localStorage.setItem(KEY, theme)
  } catch {
    /* приватный режим: тема живёт до перезагрузки */
  }
}
