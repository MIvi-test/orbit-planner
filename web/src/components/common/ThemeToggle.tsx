import { ActionIcon, Group, Menu, Tooltip, UnstyledButton, useComputedColorScheme, useMantineColorScheme } from '@mantine/core'
import { IconChevronDown } from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { THEMES, applyAppTheme, storedTheme, type AppTheme } from '../../theme/appTheme'

/** Кружок темы: два цвета — фон и акцент. */
const SWATCH: Record<AppTheme, [string, string]> = {
  light: ['#ffffff', '#14213d'],
  dark: ['#141b2e', '#7fa6d9'],
  pinkie: ['#ffd6e8', '#ec2494'],
  dracula: ['#1c0910', '#c1121f'],
}

function Dot({ theme, active }: { theme: AppTheme; active?: boolean }) {
  const [bg, accent] = SWATCH[theme]
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

/** Кнопка «светлая/тёмная» и рядом стрелка вниз со списком тем в виде цветных кружков. */
export function ThemeToggle() {
  const computed = useComputedColorScheme('light', { getInitialValueInEffect: false })
  const { setColorScheme } = useMantineColorScheme()
  const [theme, setTheme] = useState<AppTheme>(() => storedTheme() ?? computed)

  const choose = (value: AppTheme) => {
    const entry = THEMES.find((t) => t.value === value)
    if (!entry) return
    setTheme(value)
    applyAppTheme(value)
    setColorScheme(entry.scheme)
  }

  useEffect(() => {
    const saved = storedTheme()
    if (saved) applyAppTheme(saved)
  }, [])

  const next: AppTheme = computed === 'dark' ? 'light' : 'dark'
  const label = next === 'dark' ? 'Включить тёмную тему' : 'Включить светлую тему'

  return (
    <Group gap={0} wrap="nowrap">
      <Tooltip label={label}>
        <ActionIcon variant="subtle" color="post" size="lg" aria-label={label} onClick={() => choose(next)}>
          <span aria-hidden="true" style={{ fontSize: 20, lineHeight: 1 }}>
            {computed === 'dark' ? '☀' : '☾'}
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
                  <Dot theme={t.value} active={theme === t.value} />
                </UnstyledButton>
              </Tooltip>
            ))}
          </Group>
        </Menu.Dropdown>
      </Menu>
    </Group>
  )
}
