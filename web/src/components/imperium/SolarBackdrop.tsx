/** «Карта Империума Солар»: декоративная схема Солнечной системы за звёздной картой (оригинальный рисунок). */
export function SolarBackdrop({ cx, cy }: { cx: number; cy: number }) {
  const gold = 'var(--imp-gold)'
  // Пояс астероидов: детерминированные точки по кольцу
  const belt = Array.from({ length: 110 }, (_, i) => {
    const a = (i / 110) * Math.PI * 2 + Math.sin(i * 12.9898) * 0.04
    const r = 205 + Math.sin(i * 78.233) * 9
    return [cx + r * Math.cos(a), cy + r * Math.sin(a), 0.8 + (Math.sin(i * 39.4) + 1) * 0.6] as const
  })
  const mars = { x: cx + 110 * Math.cos(-0.7), y: cy + 110 * Math.sin(-0.7) }
  return (
    <g pointerEvents="none" aria-hidden="true" opacity={0.55}>
      {/* орбиты планет */}
      {[60, 110, 160, 260, 330, 400].map((r) => (
        <circle key={r} cx={cx} cy={cy} r={r} fill="none" stroke={gold} strokeOpacity={0.22} strokeDasharray="3 6" />
      ))}
      {/* линии Варпа */}
      <g fill="none" stroke={gold} strokeOpacity={0.18} strokeDasharray="10 8">
        <path d={`M ${cx - 480} ${cy - 150} Q ${cx} ${cy + 40} ${cx + 480} ${cy - 190}`} />
        <path d={`M ${cx - 470} ${cy + 220} Q ${cx - 80} ${cy - 40} ${cx + 460} ${cy + 180}`} />
      </g>
      {/* пояс астероидов */}
      {belt.map(([x, y, r], i) => (
        <circle key={i} cx={x} cy={y} r={r} fill={gold} opacity={0.5} />
      ))}
      {/* Терра в центре */}
      <circle cx={cx} cy={cy} r={20} fill="#1d3f8f" stroke={gold} strokeWidth={1.500} />
      <path d={`M ${cx - 10} ${cy - 4} q 6 -8 12 -2 q -2 6 -8 8 z M ${cx + 2} ${cy + 6} q 6 -2 8 -8 q 2 8 -4 10 z`} fill="#39d98a" opacity={0.6} />
      <text x={cx} y={cy + 38} textAnchor="middle" fontSize={11} fill={gold} fontFamily="var(--font-heading)" letterSpacing="2">
        ТЕРРА
      </text>
      {/* Марс — шестерня */}
      <g transform={`translate(${mars.x} ${mars.y})`} fill="none" stroke={gold} strokeWidth={1.600}>
        <circle r={9} />
        <circle r={3} fill={gold} />
        {Array.from({ length: 8 }).map((_, i) => (
          <line key={i} x1={0} y1={-9} x2={0} y2={-14} transform={`rotate(${i * 45})`} strokeWidth={3} />
        ))}
      </g>
      <text x={mars.x} y={mars.y + 28} textAnchor="middle" fontSize={10} fill={gold} fontFamily="var(--font-heading)" letterSpacing="2">
        МАРС
      </text>
    </g>
  )
}
