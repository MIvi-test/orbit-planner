import { Badge, Button, Group, Stack, Text, UnstyledButton } from '@mantine/core'
import { IconAlertTriangle, IconCircleCheck, IconFileText, IconHelpCircle, IconLink, IconShieldCheck } from '@tabler/icons-react'
import type { Answer, Recommendation } from '../../api/assistant'
import type { ScreenId } from '../../hooks/useHashRoute'
import { Markdown } from './Markdown'

const STATUS: Record<Answer['status'], { label: string; color: string; icon: typeof IconCircleCheck }> = {
  answered: { label: 'Ответ', color: 'teal', icon: IconCircleCheck },
  needs_clarification: { label: 'Нужно уточнение', color: 'yellow', icon: IconHelpCircle },
  insufficient_data: { label: 'Недостаточно данных', color: 'orange', icon: IconAlertTriangle },
}

const BASIS: Record<Recommendation['basis_status'], { label: string; color: string }> = {
  verified_by_scenario: { label: 'Проверено расчётом', color: 'teal' },
  proposal: { label: 'Предложение', color: 'blue' },
  needs_data: { label: 'Нужны данные', color: 'orange' },
}

const FRESH: Record<Recommendation['freshness'], { label: string; color: string }> = {
  current: { label: 'Актуально', color: 'teal' },
  stale: { label: 'Устарело', color: 'yellow' },
  superseded: { label: 'Заменено', color: 'gray' },
}

/** Куда ведёт ссылка на сущность. URL не приходит с сервера: собирается здесь из типа и идентификатора. */
function targetOf(type: string, id: string): { screen: ScreenId; query?: Record<string, string>; label: string } | null {
  switch (type) {
    case 'team': return { screen: 'profiles', query: { team: id }, label: `Команда ${id}` }
    case 'engineer': return { screen: 'starmap', label: `Инженер ${id}` }
    case 'task': return { screen: 'plan', label: `Задача ${id}` }
    case 'initiative': return { screen: 'plan', label: `Инициатива ${id}` }
    case 'role': return { screen: 'roles', label: `Роль ${id}` }
    case 'metric':
    case 'kpi': return { screen: 'kpi', label: `KPI ${id}` }
    default: return null
  }
}

export function RecommendationCard({ item }: { item: Recommendation }) {
  const basis = BASIS[item.basis_status]
  const fresh = FRESH[item.freshness]
  return (
    <div className="ai-rec" data-fresh={item.freshness}>
      <Group gap={6} mb={6} wrap="wrap">
        <Badge color={basis.color} variant="light" leftSection={item.basis_status === 'verified_by_scenario' ? <IconShieldCheck size={13} /> : undefined}>
          {basis.label}
        </Badge>
        <Badge color={fresh.color} variant="outline">{fresh.label}</Badge>
      </Group>
      <Text size="sm">{item.text}</Text>
      {item.stale_reasons && item.stale_reasons.length > 0 && (
        <Text size="xs" c="dimmed" mt={4}>Почему устарело: {item.stale_reasons.join('; ')}</Text>
      )}
    </div>
  )
}

/** Сырые ссылки модели «[evidence:<uuid>]» и «[kb:…]» → «доказательство N» / «документ»: сами основания открываются кнопками ниже. */
function humanize(text: string, evidenceIds: string[]): string {
  return text
    .replace(/\[?evidence:([0-9a-f-]{8,})\]?/gi, (_m, id: string) => {
      const n = evidenceIds.indexOf(id)
      return n >= 0 ? `доказательство ${n + 1}` : 'сохранённое основание'
    })
    .replace(/\[entity:([^\]]+)\]/g, (_m, id: string) => id.replace(/[\\`*_{}\[\]()<>#!|]/g, '\\$&'))
    .replace(/\[?kb:[^\]\s]+\]?/gi, 'документ')
}

/** Ответ помощника: вывод, объяснение, рекомендации, уточнение, источники и доказательства. */
export function AnswerCard({
  answer,
  onEvidence,
  onNavigate,
}: {
  answer: Answer
  onEvidence: (id: string) => void
  onNavigate: (screen: ScreenId, query?: Record<string, string>) => void
}) {
  const st = STATUS[answer.status]
  const Icon = st.icon
  const refs = answer.entity_refs.map((r) => ({ ref: r, target: targetOf(r.type, r.id) })).filter((r) => r.target)
  return (
    <Stack gap="sm">
      <Group gap={8}>
        <Badge color={st.color} variant="light" size="lg" leftSection={<Icon size={14} />}>{st.label}</Badge>
        {answer.degraded && <Badge color="orange" variant="outline">Упрощённый режим</Badge>}
      </Group>
      {answer.summary && <Text className="ai-answer__summary">{humanize(answer.summary, answer.evidence_ids)}</Text>}
      {answer.explanation && <Markdown>{humanize(answer.explanation, answer.evidence_ids)}</Markdown>}
      {answer.triage && <Stack gap="sm">
        {answer.triage.issues.map((issue) => <div key={issue.issue_id} className="ai-panel">
          <Text fw={700}>{issue.rank}. {issue.entity_id} — {issue.priority_reason}</Text>
          <Text size="sm">Потенциально затронуто задач: {issue.affected_count}.</Text>
          <Text size="sm">Первый шаг: {issue.first_step}</Text>
          {issue.affected_task_ids.length > 0 && <Text size="sm">Задачи: {issue.affected_task_ids.join(', ')}</Text>}
          {issue.source_alerts.map((alert, index) => <Text size="sm" key={index}>{alert.message}</Text>)}
          {issue.details_limited && <Text size="sm" c="dimmed">Подробности сокращены; полный список сохранён в основаниях.</Text>}
        </div>)}
        <Text size="sm" c="dimmed">Можно спросить «подробнее о первой»{answer.triage.next_offset < answer.triage.total ? ' или «следующие проблемы»' : ''}.</Text>
      </Stack>}
      {answer.clarification && answer.clarification.trim() !== answer.summary.trim() && (
        <div className="ai-clarify">
          <IconHelpCircle size={18} />
          <Text size="sm">{humanize(answer.clarification, answer.evidence_ids)}</Text>
        </div>
      )}
      {answer.recommendations.length > 0 && (
        <Stack gap={8}>
          <Text className="ai-label">Что делать</Text>
          {answer.recommendations.map((r) => <RecommendationCard key={r.recommendation_id} item={r} />)}
        </Stack>
      )}
      {refs.length > 0 && (
        <Group gap={6} wrap="wrap">
          {refs.map(({ ref, target }) => (
            <Button key={`${ref.type}-${ref.id}`} size="compact-sm" variant="light" leftSection={<IconLink size={14} />}
              onClick={() => onNavigate(target!.screen, target!.query)}>
              {target!.label}
            </Button>
          ))}
        </Group>
      )}
      {answer.limitations.length > 0 && (
        <details className="ai-limits">
          <summary className="ai-label">Ограничения ({answer.limitations.length})</summary>
          {answer.limitations.map((l, i) => <Text key={i} size="sm" c="dimmed">• {l}</Text>)}
        </details>
      )}
      {answer.diagnostics && <details className="ai-limits">
        <summary className="ai-label">Диагностика администратора</summary>
        <Text size="sm">Задание: {answer.diagnostics.job_id}</Text>
        {answer.diagnostics.reasons.map((reason) => <Text size="sm" key={reason}>{reason}</Text>)}
      </details>}
      {(answer.evidence_ids.length > 0 || (answer.sources?.length ?? 0) > 0) && (
        <div className="ai-sources">
          <Text className="ai-label">Источники</Text>
          <Group gap={6} wrap="wrap">
            {answer.evidence_ids.map((id, i) => (
              <UnstyledButton key={id} className="ai-chip" onClick={() => onEvidence(id)} title="Открыть доказательство">
                <IconFileText size={13} /> Доказательство {i + 1}
              </UnstyledButton>
            ))}
            {answer.sources?.map((s) => (
              <span key={s.chunk_id} className="ai-chip ai-chip--static" title={`${s.path}, версия ${s.version}`}>
                {s.heading || s.path}
              </span>
            ))}
          </Group>
        </div>
      )}
    </Stack>
  )
}
