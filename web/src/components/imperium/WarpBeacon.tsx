import { Group, Text, Tooltip } from '@mantine/core'

export type BeaconState = 'active' | 'empty' | 'offline'

const CAPTION: Record<BeaconState, string> = {
  active: 'АСТРОНОМИКОН ВЕЩАЕТ · ДАННЫЕ ПРИНЯТЫ',
  empty: 'ТРОН ПУСТ',
  offline: 'АСТРОНОМИКОН МОЛЧИТ',
}

/** Маяк Варпа: Золотой Трон. active — светится, empty — пустой, offline — погас с красной лампой. */
export function WarpBeacon({ state }: { state: BeaconState }) {
  const gold = state === 'active'
  return (
    <Tooltip label={CAPTION[state]}>
      <Group gap={8} wrap="nowrap" className={`warp-beacon warp-beacon--${state}`} aria-label={CAPTION[state]} role="status">
        <svg width="30" height="34" viewBox="0 0 30 34" aria-hidden="true">
          {gold && <circle cx="15" cy="14" r="13" fill="var(--mantine-primary-color-filled)" opacity="0.18" className="warp-beacon__glow" />}
          {/* ступени и спинка трона */}
          <path d="M3 30h24v3H3zM6 26h18v3H6z" fill="currentColor" opacity="0.7" />
          <path d="M8 26V9l7-6 7 6v17h-3V11l-4-3-4 3v15z" fill="currentColor" />
          {/* фигура на троне */}
          {gold && (
            <g fill="var(--mantine-primary-color-filled)">
              <circle cx="15" cy="13" r="2.600" />
              <path d="M11 24c0-5 2-8 4-8s4 3 4 8z" />
            </g>
          )}
          {state === 'offline' && <circle cx="26" cy="5" r="3" fill="#e0561b" className="warp-beacon__lamp" />}
        </svg>
        <Text size="xs" fw={700} className="warp-beacon__text show-from-1800" style={{ letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>
          {CAPTION[state]}
        </Text>
      </Group>
    </Tooltip>
  )
}
