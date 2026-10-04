import { AppShell, Badge, Button, Group, ScrollArea, Tabs, Text, Tooltip } from '@mantine/core'
import type { ReactNode } from 'react'
import { HealthBadge } from './HealthBadge'
import { PiBadge } from './PiBadge'
import { PiContextSelect } from './PiContextSelect'
import { RunSelect } from './RunSelect'
import type { ScreenId } from '../../hooks/useHashRoute'
import { useAuth } from '../../hooks/useAuth'
import { ROLE_LABEL } from '../../api/auth'
import { ThemeToggle } from '../common/ThemeToggle'

const NAV: { id: ScreenId; label: string }[] = [
  { id: 'upload', label: 'Загрузка' },
  { id: 'plan', label: 'План квартала' },
  { id: 'risks', label: 'Риски' },
  { id: 'starmap', label: 'Звёздная карта' },
  { id: 'kpi', label: 'KPI' },
  { id: 'roles', label: 'Роли и ёмкость' },
  { id: 'profiles', label: 'Профили' },
  { id: 'data', label: 'Данные' },
]

export function Shell({
  screen,
  onNavigate,
  children,
}: {
  screen: ScreenId
  onNavigate: (id: ScreenId) => void
  children: ReactNode
}) {
  const { me, logout } = useAuth()
  return (
    <AppShell header={{ height: 106 }} padding="md">
      <AppShell.Header>
        <Group justify="space-between" px="md" pt={10} wrap="nowrap">
          <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
            <Text fw={600} size="lg" style={{ whiteSpace: 'nowrap' }}>
              PI-Planner
            </Text>
            <ThemeToggle />
            <Text size="sm" c="dimmed">
              ПочтаТех
            </Text>
          </Group>
          <Group gap="md" wrap="nowrap">
            <PiContextSelect />
            <PiBadge />
            <RunSelect />
            <HealthBadge />
            {me && me.auth === 'required' && (
              <Group gap={4} wrap="nowrap" style={{ flexShrink: 0 }}>
                <Tooltip label={`${me.name} · роль: ${ROLE_LABEL[me.role]}`}>
                  <Badge variant="light" color="gray" size="sm" maw={110} style={{ flexShrink: 0 }}>
                    {me.name}
                  </Badge>
                </Tooltip>
                <Button variant="subtle" size="compact-xs" onClick={logout} style={{ flexShrink: 0 }}>
                  Выйти
                </Button>
              </Group>
            )}
          </Group>
        </Group>
        <ScrollArea scrollbarSize={4} type="auto" px="md">
          <Tabs
            value={screen}
            onChange={(v) => v && onNavigate(v as ScreenId)}
            variant="outline"
          >
            <Tabs.List style={{ flexWrap: 'nowrap' }}>
              {NAV.map((item) => (
                <Tabs.Tab key={item.id} value={item.id} style={{ whiteSpace: 'nowrap' }}>
                  {item.label}
                </Tabs.Tab>
              ))}
            </Tabs.List>
          </Tabs>
        </ScrollArea>
      </AppShell.Header>
      <AppShell.Main>{children}</AppShell.Main>
    </AppShell>
  )
}
