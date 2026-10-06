import type { ReactNode } from 'react'
import { Stack, Text } from '@mantine/core'
import { ApiError, ServiceUnavailableError } from '../../api/client'
import { Skull, Star } from './ImperiumIcons'

/** Подпись типа ошибки в панели «Гнев Императора». */
export function wrathKind(error: unknown): string {
  if (error instanceof ServiceUnavailableError) return 'ВАРП-БУРЯ'
  if (error instanceof ApiError && error.status === 400) return 'ЕРЕСЬ В ДАННЫХ'
  return 'НАРУШЕНИЕ ЛИТАНИЙ ПЛАНА'
}

/** problems из ответа 400 — построчно моноширинным шрифтом. */
function problemsOf(error: unknown): string[] {
  if (error instanceof ApiError && error.body && typeof error.body === 'object') {
    const p = (error.body as { problems?: unknown }).problems
    if (Array.isArray(p)) return p.map(String)
  }
  return []
}

/** «Гнев Императора»: красная панель с тлеющим краем. Исходный текст ошибки всегда виден. */
export function WrathPanel({ error, title, children }: { error: unknown; title?: string; children?: ReactNode }) {
  const lines = problemsOf(error)
  const text = error instanceof Error ? error.message : String(error)
  return (
    <div className="wrath-panel" role="alert">
      <Stack gap={6}>
        <Text fw={700} className="wrath-panel__title">
          <Skull size={20} style={{ verticalAlign: '-4px', marginRight: 8 }} />
          ГНЕВ ИМПЕРАТОРА · {wrathKind(error)}
        </Text>
        {title && <Text fw={600}>{title}</Text>}
        <Text size="sm" className="mono">{text}</Text>
        {lines.length > 0 && (
          <pre className="mono wrath-panel__lines">{lines.join('\n')}</pre>
        )}
        {children}
      </Stack>
    </div>
  )
}

/** «Ультрамарины»: синяя панель с золотой каймой для принятых файлов, пересчёта плана, KPI в норме. */
export function VictoryPanel({ children, title = 'ЗАДАЧА ВЫПОЛНЕНА ВО СЛАВУ ИМПЕРАТОРА' }: { children?: ReactNode; title?: string }) {
  return (
    <div className="victory-panel" role="status">
      <Text fw={700} className="victory-panel__title">
        <Star size={18} style={{ verticalAlign: '-3px', marginRight: 8 }} />
        {title}
      </Text>
      {children}
    </div>
  )
}
