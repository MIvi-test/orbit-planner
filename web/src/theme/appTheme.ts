/**
 * Темы интерфейса = семейство палитры × режим (светлый или тёмный).
 * Режим — это цветовая схема Mantine, её переключает кнопка ☀/☾. Семейство —
 * атрибут `data-app-theme` на <html>, под него в tokens.css переопределены
 * цвета для обоих режимов. «Стандартная» атрибута не имеет.
 */
export type AppTheme = 'default' | 'pinkie' | 'dracula' | 'violet'

export const THEMES: { value: AppTheme; label: string }[] = [
  { value: 'default', label: 'Стандартный' },
  { value: 'pinkie', label: 'Розовый' },
  { value: 'dracula', label: 'Кровавый' },
  { value: 'violet', label: 'Фиолетовый' },
]

const KEY = 'pi-planner-app-theme'

export function storedTheme(): AppTheme {
  try {
    const v = window.localStorage.getItem(KEY)
    if (THEMES.some((t) => t.value === v)) return v as AppTheme
  } catch {
    /* хранилище недоступно */
  }
  return 'default'
}

/** Ставит атрибут и запоминает выбор; режим (светлый/тёмный) не трогает. */
export function applyAppTheme(theme: AppTheme) {
  const root = document.documentElement
  if (theme === 'default') root.removeAttribute('data-app-theme')
  else root.setAttribute('data-app-theme', theme)
  try {
    window.localStorage.setItem(KEY, theme)
  } catch {
    /* приватный режим: тема живёт до перезагрузки */
  }
}
