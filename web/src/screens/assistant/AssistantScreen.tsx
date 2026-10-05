import { useEffect, useMemo, useState } from 'react'
import { ActionIcon, Alert, Button, Drawer, Group, Text, Title, Tooltip } from '@mantine/core'
import { useLocalStorage, useMediaQuery } from '@mantine/hooks'
import { IconLayoutSidebarRight, IconLayoutSidebarRightFilled, IconPencil, IconScale, IconSettings, IconTrash } from '@tabler/icons-react'
import { useQueryClient } from '@tanstack/react-query'
import { assistantApi, type Conversation, type ProviderProfile, type Scope } from '../../api/assistant'
import { selectedPiContext } from '../../api/client'
import { L } from '../../components/imperium/L'
import { useAuth } from '../../hooks/useAuth'
import { useHashQuery, type ScreenId } from '../../hooks/useHashRoute'
import { useRun } from '../../hooks/useRun'
import { notifications } from '../../utils/notify'
import { AI_KEYS, useConversation, useProfiles } from './hooks'
import { ChatList } from './ChatList'
import { ChatDialogs } from './ChatDialogs'
import { Composer, ModelPicker, ScopePicker, privacyFor } from './Composer'
import { ConversationView } from './Conversation'
import { EmptyHero } from './EmptyHero'
import { EvidenceDrawer } from './EvidenceDrawer'
import { ScenarioDrawer } from './ScenarioDrawer'
import { SettingsDrawer, type SettingsTab } from './SettingsDrawer'
import { SidePanel } from './SidePanel'
import './assistant.css'

type Go = (id: ScreenId, query?: Record<string, string>) => void
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e))

/**
 * ИИ-ассистент (в теме «Империум» — «Омниссия»). Слева история, по центру чат.
 * «Новый чат» сразу открывает пустой чат: тема и модель выбираются под полем ввода,
 * сам чат создаётся первым вопросом. Детали (контекст, рекомендации) — по кнопке справа.
 */
export function AssistantScreen({ onNavigate }: { onNavigate: Go }) {
  const qc = useQueryClient()
  const { can } = useAuth()
  const { runId, runs, setRunId } = useRun()
  const chatParam = useHashQuery().get('chat')
  const [activeId, setActiveId] = useState<string | null>(chatParam)
  const [settingsTab, setSettingsTab] = useState<SettingsTab | null>(null)
  const [scenarioOpen, setScenarioOpen] = useState(false)
  const [details, setDetails] = useLocalStorage({ key: 'pi-ai-details', defaultValue: false })
  const wide = useMediaQuery('(min-width: 1500px)')
  const [evidenceId, setEvidenceId] = useState<string | null>(null)
  const [auto, setAuto] = useState<{ id: string; text: string } | null>(null)
  const [renameTarget, setRenameTarget] = useState<Conversation | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null)
  // Новый (ещё не созданный) чат: тема и модель, запомненная с прошлого раза.
  const [draftScope, setDraftScope] = useState<Scope>('knowledge')
  const [lastModel, setLastModel] = useLocalStorage<number | null>({ key: 'pi-ai-model', defaultValue: null })
  const [creating, setCreating] = useState(false)
  const profiles = useProfiles()
  const list = profiles.data?.profiles ?? []
  const conv = useConversation(activeId)
  const run = runs.find((r) => r.run_id === runId)

  useEffect(() => { setActiveId(chatParam) }, [chatParam])
  useEffect(() => { if (draftScope === 'planning' && !run) setDraftScope('knowledge') }, [run, draftScope])

  const draftModel = list.find((p) => p.profile_id === lastModel) ?? list[0] ?? null
  const profile = useMemo(() => list.find((p) => p.profile_id === conv.data?.provider_profile_id), [list, conv.data])
  const planning = conv.data?.scope === 'planning'

  const open = (id: string | null) => {
    setActiveId(id)
    onNavigate('assistant', id ? { chat: id } : undefined)
  }
  const refreshChat = async (id: string) => {
    await qc.invalidateQueries({ queryKey: AI_KEYS.conv(id) })
    await qc.invalidateQueries({ queryKey: AI_KEYS.list })
  }

  // Первый вопрос нового чата: создаём чат с выбранной темой и моделью и сразу отправляем вопрос.
  const startWith = async (q: string) => {
    if (!draftModel) { setSettingsTab('models'); return }
    setCreating(true)
    try {
      const base = { scope: draftScope, provider_profile_id: draftModel.profile_id, privacy_mode: privacyFor(draftModel) }
      const created = await assistantApi.createConversation(draftScope === 'planning' && run
        ? { ...base, pi_id: run.pi_id, scenario_id: selectedPiContext()?.scenario_id ?? 'main', run_id: run.run_id }
        : base)
      await qc.invalidateQueries({ queryKey: AI_KEYS.list })
      setAuto({ id: created.conversation_id, text: q })
      open(created.conversation_id)
    } catch (e) {
      notifications.show({ color: 'red', title: 'Не удалось начать чат', message: errText(e) })
    } finally {
      setCreating(false)
    }
  }

  const changeModel = async (c: Conversation, p: ProviderProfile) => {
    try {
      await assistantApi.settings(c.conversation_id, { provider_profile_id: p.profile_id, privacy_mode: privacyFor(p) })
      setLastModel(p.profile_id)
      await refreshChat(c.conversation_id)
    } catch (e) {
      notifications.show({ color: 'red', title: 'Модель не изменена', message: errText(e) })
    }
  }

  const attachRun = async (c: Conversation) => {
    if (!run) return
    try {
      await assistantApi.bindContext(c.conversation_id, { pi_id: run.pi_id, scenario_id: selectedPiContext()?.scenario_id ?? 'main', run_id: run.run_id, expected_context_revision: c.context_revision })
      setRunId(run.run_id)
      await refreshChat(c.conversation_id)
    } catch (e) {
      notifications.show({ color: 'red', title: 'Прогон не подключён', message: errText(e) })
    }
  }

  const noModels = !profiles.isPending && list.length === 0
  const noModelsAlert = noModels && (
    <Alert color="yellow" mx="md" mb="sm" title="Нет доступных моделей">
      <Group justify="space-between" wrap="nowrap">
        <Text size="sm">{can('admin') ? 'Добавьте модель, чтобы ассистент мог отвечать.' : 'Попросите администратора добавить модель.'}</Text>
        {can('admin') && <Button size="compact-sm" onClick={() => setSettingsTab('models')}>Добавить модель</Button>}
      </Group>
    </Alert>
  )

  const side = conv.data ? <SidePanel conv={conv.data} profile={profile} /> : null
  const showSide = Boolean(side && details && wide)

  return (
    <div className="ai-screen">
      <Group justify="space-between" align="flex-end" wrap="nowrap" mb="md">
        <div style={{ minWidth: 0, flex: 1 }}>
          <Title order={2}><L>ИИ-ассистент</L></Title>
          <Text c="dimmed" mt={2}>Объясняет правила, разбирает прогон и сравнивает кадровые меры со ссылками на данные.</Text>
        </div>
        <Button variant="default" leftSection={<IconSettings size={17} />} onClick={() => setSettingsTab('models')}>Настройки</Button>
      </Group>

      <div className="ai-layout" data-side={showSide ? 'on' : 'off'}>
        <ChatList activeId={activeId} onSelect={(c) => open(c.conversation_id)} onNew={() => open(null)} onRename={setRenameTarget} onDelete={setDeleteTarget} />
        <div className="ai-panel ai-main">
          {activeId === null ? (
            <div className="ai-chat">
              <div className="ai-chat-head"><Text fw={700} style={{ flex: 1 }}>Новый чат</Text></div>
              {noModelsAlert}
              <div className="ai-thread" data-empty="true">
                <EmptyHero intro planning={draftScope === 'planning'} disabled={creating || noModels} onPick={(q) => void startWith(q)} />
              </div>
              <Composer busy={creating} disabled={noModels} onSend={(t) => void startWith(t)}
                placeholder={draftScope === 'planning' ? 'Спросите про выбранный прогон…' : 'Спросите, как устроена система…'}
                toolbar={<>
                  <ScopePicker scope={draftScope} runId={run?.run_id ?? null} latestRun={run?.run_id ?? null} onChange={setDraftScope} />
                  <ModelPicker profiles={list} value={draftModel?.profile_id ?? null} onChange={(p) => setLastModel(p.profile_id)} />
                </>} />
            </div>
          ) : conv.isPending ? (
            <Text c="dimmed" p="md">Загрузка чата…</Text>
          ) : conv.isError ? (
            <Alert color="red" m="md" title="Чат недоступен">{conv.error.message}</Alert>
          ) : (
            <>
              <div className="ai-chat-head">
                <Text fw={700} lineClamp={1} style={{ flex: 1, minWidth: 0 }}>{conv.data.title || 'Новый чат'}</Text>
                {planning && can('planner') && <Button size="compact-sm" variant="light" leftSection={<IconScale size={15} />} onClick={() => setScenarioOpen(true)}>Сравнить меры</Button>}
                <Tooltip label="Переименовать"><ActionIcon variant="subtle" color="gray" onClick={() => setRenameTarget(conv.data)} aria-label="Переименовать"><IconPencil size={17} /></ActionIcon></Tooltip>
                <Tooltip label="Удалить чат"><ActionIcon variant="subtle" color="red" onClick={() => setDeleteTarget(conv.data)} aria-label="Удалить чат"><IconTrash size={17} /></ActionIcon></Tooltip>
                <Tooltip label={details ? 'Скрыть детали' : 'Детали: контекст и рекомендации'}>
                  <ActionIcon variant={details ? 'light' : 'subtle'} color={details ? undefined : 'gray'} onClick={() => setDetails(!details)} aria-label="Детали чата">
                    {details ? <IconLayoutSidebarRightFilled size={17} /> : <IconLayoutSidebarRight size={17} />}
                  </ActionIcon>
                </Tooltip>
              </div>
              {noModelsAlert}
              <ConversationView conv={conv.data} onEvidence={setEvidenceId} onNavigate={onNavigate}
                autoSend={auto?.id === conv.data.conversation_id ? auto.text : null} onAutoSent={() => setAuto(null)}
                toolbar={<>
                  <ScopePicker locked scope={conv.data.scope} runId={conv.data.run_id} latestRun={run?.run_id ?? null} onChange={(s) => { if (s === 'planning') void attachRun(conv.data) }} />
                  <ModelPicker profiles={list} value={conv.data.provider_profile_id} current={conv.data.privacy_mode} onChange={(p) => void changeModel(conv.data, p)} />
                </>} />
            </>
          )}
        </div>
        {showSide && <div className="ai-side-col">{side}</div>}
      </div>

      <Drawer opened={Boolean(side && details && !wide)} onClose={() => setDetails(false)} position="right" size="md" title="Детали чата">{side}</Drawer>
      <SettingsDrawer tab={settingsTab} onTab={setSettingsTab} onClose={() => setSettingsTab(null)} />
      {conv.data && <ScenarioDrawer conv={conv.data} opened={scenarioOpen} onClose={() => setScenarioOpen(false)} onEvidence={setEvidenceId} onNavigate={onNavigate} />}
      <EvidenceDrawer evidenceId={evidenceId} onClose={() => setEvidenceId(null)} />
      <ChatDialogs renameTarget={renameTarget} deleteTarget={deleteTarget}
        onClose={() => { setRenameTarget(null); setDeleteTarget(null) }}
        onDeleted={(id) => { if (id === activeId) open(null) }} />
    </div>
  )
}
