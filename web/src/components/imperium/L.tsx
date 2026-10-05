import { useLabel } from '../../theme/imperiumLabels'

/** Подпись, заменяемая словарём темы «Империум»; в других темах выводится как есть. */
export function L({ children }: { children: string }) {
  const label = useLabel()
  return <>{label(children)}</>
}
