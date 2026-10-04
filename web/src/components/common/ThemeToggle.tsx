import { ActionIcon, Tooltip, useComputedColorScheme, useMantineColorScheme } from '@mantine/core'

/** Выбор сохраняет MantineProvider; до первого выбора действует тема ОС. */
export function ThemeToggle() {
  const current = useComputedColorScheme('light', { getInitialValueInEffect: false })
  const { setColorScheme } = useMantineColorScheme()
  const next = current === 'dark' ? 'light' : 'dark'
  const label = next === 'dark' ? 'Включить тёмную тему' : 'Включить светлую тему'

  return (
    <Tooltip label={label}>
      <ActionIcon
        variant="subtle"
        color="post"
        size="lg"
        aria-label={label}
        onClick={() => setColorScheme(next)}
      >
        <span aria-hidden="true" style={{ fontSize: 20, lineHeight: 1 }}>
          {next === 'dark' ? '☾' : '☀'}
        </span>
      </ActionIcon>
    </Tooltip>
  )
}
