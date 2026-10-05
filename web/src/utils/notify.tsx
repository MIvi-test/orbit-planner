import type { ReactNode } from 'react'
import { notifications as base } from '@mantine/notifications'
import { Text } from '@mantine/core'
import { currentTheme } from '../theme/appTheme'

type Show = Parameters<typeof base.show>[0]

type Kind = 'success' | 'info' | 'warning' | 'critical'

function kindOf(color: unknown): Kind {
  if (color === 'red') return 'critical'
  if (color === 'yellow' || color === 'orange') return 'warning'
  if (color === 'teal' || color === 'green') return 'success'
  return 'info'
}

const MACHINE: Record<Exclude<Kind, 'success'>, string> = {
  info: 'ДУХ МАШИНЫ: ЛИТАНИЯ ПОДТВЕРЖДЕНА',
  warning: 'ДУХ МАШИНЫ: ДУХ МАШИНЫ БЕСПОКОЕН',
  critical: 'ДУХ МАШИНЫ: ЕРЕСЬ ОБНАРУЖЕНА',
}

/**
 * Уведомления. В обычных темах — как раньше. В теме «Империум» тип дублируется словом:
 * успех — «Ультрамарины», остальное — терминал Адептус Механикус. Исходный текст сохраняется.
 */
export const notifications = {
  show(options: Show) {
    if (currentTheme() !== 'imperium') return base.show(options)
    const kind = kindOf(options.color)
    const original = options.title as ReactNode
    const head = kind === 'success' ? 'ЗАДАЧА ВЫПОЛНЕНА ВО СЛАВУ ИМПЕРАТОРА' : MACHINE[kind]
    return base.show({
      ...options,
      className: `imperium-note imperium-note--${kind}`,
      title: head,
      message: (
        <>
          {original && <Text fw={600} size="sm" component="div">{original}</Text>}
          {options.message}
        </>
      ),
    })
  },
}
