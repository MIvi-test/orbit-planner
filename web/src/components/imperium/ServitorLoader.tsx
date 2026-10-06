import { useEffect, useState } from 'react'
import { Stack, Text } from '@mantine/core'

const CAPTIONS = [
  'СЕРВИТОРЫ ПЕРЕНОСЯТ СВИТКИ…',
  'ДУХ МАШИНЫ ПРОБУЖДАЕТСЯ…',
  'АДЕПТЫ СВЕРЯЮТ ЛИТАНИИ…',
  'СЕРВОЧЕРЕП СКАНИРУЕТ ДАННЫЕ…',
]

export type ServitorVariant = 'inline' | 'panel' | 'fullscreen'

function ServoSkull({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" className="servitor__svg">
      {/* механическая рука */}
      <g className="servitor__arm" stroke="currentColor" strokeWidth="2.500" fill="none" strokeLinecap="square">
        <path d="M6 40l10-8 8 4" />
        <circle cx="6" cy="40" r="2.500" fill="currentColor" />
      </g>
      {/* сервочереп */}
      <g className="servitor__skull" fill="currentColor">
        <path d="M30 8c-6 0-10 4-10 9 0 3 1.500 5 3.500 6.200V28h2.500v-2h1v2h3v-2h1v2h2.500v-4.800c2-1.200 3.500-3.200 3.500-6.200 0-5-4-9-10-9z" />
        <circle cx="27" cy="16" r="2" fill="var(--mantine-color-body)" />
        <circle cx="34" cy="16" r="2" fill="var(--mantine-color-body)" />
      </g>
      {/* шестерня */}
      <g className="servitor__gear" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="38" cy="38" r="5" />
        <path d="M38 30v3M38 43v3M30 38h3M43 38h3" strokeWidth="3" />
      </g>
    </svg>
  )
}

/** Сервиторы: единый индикатор загрузки темы «Империум» с циклическими подписями. */
export function ServitorLoader({ variant = 'panel', label }: { variant?: ServitorVariant; label?: string }) {
  const [i, setI] = useState(0)
  useEffect(() => {
    if (label) return
    const id = window.setInterval(() => setI((n) => (n + 1) % CAPTIONS.length), 2200)
    return () => window.clearInterval(id)
  }, [label])
  const size = variant === 'inline' ? 28 : variant === 'panel' ? 56 : 96
  const text = label ?? CAPTIONS[i]
  const body = (
    <Stack align="center" gap={variant === 'inline' ? 2 : 8} className={`servitor servitor--${variant}`}>
      <ServoSkull size={size} />
      <Text size={variant === 'inline' ? 'xs' : 'sm'} fw={600} role="status" style={{ letterSpacing: '0.08em', color: 'var(--mantine-color-green-5, #39d98a)' }} className="mono">
        {text}
      </Text>
    </Stack>
  )
  if (variant === 'fullscreen') {
    return <div className="servitor-fullscreen">{body}</div>
  }
  return body
}
