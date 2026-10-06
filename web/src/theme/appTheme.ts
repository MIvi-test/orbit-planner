/**
 * Темы интерфейса = семейство палитры × режим (светлый или тёмный).
 * Режим — это цветовая схема Mantine, её переключает кнопка ☀/☾. Семейство —
 * атрибут `data-app-theme` на <html>, под него в tokens.css переопределены
 * цвета для обоих режимов. «Стандартная» атрибута не имеет.
 */
import { useSyncExternalStore } from 'react'

export type AppTheme = 'default' | 'pinkie' | 'dracula' | 'violet' | 'imperium'

export const THEMES: { value: AppTheme; label: string }[] = [
  { value: 'default', label: 'Стандартный' },
  { value: 'pinkie', label: 'Розовый' },
  { value: 'dracula', label: 'Кровавый' },
  { value: 'violet', label: 'Фиолетовый' },
  { value: 'imperium', label: 'Империум' },
]

const KEY = 'pi-planner-app-theme'
const listeners = new Set<() => void>()

function subscribe(cb: () => void) {
  listeners.add(cb)
  return () => {
    listeners.delete(cb)
  }
}

/** Текущая палитра, прочитанная из атрибута на <html>. */
export function currentTheme(): AppTheme {
  const v = document.documentElement.getAttribute('data-app-theme')
  return THEMES.some((t) => t.value === v) ? (v as AppTheme) : 'default'
}

/** Реактивная палитра: компоненты перерисовываются при смене темы. */
export function useAppTheme(): AppTheme {
  return useSyncExternalStore(subscribe, currentTheme, () => 'default' as AppTheme)
}

/** Включена ли тема «Империум» (меняет подписи, шапку, индикаторы и уведомления). */
export const useImperium = () => useAppTheme() === 'imperium'

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
  listeners.forEach((cb) => cb())
  try {
    window.localStorage.setItem(KEY, theme)
  } catch {
    /* приватный режим: тема живёт до перезагрузки */
  }
}
