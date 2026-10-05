import type { CSSProperties } from 'react'

/** Общие стили области карты: цвета берутся из переменных текущей темы (tokens.css). */
export const panel: CSSProperties = {
  background: 'var(--field)',
  border: '1px solid var(--sm-border)',
  borderRadius: 8,
  padding: 16,
}

export const muted: CSSProperties = { color: 'var(--sm-muted)' }

export const chip = (active: boolean): CSSProperties => ({
  all: 'unset',
  cursor: 'pointer',
  padding: '3px 10px',
  borderRadius: 2,
  fontSize: 13,
  border: `1px solid ${active ? 'var(--star)' : 'var(--sm-border)'}`,
  background: active ? 'color-mix(in srgb, var(--star) 14%, transparent)' : 'transparent',
  color: 'var(--star)',
})
