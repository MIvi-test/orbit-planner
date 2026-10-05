import { useMemo } from 'react'
import { Text, UnstyledButton } from '@mantine/core'
import { IconCornerDownRight, IconSparkles } from '@tabler/icons-react'
import { KNOWLEDGE_EXAMPLES, PLANNING_EXAMPLES } from './examples'
import { useTypewriter } from './useTypewriter'

/** Пустой чат: приветствие, «командная строка» с набором примеров и подсказки по выбранной теме чата. */
export function EmptyHero({ planning, disabled, onPick, intro = false }: { planning: boolean; disabled?: boolean; onPick: (q: string) => void; intro?: boolean }) {
  const examples = planning ? PLANNING_EXAMPLES : KNOWLEDGE_EXAMPLES
  const typed = useTypewriter(useMemo(() => examples, [examples]))
  return (
    <div className="ai-hero">
      <div className="ai-hero__orb" aria-hidden="true">
        <IconSparkles size={30} stroke={1.5} />
      </div>
      <Text className="ai-hero__title">Чем я могу помочь?</Text>
      {intro && (
        <Text c="dimmed" ta="center" maw={560}>
          {planning
            ? 'Разберу выбранный прогон: где риски, кого не хватает, что менять. Каждый ответ — со ссылками на данные.'
            : 'Объясню, как устроена система: правила, формулы, откуда берутся числа. Тему и модель можно поменять под полем ввода.'}
        </Text>
      )}
      <div className="ai-terminal" aria-live="off">
        <span className="ai-terminal__prompt">&gt;</span>
        <span className="ai-terminal__text">{typed}</span>
        <span className="ai-terminal__cursor" aria-hidden="true" />
      </div>
      <div className="ai-chips-row">
        {examples.map((q) => (
          <UnstyledButton key={q} className="ai-example ai-example--chip" disabled={disabled} onClick={() => onPick(q)}>
            <IconCornerDownRight size={15} stroke={1.8} />
            <span>{q}</span>
          </UnstyledButton>
        ))}
      </div>
    </div>
  )
}
