import { ActionIcon, AppShell, Badge, Group, ScrollArea, Text, Tooltip, UnstyledButton } from '@mantine/core'
import { useLocalStorage } from '@mantine/hooks'
import {
  IconChartDots3,
  IconChevronsLeft,
  IconCircleX,
  IconChevronsRight,
  IconCloudUpload,
  IconDatabaseSearch,
  IconGauge,
  IconLayoutDashboard,
  IconTimeline,
  IconUserCircle,
  IconUsersGroup,
  IconSparkles,
  IconAlertTriangle,
  type Icon,
} from '@tabler/icons-react'
import type { ReactNode } from 'react'
import { HealthBadge } from './HealthBadge'
import { PiBadge } from './PiBadge'
import { PiContextSelect } from './PiContextSelect'
import { RunSelect } from './RunSelect'
import type { ScreenId } from '../../hooks/useHashRoute'
import { useAuth } from '../../hooks/useAuth'
import { ROLE_LABEL } from '../../api/auth'
import { ThemeToggle } from '../common/ThemeToggle'
import { useImperium } from '../../theme/appTheme'
import { LITANIES, useLabel } from '../../theme/imperiumLabels'
import { useHealth } from '../../hooks/useHealth'
import { useRun } from '../../hooks/useRun'
import { ImperiumLogo } from '../imperium/ImperiumLogo'
import { WarpBeacon, type BeaconState } from '../imperium/WarpBeacon'
import { Aquila } from '../imperium/ImperiumIcons'

const NAV: { id: ScreenId; label: string; icon: Icon }[] = [
  { id: 'summary', label: 'Сводка', icon: IconLayoutDashboard },
  { id: 'assistant', label: 'ИИ-ассистент', icon: IconSparkles },
  { id: 'upload', label: 'Загрузка', icon: IconCloudUpload },
  { id: 'plan', label: 'План квартала', icon: IconTimeline },
  { id: 'risks', label: 'Риски', icon: IconAlertTriangle },
  { id: 'starmap', label: 'Звёздная карта', icon: IconChartDots3 },
  { id: 'kpi', label: 'KPI', icon: IconGauge },
  { id: 'roles', label: 'Роли и ёмкость', icon: IconUsersGroup },
  { id: 'profiles', label: 'Профили', icon: IconUserCircle },
  { id: 'data', label: 'Данные', icon: IconDatabaseSearch },
]

const ROLE_COLOR = { viewer: 'gray', planner: 'blue', admin: 'grape' } as const

const NAV_OPEN = 250
const NAV_COLLAPSED = 64

export function Shell({
  screen,
  onNavigate,
  children,
}: {
  screen: ScreenId
  onNavigate: (id: ScreenId, query?: Record<string, string>) => void
  children: ReactNode
}) {
  const { me, logout } = useAuth()
  const imperium = useImperium()
  const label = useLabel()
  const health = useHealth()
  const { runs } = useRun()
  const beacon: BeaconState = health.isError ? 'offline' : runs.length > 0 ? 'active' : 'empty'
  const litany = LITANIES[new Date().getDate() % LITANIES.length]
  const [collapsed, setCollapsed] = useLocalStorage({ key: 'pi-planner-nav-collapsed', defaultValue: false })
  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: collapsed ? NAV_COLLAPSED : imperium ? 310 : NAV_OPEN, breakpoint: 0 }}
      padding="md"
      styles={{ navbar: { transition: 'width 150ms ease' } }}
    >
      <AppShell.Header>
        <Group justify="space-between" px="md" h="100%" wrap="nowrap">
          <Group gap="sm" wrap="nowrap" style={{ flexShrink: 0 }}>
            {imperium && <ImperiumLogo size={40} />}
            <div style={{ lineHeight: 1.15 }}>
              <Text fw={700} size="lg" style={{ whiteSpace: 'nowrap', fontFamily: 'var(--font-heading)' }}>
                {imperium ? 'PI-PLANNER' : 'PI-Planner'}
              </Text>
              <Text size="xs" c="dimmed">
                {imperium ? 'ИМПЕРИУМ ПЛАНИРОВАНИЯ' : 'ПочтаТех'}
              </Text>
            </div>
            <ThemeToggle />
          </Group>
          <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
            <PiContextSelect />
            <RunSelect />
            <div className="show-from-1800">
              <PiBadge />
            </div>
            {imperium ? <WarpBeacon state={beacon} /> : <HealthBadge />}
            {me && me.auth === 'required' && (
              <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
                <Text size="sm" fw={600} style={{ whiteSpace: 'nowrap' }} maw={140} truncate>
                  {me.name}
                </Text>
                <Badge variant="light" color={ROLE_COLOR[me.role]} size="lg" style={{ textTransform: 'none', flexShrink: 0 }}>
                  {ROLE_LABEL[me.role]}
                </Badge>
                <Tooltip label="Выйти из системы">
                  <ActionIcon variant="subtle" color="gray" size="lg" radius="xl" onClick={logout} aria-label="Выйти" className="logout-btn">
                    <IconCircleX size={24} stroke={1.7} />
                  </ActionIcon>
                </Tooltip>
              </Group>
            )}
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p={0}>
        <ScrollArea style={{ flex: collapsed ? '0 0 auto' : 1 }} scrollbarSize={4} px={8} pt="sm">
          {NAV.map((item) => {
            const Ico = item.icon
            const active = screen === item.id
            const link = (
              <UnstyledButton
                key={item.id}
                onClick={() => onNavigate(item.id)}
                aria-label={label(item.label)}
                aria-current={active ? 'page' : undefined}
                className="nav-item"
                data-active={active || undefined}
                data-ai={item.id === 'assistant' || undefined}
              >
                <Ico size={24} stroke={1.7} className="nav-icon" />
                <span className="nav-label" data-collapsed={collapsed || undefined}>
                  {label(item.label)}
                </span>
              </UnstyledButton>
            )
            return collapsed ? (
              <Tooltip key={item.id} label={label(item.label)} position="right" withArrow>
                {link}
              </Tooltip>
            ) : (
              link
            )
          })}
        </ScrollArea>
        {collapsed && (
          <div className="rail-current" aria-live="polite">
            <span>{label(NAV.find((n) => n.id === screen)?.label ?? '')}</span>
          </div>
        )}
        <div style={{ padding: '8px' }}>
          <Tooltip label={collapsed ? 'Развернуть меню' : 'Свернуть меню'} position="right">
            <UnstyledButton
              onClick={() => setCollapsed((v) => !v)}
              aria-label={collapsed ? 'Развернуть меню' : 'Свернуть меню'}
              className="nav-item"
            >
              {collapsed ? (
                <IconChevronsRight size={24} stroke={1.7} className="nav-icon" />
              ) : (
                <IconChevronsLeft size={24} stroke={1.7} className="nav-icon" />
              )}
              <span className="nav-label" data-collapsed={collapsed || undefined}>
                Свернуть меню
              </span>
            </UnstyledButton>
          </Tooltip>
        </div>
      </AppShell.Navbar>
      <AppShell.Main>
        {children}
        {imperium && (
          <footer className="imperium-footer" aria-label="Литания">
            <Aquila size={16} /> <span>{litany}</span>
          </footer>
        )}
      </AppShell.Main>
    </AppShell>
  )
}
