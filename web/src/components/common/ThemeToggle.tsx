import { ActionIcon, Group, Menu, Tooltip, UnstyledButton, useComputedColorScheme, useMantineColorScheme } from '@mantine/core'
import { IconChevronDown } from '@tabler/icons-react'
import { useState } from 'react'
import { THEMES, applyAppTheme, storedTheme, type AppTheme } from '../../theme/appTheme'

/** Кружок темы: половина — фон, половина — акцент; цвета зависят от режима. */
const SWATCH: Record<AppTheme, { light: [string, string]; dark: [string, string] }> = {
  default: { light: ['#ffffff', '#14213d'], dark: ['#141b2e', '#7fa6d9'] },
  pinkie: { light: ['#ffd6e8', '#ec2494'], dark: ['#4d2438', '#f783ac'] },
  dracula: { light: ['#fbeaec', '#b3121c'], dark: ['#1c0910', '#c1121f'] },
  violet: { light: ['#f7f4ff', '#4c1d95'], dark: ['#1e1038', '#a78bfa'] },
}

function Dot({ theme, mode, active }: { theme: AppTheme; mode: 'light' | 'dark'; active?: boolean }) {
  const [bg, accent] = SWATCH[theme][mode]
  return (
    <span
      aria-hidden="true"
      style={{
        display: 'inline-block',
        width: 26,
        height: 26,
        borderRadius: '50%',
        background: `linear-gradient(135deg, ${bg} 50%, ${accent} 50%)`,
        border: `2px solid ${active ? 'var(--mantine-color-text)' : 'var(--mantine-color-default-border)'}`,
      }}
    />
  )
}

/** Кнопка ☀/☾ меняет светлый и тёмный режим; стрелка вниз открывает цветные кружки семейств тем. */
export function ThemeToggle() {
  const mode = useComputedColorScheme('dark', { getInitialValueInEffect: false })
  const { setColorScheme } = useMantineColorScheme()
  const [theme, setTheme] = useState<AppTheme>(storedTheme)

  const choose = (value: AppTheme) => {
    setTheme(value)
    applyAppTheme(value)
  }

  const next = mode === 'dark' ? 'light' : 'dark'
  const label = next === 'dark' ? 'Включить тёмный режим' : 'Включить светлый режим'

  return (
    <Group gap={0} wrap="nowrap">
      <Tooltip label={label}>
        <ActionIcon variant="subtle" color="post" size="lg" aria-label={label} onClick={() => setColorScheme(next)}>
          <span aria-hidden="true" style={{ fontSize: 20, lineHeight: 1 }}>
            {mode === 'dark' ? '☀' : '☾'}
          </span>
        </ActionIcon>
      </Tooltip>
      <Menu position="bottom-start" withinPortal shadow="md" width="auto">
        <Menu.Target>
          <Tooltip label="Выбрать тему">
            <ActionIcon variant="subtle" color="gray" size="md" aria-label="Выбрать тему оформления">
              <IconChevronDown size={16} stroke={2} />
            </ActionIcon>
          </Tooltip>
        </Menu.Target>
        <Menu.Dropdown p={8}>
          <Group gap={8} wrap="nowrap">
            {THEMES.map((t) => (
              <Tooltip key={t.value} label={t.label}>
                <UnstyledButton aria-label={t.label} onClick={() => choose(t.value)} style={{ lineHeight: 0 }}>
                  <Dot theme={t.value} mode={mode} active={theme === t.value} />
                </UnstyledButton>
              </Tooltip>
            ))}
          </Group>
        </Menu.Dropdown>
      </Menu>
    </Group>
  )
}
