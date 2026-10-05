import { useEffect, useState } from 'react'

/**
 * Эффект набора текста в командной строке: печатает фразу, держит паузу, стирает и берёт следующую.
 * При `prefers-reduced-motion` анимации нет: показывается первая фраза целиком.
 */
export function useTypewriter(phrases: string[], active = true): string {
  const [text, setText] = useState('')
  useEffect(() => {
    if (!active || phrases.length === 0) return
    const reduce = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduce) {
      setText(phrases[0])
      return
    }
    let phrase = 0
    let pos = 0
    let deleting = false
    let timer = 0
    const tick = () => {
      const full = phrases[phrase]
      if (!deleting) {
        pos += 1
        setText(full.slice(0, pos))
        if (pos >= full.length) {
          deleting = true
          timer = window.setTimeout(tick, 1900)
          return
        }
        timer = window.setTimeout(tick, 34 + Math.random() * 38)
      } else {
        pos -= 1
        setText(full.slice(0, pos))
        if (pos <= 0) {
          deleting = false
          phrase = (phrase + 1) % phrases.length
          timer = window.setTimeout(tick, 420)
          return
        }
        timer = window.setTimeout(tick, 14)
      }
    }
    timer = window.setTimeout(tick, 500)
    return () => window.clearTimeout(timer)
  }, [phrases, active])
  return text
}
