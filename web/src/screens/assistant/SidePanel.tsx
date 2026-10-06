import { Badge, Group, Stack, Text } from '@mantine/core'
import { IconBook2, IconChartInfographic } from '@tabler/icons-react'
import type { Conversation, ProviderProfile } from '../../api/assistant'
import { RecommendationCard } from './AnswerCard'
import { useRecommendations } from './hooks'

/** «Детали чата»: контекст, модель и действующие рекомендации. Открывается кнопкой в шапке чата. */
export function SidePanel({ conv, profile }: { conv: Conversation; profile?: ProviderProfile }) {
  const recs = useRecommendations(conv.conversation_id)
  const items = recs.data?.recommendations ?? []
  const planning = conv.scope === 'planning'
  return (
    <div className="ai-side">
      <div className="ai-panel">
        <Text className="ai-label" mb={8}>Контекст</Text>
        <Group gap={8} mb={8}>
          {planning ? <IconChartInfographic size={18} /> : <IconBook2 size={18} />}
          <Text fw={700}>{planning ? 'Разбор прогона' : 'Как устроена система'}</Text>
        </Group>
        <Stack gap={4}>
          {planning && <Row k="PI" v={`${conv.pi_id ?? '—'} / ${conv.scenario_id ?? '—'}`} />}
          {planning && <Row k="Прогон" v={conv.run_id !== null ? `№${conv.run_id}` : '—'} />}
          <Row k="Версия контекста" v={String(conv.context_revision)} />
          <Row k="Модель" v={profile ? `${profile.name} · ${profile.model}` : 'отключена'} />
          <Row k="Данные" v={conv.privacy_mode === 'local_only' ? 'только локально' : 'внешний сервис'} />
        </Stack>
        {conv.newer_run_available && <Badge mt={8} color="yellow" variant="filled">Есть новый прогон</Badge>}
      </div>

      <div className="ai-panel">
        <Text className="ai-label" mb={8}>Рекомендации {items.length > 0 && <span className="mono">({items.length})</span>}</Text>
        {items.length === 0
          ? <Text size="sm" c="dimmed">Пока нет. Попросите помощника разобрать прогон или сравнить меры: советы появятся здесь с отметкой о свежести.</Text>
          : <Stack gap={8}>{items.map((r) => <RecommendationCard key={r.recommendation_id} item={r} />)}</Stack>}
      </div>

    </div>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <Group justify="space-between" gap={8} wrap="nowrap" className="ai-row">
      <Text size="sm" c="dimmed">{k}</Text>
      <Text size="sm" fw={600} className="mono" style={{ textAlign: 'right' }}>{v}</Text>
    </Group>
  )
}
