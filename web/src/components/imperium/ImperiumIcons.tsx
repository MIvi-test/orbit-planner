import type { SVGProps } from 'react'

/** Единый набор иконок темы «Империум»: цвет — currentColor, размер — size. */
type P = { size?: number } & Omit<SVGProps<SVGSVGElement>, 'width' | 'height'>

function Svg({ size = 22, children, ...rest }: P & { children: React.ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="currentColor" aria-hidden="true" {...rest}>
      {children}
    </svg>
  )
}

/** Двуглавая аквила (собственный рисунок). */
export const Aquila = (p: P) => (
  <Svg {...p}>
    <path d="M16 6l-2 3-4-2 1 4-6-2 4 5-5 1 6 3-3 3 6-1-1 4 3-2 3 2-1-4 6 1-3-3 6-3-5-1 4-5-6 2 1-4-4 2z" />
    <circle cx="11" cy="8" r="2" />
    <circle cx="21" cy="8" r="2" />
    <path d="M14 20h4v6l-2 2-2-2z" />
  </Svg>
)
export const Gear = (p: P) => (
  <Svg {...p}>
    <path d="M14 3h4l1 3 3 1 3-2 3 3-2 3 1 3 3 1v4l-3 1-1 3 2 3-3 3-3-2-3 1-1 3h-4l-1-3-3-1-3 2-3-3 2-3-1-3-3-1v-4l3-1 1-3-2-3 3-3 3 2 3-1z M16 11a5 5 0 100 10 5 5 0 000-10z" fillRule="evenodd" />
  </Svg>
)
export const Skull = (p: P) => (
  <Svg {...p}>
    <path d="M16 3C9.9 3 6 7 6 12.5c0 3.2 1.4 5.2 3.5 6.5V25h3v-2h1.5v2h4v-2H19v2h3.5v-6c2.1-1.300 3.500-3.300 3.500-6.500C26 7 22.100 3 16 3zM11.500 11a2.500 2.500 0 110 5 2.500 2.500 0 010-5zm9 0a2.500 2.500 0 110 5 2.500 2.500 0 010-5zM16 17l1.500 3h-3z" fillRule="evenodd" />
  </Svg>
)
export const Sword = (p: P) => (
  <Svg {...p}>
    <path d="M15 2h2v18h-2zM10 20h12v2H10zM14 22h4v7h-4z" />
  </Svg>
)
export const Shield = (p: P) => (
  <Svg {...p}>
    <path d="M16 3l11 4v8c0 7-5 11-11 14C10 26 5 22 5 15V7z" />
  </Svg>
)
export const Scroll = (p: P) => (
  <Svg {...p}>
    <path d="M8 4h14a3 3 0 013 3v17a4 4 0 01-4 4H9a3 3 0 01-3-3V8a4 4 0 012-4zm3 6v2h10v-2zm0 5v2h10v-2zm0 5v2h6v-2z" fillRule="evenodd" />
  </Svg>
)
export const Helmet = (p: P) => (
  <Svg {...p}>
    <path d="M16 4c6 0 10 4 10 10v10h-5v-5h-10v5H6V14C6 8 10 4 16 4zm-5 9v3h10v-3z" fillRule="evenodd" />
  </Svg>
)
export const Star = (p: P) => (
  <Svg {...p}>
    <path d="M16 3l3.500 8 8.500.8-6.400 5.700 1.900 8.500L16 21.500 8.500 26l1.900-8.500L4 11.800 12.500 11z" />
  </Svg>
)
