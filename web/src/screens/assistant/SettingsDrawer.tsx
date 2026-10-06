import { useEffect, useState } from 'react'
import { Accordion, ActionIcon, Alert, Badge, Button, Drawer, Group, Menu, Modal, NativeSelect, Stack, Switch, Table, Tabs, Text, TextInput, Textarea } from '@mantine/core'
import { IconDots, IconPencil, IconPlugConnected, IconPlus, IconTrash } from '@tabler/icons-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { assistantApi, type ProviderProfile, type ProviderProfileInput } from '../../api/assistant'
import { L } from '../../components/imperium/L'
import { useAuth } from '../../hooks/useAuth'
import { notifications } from '../../utils/notify'
import { AI_KEYS, useKbStatus, useProfiles } from './hooks'

export type SettingsTab = 'models' | 'prompt' | 'project'

const PRESETS: Record<string, Partial<ProviderProfileInput>> = {
  Groq: { name: 'Groq', protocol: 'openai_compatible', base_url: 'https://api.groq.com/openai/v1', model: 'openai/gpt-oss-20b', api_key_ref: 'env:GROQ_API_KEY' },
  OpenAI: { name: 'OpenAI', protocol: 'openai_compatible', base_url: 'https://api.openai.com/v1', model: 'gpt-4o-mini', api_key_ref: 'env:OPENAI_API_KEY' },
  Gemini: { name: 'Gemini', protocol: 'gemini', base_url: 'https://generativelanguage.googleapis.com/v1beta', model: 'gemini-3.5-flash-lite', auth_type: 'header', auth_header_name: 'x-goog-api-key', api_key_ref: 'env:GEMINI_API_KEY' },
  'Ollama (локально)': { name: 'Ollama', protocol: 'ollama', base_url: 'http://ollama:11434', model: 'qwen3.5:9b', auth_type: 'none', api_key_ref: '', network_scope: 'internal' },
}
const replacementModel = (p: ProviderProfile) =>
  p.protocol === 'gemini' && p.model === 'gemini-2.0-flash' ? 'gemini-3.5-flash-lite'
    : p.base_url === 'https://api.groq.com/openai/v1' && p.model === 'llama-3.3-70b-versatile' ? 'openai/gpt-oss-20b' : null
const EMPTY: ProviderProfileInput = { name: '', protocol: 'openai_compatible', base_url: '', model: '', auth_type: 'bearer', api_key_ref: '', network_scope: 'external' }
const errText = (e: unknown) => (e instanceof Error ? e.message : String(e))

/** Настройки ассистента: модели (список, добавление, правка, удаление), личные инструкции, проект и база знаний. */
export function SettingsDrawer({ tab, onTab, onClose }: { tab: SettingsTab | null; onTab: (t: SettingsTab) => void; onClose: () => void }) {
  const { can } = useAuth()
  const admin = can('admin')
  return (
    <Drawer opened={tab !== null} onClose={onClose} position="right" size="xl" title={<L>Настройки ассистента</L>}>
      <Tabs value={tab ?? 'models'} onChange={(v) => v && onTab(v as SettingsTab)} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="models">Модели</Tabs.Tab>
          <Tabs.Tab value="prompt">Мои инструкции</Tabs.Tab>
          {admin && <Tabs.Tab value="project">Проект и база знаний</Tabs.Tab>}
        </Tabs.List>
        <Tabs.Panel value="models"><ModelsPanel admin={admin} /></Tabs.Panel>
        <Tabs.Panel value="prompt"><MyPromptPanel /></Tabs.Panel>
        {admin && <Tabs.Panel value="project"><ProjectPanel /></Tabs.Panel>}
      </Tabs>
    </Drawer>
  )
}

function ModelsPanel({ admin }: { admin: boolean }) {
  const qc = useQueryClient()
  const profiles = useProfiles()
  const list = profiles.data?.profiles ?? []
  const [editing, setEditing] = useState<ProviderProfile | 'new' | null>(null)
  const [removing, setRemoving] = useState<ProviderProfile | null>(null)
  const reload = () => qc.invalidateQueries({ queryKey: AI_KEYS.profiles })

  const check = async (p: ProviderProfile) => {
    try {
      const r = await assistantApi.checkProfile(p.profile_id)
      const ok = Boolean(r.reachable)
      notifications.show({ color: ok ? 'teal' : 'red', title: ok ? `«${p.name}» отвечает` : `«${p.name}» не отвечает`, message: ok ? 'Модель доступна для чатов.' : String(r.error ?? 'Проверьте адрес и ключ.') })
    } catch (e) {
      notifications.show({ color: 'red', title: 'Проверка не удалась', message: errText(e) })
    }
  }

  const upgrade = async (p: ProviderProfile) => {
    const model = replacementModel(p)
    if (!model) return
    try {
      const updated = await assistantApi.updateProfile(p.profile_id, {
        name: p.name, protocol: p.protocol as ProviderProfileInput['protocol'], base_url: p.base_url,
        model, auth_type: p.auth_type as ProviderProfileInput['auth_type'], network_scope: p.network_scope,
      })
      await reload()
      await check(updated)
    } catch (e) {
      notifications.show({ color: 'red', title: 'Не удалось обновить модель', message: errText(e) })
    }
  }

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Text size="sm" c="dimmed" style={{ flex: 1 }}>Модель для конкретного чата выбирается под полем ввода. Здесь — список доступных моделей.</Text>
        {admin && <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing('new')}>Добавить модель</Button>}
      </Group>
      <Stack gap={8}>
        {list.map((p) => (
          <div key={p.profile_id} className="ai-panel ai-model-row">
            <div style={{ flex: 1, minWidth: 0 }}>
              <Group gap={8}>
                <Text fw={700}>{p.name}</Text>
                <Badge size="sm" variant="light" color={p.network_scope === 'internal' ? 'teal' : 'blue'}>{p.network_scope === 'internal' ? 'Локальная' : 'Внешний сервис'}</Badge>
                {!p.credential_configured && <Badge size="sm" variant="outline" color="red">Ключ не найден</Badge>}
                {replacementModel(p) && <Badge size="sm" variant="outline" color="orange">Модель устарела</Badge>}
                {p.capabilities?.thinking === false && <Badge size="sm" variant="light" color="grape">Быстрый режим</Badge>}
              </Group>
              <Text size="sm" c="dimmed" className="mono" truncate>{p.model} · {p.base_url}</Text>
            </div>
            {admin && (
              <Group gap={4} wrap="nowrap">
                {replacementModel(p) && <Button size="compact-sm" variant="light" color="orange" onClick={() => void upgrade(p)}>Обновить модель</Button>}
                <Button size="compact-sm" variant="light" leftSection={<IconPlugConnected size={14} />} onClick={() => void check(p)}>Проверить</Button>
                <Menu position="bottom-end" withinPortal>
                  <Menu.Target><ActionIcon variant="subtle" color="gray" aria-label="Действия с моделью"><IconDots size={17} /></ActionIcon></Menu.Target>
                  <Menu.Dropdown>
                    <Menu.Item leftSection={<IconPencil size={15} />} onClick={() => setEditing(p)}>Изменить</Menu.Item>
                    <Menu.Item color="red" leftSection={<IconTrash size={15} />} onClick={() => setRemoving(p)}>Удалить</Menu.Item>
                  </Menu.Dropdown>
                </Menu>
              </Group>
            )}
          </div>
        ))}
        {list.length === 0 && <Text c="dimmed" size="sm">{profiles.isPending ? 'Загрузка…' : 'Моделей пока нет.'}</Text>}
      </Stack>
      {!admin && <Text size="sm" c="dimmed">Добавлять и менять модели может администратор.</Text>}
      <KeyHelp />
      <ProfileModal target={editing} onClose={() => setEditing(null)} onSaved={reload} />
      <Modal opened={removing !== null} onClose={() => setRemoving(null)} title="Удалить модель?" centered>
        <Text size="sm">Модель «{removing?.name}» пропадёт из списка. Прошлые ответы сохранятся, а чатам на этой модели нужно будет выбрать другую под полем ввода.</Text>
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={() => setRemoving(null)}>Отмена</Button>
          <Button color="red" onClick={() => { const p = removing; setRemoving(null); if (p) void assistantApi.deleteProfile(p.profile_id).then(reload).catch((e) => notifications.show({ color: 'red', title: 'Не удалось удалить', message: errText(e) })) }}>Удалить</Button>
        </Group>
      </Modal>
    </Stack>
  )
}

function KeyHelp() {
  return (
    <Accordion variant="contained" radius="md">
      <Accordion.Item value="key">
        <Accordion.Control>Как подключить свой ключ API</Accordion.Control>
        <Accordion.Panel>
          <Stack gap={6}>
            <Text size="sm">Ключ не вводится в интерфейсе и не хранится в базе — сервер читает его из окружения.</Text>
            <Text size="sm">1. Впишите ключ в файл <code>.env</code> рядом с <code>docker-compose.yaml</code>: <code>GROQ_API_KEY=ваш_ключ</code>.</Text>
            <Text size="sm">2. Пересоздайте приложение и обработчик: <code>docker compose up -d --force-recreate app assistant-worker</code>.</Text>
            <Text size="sm">3. Добавьте модель (или выберите шаблон) и укажите ссылку на ключ <code>env:GROQ_API_KEY</code>. Нажмите «Проверить».</Text>
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  )
}

function ProfileModal({ target, onClose, onSaved }: { target: ProviderProfile | 'new' | null; onClose: () => void; onSaved: () => void }) {
  const isNew = target === 'new'
  const [form, setForm] = useState<ProviderProfileInput>(EMPTY)
  const [more, setMore] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    setError(null)
    setMore(false)
    if (target === 'new') setForm(EMPTY)
    else if (target) setForm({ name: target.name, protocol: target.protocol as ProviderProfileInput['protocol'], base_url: target.base_url, model: target.model, auth_type: target.auth_type as ProviderProfileInput['auth_type'], network_scope: target.network_scope, api_key_ref: '', auth_header_name: '', capabilities: target.capabilities?.thinking === false ? { thinking: false } : {} })
  }, [target])
  const set = (patch: Partial<ProviderProfileInput>) => setForm((f) => ({ ...f, ...patch }))

  const save = async () => {
    if (!target) return
    setBusy(true)
    setError(null)
    // Пустые ссылка на ключ и заголовок при правке — значит «оставить прежние».
    const body: ProviderProfileInput = { ...form }
    if (form.auth_type === 'none') { body.api_key_ref = null; delete body.auth_header_name }
    else {
      if (!form.api_key_ref) { if (isNew) body.api_key_ref = null; else delete body.api_key_ref }
      if (form.auth_type !== 'header' || !form.auth_header_name) delete body.auth_header_name
    }
    try {
      if (isNew) await assistantApi.createProfile(body)
      else await assistantApi.updateProfile(target.profile_id, body)
      onSaved()
      onClose()
      notifications.show({ color: 'teal', title: isNew ? 'Модель добавлена' : 'Модель обновлена', message: 'Нажмите «Проверить», чтобы убедиться, что провайдер отвечает.' })
    } catch (e) {
      setError(errText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal opened={target !== null} onClose={onClose} title={isNew ? 'Новая модель' : `Изменить «${(target as ProviderProfile | null)?.name ?? ''}»`} size="lg" centered>
      <Stack gap="sm">
        {isNew && (
          <NativeSelect label="Шаблон" value="" onChange={(e) => { const v = PRESETS[e.currentTarget.value]; if (v) setForm({ ...EMPTY, ...v }) }}
            data={[{ value: '', label: 'Выберите провайдера — поля заполнятся сами' }, ...Object.keys(PRESETS)]} />
        )}
        <Group grow>
          <TextInput label="Название" description={isNew ? 'Видно в выборе модели' : 'Название не меняется'} value={form.name} disabled={!isNew} onChange={(e) => set({ name: e.currentTarget.value })} />
          <TextInput label="Модель" description="Идентификатор у провайдера" value={form.model} onChange={(e) => set({ model: e.currentTarget.value })} />
        </Group>
        {form.auth_type !== 'none' && (
          <TextInput label="Ссылка на ключ" placeholder={isNew ? 'env:GROQ_API_KEY' : 'Оставьте пустым, чтобы не менять'}
            description="env:ИМЯ_ПЕРЕМЕННОЙ или file:/путь — сам ключ сюда не вводится"
            value={form.api_key_ref ?? ''} onChange={(e) => set({ api_key_ref: e.currentTarget.value })} />
        )}
        <Switch checked={form.capabilities?.thinking === false} onChange={(e) => set({ capabilities: e.currentTarget.checked ? { thinking: false } : {} })}
          label="Быстрые ответы без размышлений"
          description="Для Gemini 3 выбирает минимальный уровень рассуждения; у других поддерживаемых моделей отключает его. Доступность режима зависит от модели." />
        <Button variant="subtle" size="compact-sm" onClick={() => setMore((m) => !m)} style={{ alignSelf: 'flex-start' }}>{more ? 'Скрыть подключение' : 'Адрес, протокол, сеть'}</Button>
        {more && (
          <Stack gap="sm">
            <TextInput label="Адрес API" placeholder="https://api.groq.com/openai/v1" value={form.base_url} onChange={(e) => set({ base_url: e.currentTarget.value })} />
            <Group grow>
              <NativeSelect label="Протокол" value={form.protocol} onChange={(e) => set({ protocol: e.currentTarget.value as ProviderProfileInput['protocol'] })} data={[{ value: 'openai_compatible', label: 'OpenAI-совместимый' }, { value: 'gemini', label: 'Gemini' }, { value: 'ollama', label: 'Ollama' }]} />
              <NativeSelect label="Авторизация" value={form.auth_type} onChange={(e) => set({ auth_type: e.currentTarget.value as ProviderProfileInput['auth_type'] })} data={[{ value: 'bearer', label: 'Bearer-токен' }, { value: 'header', label: 'Свой заголовок' }, { value: 'none', label: 'Без ключа' }]} />
              <NativeSelect label="Сеть" value={form.network_scope} onChange={(e) => set({ network_scope: e.currentTarget.value as ProviderProfileInput['network_scope'] })} data={[{ value: 'external', label: 'Внешний сервис' }, { value: 'internal', label: 'Локальная' }]} />
            </Group>
            {form.auth_type === 'header' && <TextInput label="Имя заголовка" placeholder={isNew ? 'x-goog-api-key' : 'Оставьте пустым, чтобы не менять'} value={form.auth_header_name ?? ''} onChange={(e) => set({ auth_header_name: e.currentTarget.value })} />}
          </Stack>
        )}
        {!more && !form.base_url && <Text size="xs" c="dimmed">Выберите шаблон или раскройте «Адрес, протокол, сеть».</Text>}
        {error && <Alert color="red">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Отмена</Button>
          <Button loading={busy} disabled={!form.name || !form.model || !form.base_url} onClick={() => void save()}>{isNew ? 'Добавить' : 'Сохранить'}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function MyPromptPanel() {
  const qc = useQueryClient()
  const my = useQuery({ queryKey: AI_KEYS.myPrompt, queryFn: assistantApi.myPrompt, retry: false })
  const [text, setText] = useState('')
  useEffect(() => { if (my.data) setText(my.data.content) }, [my.data])
  return (
    <Stack gap="sm">
      <Text size="sm" c="dimmed">Ваши инструкции для всех чатов: стиль ответов, язык, на чём делать упор. Они дополняют правила проекта и не отменяют их.</Text>
      <Textarea autosize minRows={6} maxRows={16} value={text} onChange={(e) => setText(e.currentTarget.value)} maxLength={12000} placeholder="Например: отвечай коротко, сначала вывод, потом детали." />
      <Group justify="space-between">
        <Text size="xs" c="dimmed">{text.length}/12000</Text>
        <Button disabled={!text.trim()} onClick={() => void assistantApi.saveMyPrompt(text).then(() => qc.invalidateQueries({ queryKey: AI_KEYS.myPrompt })).then(() => notifications.show({ color: 'teal', title: 'Сохранено', message: 'Инструкции применятся к новым сообщениям.' })).catch((e) => notifications.show({ color: 'red', title: 'Не сохранено', message: errText(e) }))}>Сохранить</Button>
      </Group>
    </Stack>
  )
}

function ProjectPanel() {
  const qc = useQueryClient()
  const proj = useQuery({ queryKey: AI_KEYS.defaultPrompt, queryFn: assistantApi.defaultPrompt, retry: false })
  const kb = useKbStatus(true)
  const [text, setText] = useState('')
  useEffect(() => { if (proj.data) setText(proj.data.content) }, [proj.data])
  const run = (fn: () => Promise<unknown>, ok: string) => void fn().then(() => notifications.show({ color: 'teal', title: ok, message: '' })).catch((e) => notifications.show({ color: 'red', title: 'Ошибка', message: errText(e) }))
  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Text fw={700}>Проектный промпт</Text>
        <Text size="sm" c="dimmed">Общие правила для всех пользователей. Новая версия применяется к новым сообщениям.</Text>
        <Textarea autosize minRows={5} maxRows={14} value={text} onChange={(e) => setText(e.currentTarget.value)} maxLength={12000} />
        <Group justify="space-between">
          <Text size="xs" c="dimmed">Версия {proj.data?.version ?? '—'}</Text>
          <Button disabled={!text.trim()} onClick={() => run(async () => { await assistantApi.saveDefaultPrompt(text); await qc.invalidateQueries({ queryKey: AI_KEYS.defaultPrompt }) }, 'Проектный промпт обновлён')}>Опубликовать версию</Button>
        </Group>
      </Stack>
      <Stack gap="xs">
        <Text fw={700}>База знаний</Text>
        {kb.data ? (
          <Table verticalSpacing={4} fz="sm"><Table.Tbody>
            <Table.Tr><Table.Td c="dimmed">Ревизия</Table.Td><Table.Td className="mono">{kb.data.revision ?? 'не построена'}</Table.Td></Table.Tr>
            <Table.Tr><Table.Td c="dimmed">Документов</Table.Td><Table.Td className="mono">{kb.data.documents}</Table.Td></Table.Tr>
            <Table.Tr><Table.Td c="dimmed">Модель эмбеддингов</Table.Td><Table.Td className="mono">{kb.data.embedding_model ?? '—'}{kb.data.dimensions ? `, ${kb.data.dimensions} изм.` : ''}</Table.Td></Table.Tr>
          </Table.Tbody></Table>
        ) : <Text size="sm" c="dimmed">{kb.isError ? kb.error.message : 'Загрузка…'}</Text>}
        <Group justify="flex-end">
          <Button variant="light" onClick={() => run(async () => { await assistantApi.kbReindex(); await qc.invalidateQueries({ queryKey: AI_KEYS.kb }) }, 'Индексация запущена')}>Переиндексировать</Button>
        </Group>
      </Stack>
    </Stack>
  )
}
