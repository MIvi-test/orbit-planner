/**
 * SVG звёздной карты. Ядра — команды, точки — инженеры. Каждая точка —
 * кнопка с клавиатуры (Tab, Enter), подпись и уровень риска дублируются
 * текстом: цвет не единственный носитель смысла (docs/UI_DESIGN.md §9).
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { EngineerAbsenceRiskRow, OrbitMapRow } from '../../types/views'
import { CORE_R, VIEW_H, VIEW_W, computeLayout } from './layout'
import { useImperium } from '../../theme/appTheme'
import { SolarBackdrop } from '../../components/imperium/SolarBackdrop'
import { LEVEL_COLOR, LEVEL_WORD, gradeRadius, shortTeam, starLevel } from './risk'

/** Фон из мелких звёзд: детерминированный, чтобы картинка не менялась между отрисовками. */
const BACKDROP_STARS: [number, number, number, number][] = Array.from({ length: 140 }, (_, i) => {
  const a = Math.sin(i * 12.9898) * 43758.5453
  const b = Math.sin(i * 78.233) * 12543.2193
  const c = Math.sin(i * 39.425) * 9871.6417
  const f = (v: number) => v - Math.floor(v)
  return [f(a), f(b), 0.5 + f(c) * 1.3, 0.15 + f(a + b) * 0.5]
})

const MIN_K = 1
const MAX_K = 8

export function StarMapSvg({
  rows,
  absenceById,
  highlight,
  selectedId,
  onSelect,
  onSelectTeam,
}: {
  rows: OrbitMapRow[]
  absenceById: Map<string, EngineerAbsenceRiskRow>
  highlight: Set<string> | null
  selectedId: string | null
  onSelect: (id: string) => void
  onSelectTeam: (teamId: string) => void
}) {
  const imperium = useImperium()
  const { cores, nodes } = useMemo(() => computeLayout(rows), [rows])
  const coreById = new Map(cores.map((c) => [c.team_id, c]))
  const [hover, setHover] = useState<string | null>(null)

  // Рамка карты подстраивается под прямоугольник блока: viewBox получает его пропорции,
  // поэтому карта занимает всю область без пустых полос по бокам.
  const [box, setBox] = useState({ w: VIEW_W, h: VIEW_H })
  const aspect = box.w / Math.max(box.h, 1)
  const wide = aspect >= VIEW_W / VIEW_H
  const bh = wide ? VIEW_H : VIEW_W / aspect
  const bw = wide ? VIEW_H * aspect : VIEW_W
  const bx = (VIEW_W - bw) / 2
  const by = (VIEW_H - bh) / 2

  const openTeam = onSelectTeam

  const dim = (id: string) => highlight !== null && !highlight.has(id)

  // Масштаб и сдвиг: колесо — приближение к курсору, перетаскивание — сдвиг.
  const [view, setView] = useState({ k: 1, x: 0, y: 0 })
  const svgRef = useRef<SVGSVGElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => setBox({ w: entry.contentRect.width, h: entry.contentRect.height }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  // Колесо работает только после клика по карте — иначе оно мешает прокручивать страницу.
  const [wheelOn, setWheelOn] = useState(false)
  const drag = useRef<{ px: number; py: number; vx: number; vy: number; moved: boolean } | null>(null)
  const clamp = (v: { k: number; x: number; y: number }) => {
    const w = bw / v.k
    const h = bh / v.k
    return { k: v.k, x: Math.min(Math.max(v.x, 0), bw - w), y: Math.min(Math.max(v.y, 0), bh - h) }
  }
  const zoomAt = (factor: number, fx = 0.5, fy = 0.5) =>
    setView((v) => {
      const k = Math.min(MAX_K, Math.max(MIN_K, v.k * factor))
      if (k === v.k) return v
      const cx = v.x + (bw / v.k) * fx
      const cy = v.y + (bh / v.k) * fy
      return clamp({ k, x: cx - (bw / k) * fx, y: cy - (bh / k) * fy })
    })
  // Нативный слушатель: React вешает wheel пассивным, и страница прокручивалась бы вместе с зумом.
  useEffect(() => {
    const el = svgRef.current
    if (!el || !wheelOn) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const rect = el.getBoundingClientRect()
      zoomAt(e.deltaY < 0 ? 1.2 : 1 / 1.2, (e.clientX - rect.left) / rect.width, (e.clientY - rect.top) / rect.height)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [wheelOn])

  // Клик вне карты или Esc выключают колесо.
  useEffect(() => {
    if (!wheelOn) return
    const off = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !wrapRef.current?.contains(e.target as Node)) setWheelOn(false)
    }
    document.addEventListener('pointerdown', off)
    document.addEventListener('keydown', off)
    return () => {
      document.removeEventListener('pointerdown', off)
      document.removeEventListener('keydown', off)
    }
  }, [wheelOn])
  const onPointerDown = (e: React.PointerEvent) => {
    setWheelOn(true)
    drag.current = { px: e.clientX, py: e.clientY, vx: view.x, vy: view.y, moved: false }
  }
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current
    const rect = svgRef.current?.getBoundingClientRect()
    if (!d || !rect || view.k === 1) return
    const dx = e.clientX - d.px
    const dy = e.clientY - d.py
    if (Math.abs(dx) + Math.abs(dy) > 4) d.moved = true
    if (!d.moved) return
    setView((v) => clamp({ k: v.k, x: d.vx - (dx / rect.width) * (bw / v.k), y: d.vy - (dy / rect.height) * (bh / v.k) }))
  }
  const endDrag = () => {
    window.setTimeout(() => {
      drag.current = null
    }, 0)
  }
  const zoomBtn = {
    width: 36,
    height: 36,
    border: '1px solid var(--orbit)',
    borderRadius: 6,
    background: 'var(--field)',
    color: 'var(--star)',
    fontSize: 20,
    cursor: 'pointer',
  } as const

  return (
    <div ref={wrapRef} style={{ position: 'relative', borderRadius: 10, overflow: 'hidden', height: 'clamp(520px, 78vh, 980px)' }}>
    <div style={{ position: 'absolute', top: 8, right: 8, zIndex: 2, display: 'flex', gap: 6 }}>
      <button type="button" style={zoomBtn} onClick={() => zoomAt(1.4)} aria-label="Приблизить" title="Приблизить">+</button>
      <button type="button" style={zoomBtn} onClick={() => zoomAt(1 / 1.4)} aria-label="Отдалить" title="Отдалить">−</button>
      <button type="button" style={{ ...zoomBtn, fontSize: 13, width: 'auto', padding: '0 10px' }} onClick={() => setView({ k: 1, x: 0, y: 0 })} title="Вернуть масштаб">
        {Math.round(view.k * 100)}%
      </button>
    </div>
    <div style={{ position: 'absolute', left: 12, top: 12, zIndex: 2, padding: '4px 10px', borderRadius: 6, fontSize: 13, background: 'color-mix(in srgb, var(--field) 85%, transparent)', color: wheelOn ? 'var(--bloom)' : 'var(--orbit)', border: '1px solid var(--sm-border)' }}>
      {wheelOn ? 'Колесо мыши меняет масштаб. Esc или клик вне карты выключает' : 'Нажмите на карту, чтобы масштабировать колесом'}
    </div>
    <svg
      ref={svgRef}
      viewBox={`${bx + view.x} ${by + view.y} ${bw / view.k} ${bh / view.k}`}
      width="100%"
      height="100%"
      role="group"
      aria-label={`Звёздная карта: ${cores.length} команд, ${nodes.length} инженеров`}
      style={{ display: 'block', cursor: view.k > 1 ? 'grab' : 'default', touchAction: 'none' }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerLeave={endDrag}
      onClickCapture={(e) => {
        if (drag.current?.moved) e.stopPropagation()
      }}
    >
      <defs>
        <radialGradient id="sm-bg" cx="50%" cy="50%" r="75%">
          <stop offset="0%" style={{ stopColor: 'var(--sm-bg0)' }} />
          <stop offset="60%" style={{ stopColor: 'var(--sm-bg1)' }} />
          <stop offset="100%" style={{ stopColor: 'var(--sm-bg2)' }} />
        </radialGradient>
        <radialGradient id="sm-core" cx="50%" cy="40%" r="70%">
          <stop offset="0%" style={{ stopColor: 'var(--sm-core0)' }} />
          <stop offset="100%" style={{ stopColor: 'var(--sm-core1)' }} />
        </radialGradient>
        <filter id="sm-glow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="4" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <rect x={bx - 2000} y={by - 2000} width={bw + 4000} height={bh + 4000} fill="var(--sm-bg1)" />
      <rect x={bx} y={by} width={bw} height={bh} fill="url(#sm-bg)" />
      {BACKDROP_STARS.map(([x, y, r, o], i) => (
        <circle key={`bg-${i}`} cx={bx + x * bw} cy={by + y * bh} r={r} fill="var(--sm-dot)" opacity={o} />
      ))}

      {imperium && <SolarBackdrop cx={VIEW_W / 2} cy={VIEW_H / 2} />}

      {/* орбиты ядер */}
      {cores.map((c) => (
        <circle
          key={`orbit-${c.team_id}`}
          cx={c.x}
          cy={c.y}
          r={c.orbitR}
          fill="none"
          stroke="var(--orbit)"
          strokeOpacity={0.22}
          strokeDasharray="2 5"
        />
      ))}

      {/* связи инженер → ядро */}
      {nodes.map((n) =>
        n.row.teams.map((t) => {
          const core = coreById.get(t)
          if (!core) return null
          return (
            <line
              key={`link-${n.row.engineer_id}-${t}`}
              x1={core.x}
              y1={core.y}
              x2={n.x}
              y2={n.y}
              stroke="var(--orbit)"
              strokeWidth={n.shared ? 1.4 : 0.8}
              strokeOpacity={dim(n.row.engineer_id) ? 0.08 : n.shared ? 0.75 : 0.3}
              strokeDasharray={n.shared ? '5 3' : undefined}
            />
          )
        }),
      )}

      {/* ядра-команды */}
      {cores.map((c) => (
        <g
          key={`core-${c.team_id}`}
          role="link"
          tabIndex={0}
          aria-label={`Показать команду ${c.team_id}`}
          onClick={() => openTeam(c.team_id)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              openTeam(c.team_id)
            }
          }}
          style={{ cursor: 'pointer', outline: 'none' }}
          className="core-link"
        >
          <title>{`Команда ${c.team_id}: показать состав`}</title>
          <circle cx={c.x} cy={c.y} r={CORE_R + 8} fill="var(--orbit)" opacity={0.08} />
          <circle cx={c.x} cy={c.y} r={CORE_R} fill="url(#sm-core)" stroke="var(--star)" strokeWidth={1.5} filter="url(#sm-glow)" />
          <text x={c.x} y={c.y - 2} textAnchor="middle" fontSize={13} fontWeight={700} fill="var(--star)" fontFamily="var(--font-heading)">
            {shortTeam(c.team_id)}
          </text>
          <text x={c.x} y={c.y + 12} textAnchor="middle" fontSize={10} fill="var(--orbit)" fontFamily="var(--font-mono)">
            {c.members} чел.
          </text>
        </g>
      ))}

      {/* инженеры */}
      {nodes.map((n) => {
        const absence = absenceById.get(n.row.engineer_id)
        const level = starLevel(n.row, absence)
        const r = gradeRadius(n.row.grade)
        const color = LEVEL_COLOR[level]
        const isSel = selectedId === n.row.engineer_id
        const showLabel = level !== 'ok' || hover === n.row.engineer_id || isSel || (highlight?.has(n.row.engineer_id) ?? false)
        const faded = dim(n.row.engineer_id)
        const label = `${n.row.engineer_id}, ${n.row.role_name}, ${n.row.grade}, ${n.row.teams.join(' и ')}, ${LEVEL_WORD[level]}`
        return (
          <g
            key={n.row.engineer_id}
            role="button"
            tabIndex={0}
            aria-label={label}
            aria-pressed={isSel}
            onClick={() => onSelect(n.row.engineer_id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onSelect(n.row.engineer_id)
              }
            }}
            onMouseEnter={() => setHover(n.row.engineer_id)}
            onMouseLeave={() => setHover(null)}
            onFocus={() => setHover(n.row.engineer_id)}
            onBlur={() => setHover(null)}
            style={{ cursor: 'pointer', outline: 'none' }}
            opacity={faded ? 0.22 : 1}
          >
            <title>{label}</title>
            {/* область попадания больше самой точки */}
            <circle cx={n.x} cy={n.y} r={r + 7} fill="transparent" />
            {(isSel || hover === n.row.engineer_id) && (
              <circle cx={n.x} cy={n.y} r={r + 5} fill="none" stroke="var(--star)" strokeWidth={1.5} />
            )}
            {level === 'critical' && (
              <circle cx={n.x} cy={n.y} r={r + 3.5} fill="none" stroke={color} strokeWidth={1.5} />
            )}
            {n.shared ? (
              // парттаймер на двух орбитах — ромб, а не круг
              <rect
                x={n.x - r * 0.9}
                y={n.y - r * 0.9}
                width={r * 1.8}
                height={r * 1.8}
                transform={`rotate(45 ${n.x} ${n.y})`}
                fill={color}
                stroke="var(--void)"
                strokeWidth={1.5}
              />
            ) : (
              <circle cx={n.x} cy={n.y} r={r} fill={color} stroke="var(--void)" strokeWidth={1.5} filter={level === 'ok' ? undefined : 'url(#sm-glow)'} />
            )}
            {showLabel && (
              <text
                x={n.x}
                y={n.y - r - 6}
                textAnchor="middle"
                fontSize={10.5}
                fontFamily="var(--font-mono)"
                fill="var(--star)"
                stroke="var(--void)"
                strokeWidth={3}
                paintOrder="stroke"
              >
                {n.row.engineer_id}
              </text>
            )}
          </g>
        )
      })}
    </svg>
    </div>
  )
}
