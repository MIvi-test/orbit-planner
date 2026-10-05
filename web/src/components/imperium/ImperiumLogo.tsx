/** Собственная эмблема: двуглавая аквила, шестерня и череп. Не копирует официальных логотипов. */
export function ImperiumLogo({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="PI-Planner" style={{ color: 'var(--mantine-primary-color-filled)' }}>
      {/* шестерня */}
      <g fill="none" stroke="currentColor" strokeWidth="2.200">
        <circle cx="32" cy="34" r="15" />
        {Array.from({ length: 12 }).map((_, i) => (
          <line key={i} x1="32" y1="14" x2="32" y2="18" transform={`rotate(${i * 30} 32 34)`} strokeWidth="3.500" strokeLinecap="square" />
        ))}
      </g>
      {/* крылья */}
      <g fill="currentColor">
        <path d="M30 24C22 18 12 18 4 22c6 1 9 4 10 8-4 0-7 2-9 5 5-1 9 0 12 3-2 2-3 4-3 7 5-3 9-8 16-8z" />
        <path d="M34 24c8-6 18-6 26-2-6 1-9 4-10 8 4 0 7 2 9 5-5-1-9 0-12 3 2 2 3 4 3 7-5-3-9-8-16-8z" />
        {/* головы аквилы */}
        <path d="M26 16l-5-3 1 5 4 1z" />
        <path d="M38 16l5-3-1 5-4 1z" />
      </g>
      {/* череп */}
      <g fill="var(--mantine-color-body)" stroke="currentColor" strokeWidth="1.400">
        <path d="M32 24c-5 0-8 3-8 7 0 2.500 1 4 2.500 5v4h3v-2h1v2h3v-2h1v2h3v-4c1.500-1 2.500-2.500 2.500-5 0-4-3-7-8-7z" />
      </g>
      <circle cx="29" cy="31" r="1.800" fill="currentColor" />
      <circle cx="35" cy="31" r="1.800" fill="currentColor" />
    </svg>
  )
}
