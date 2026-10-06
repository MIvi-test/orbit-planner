import { useState, type ReactNode } from 'react'
import { ActionIcon, Button, Group, Menu, Modal, Select, Text, Textarea, Tooltip } from '@mantine/core'
import { IconBook2, IconChartInfographic, IconCheck, IconChevronDown, IconLock, IconSend2, IconWorld } from '@tabler/icons-react'
import type { PrivacyMode, ProviderProfile, Scope } from '../../api/assistant'

/** Приватность выводится из модели: внутренняя — «только локально», внешняя — «настроенный сервис». */
export const privacyFor = (p: ProviderProfile): PrivacyMode => (p.network_scope === 'internal' ? 'local_only' : 'configured')

/** Поле ввода с панелью под ним: слева тема и модель, справа подсказка. */
export function Composer({ busy, disabled, placeholder, onSend, toolbar }: {
  busy: boolean
  disabled?: boolean
  placeholder?: string
  onSend: (text: string) => void
  toolbar?: ReactNode
}) {
  const [text, setText] = useState('')
  const send = () => {
    if (!text.trim() || busy || disabled) return
    onSend(text)
    setText('')
  }
  return (
    <div className="ai-composer">
      <div className="ai-composer__box">
        <Textarea variant="unstyled" autosize minRows={1} maxRows={6} value={text} maxLength={10000}
          onChange={(e) => setText(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          placeholder={busy ? 'Дождитесь ответа…' : placeholder ?? 'Задайте вопрос…'} disabled={busy || disabled} />
        <div className="ai-composer__bar">
          <Group gap={6} wrap="wrap" style={{ flex: 1, minWidth: 0 }}>{toolbar}</Group>
          <Text size="xs" c="dimmed" className="ai-composer__hint">Enter — отправить, Shift+Enter — строка</Text>
          <Tooltip label="Отправить">
            <ActionIcon size="lg" radius="xl" variant="filled" disabled={busy || disabled || !text.trim()} onClick={send} aria-label="Отправить"><IconSend2 size={18} /></ActionIcon>
          </Tooltip>
        </div>
      </div>
    </div>
  )
}

/** Выбор модели внизу чата. Переход с локальной модели на внешнюю требует подтверждения. */
export function ModelPicker({ profiles, value, current, onChange, disabled }: {
  profiles: ProviderProfile[]
  value: number | null
  /** Текущая приватность чата: при смене local_only → внешний сервис спрашиваем подтверждение. */
  current?: PrivacyMode
  onChange: (p: ProviderProfile) => void
  disabled?: boolean
}) {
  const [confirm, setConfirm] = useState<ProviderProfile | null>(null)
  const selected = profiles.find((p) => p.profile_id === value)
  const pick = (id: string | null) => {
    const p = profiles.find((x) => String(x.profile_id) === id)
    if (!p || p.profile_id === value) return
    if (current === 'local_only' && p.network_scope === 'external') setConfirm(p)
    else onChange(p)
  }
  return (
    <>
      <Select size="xs" className="ai-model-select" disabled={disabled} allowDeselect={false} comboboxProps={{ position: 'top-start', width: 300 }}
        value={value !== null ? String(value) : null} onChange={pick}
        placeholder={profiles.length ? 'Модель отключена — выберите' : 'Нет моделей'}
        error={value !== null && !selected ? true : undefined}
        leftSection={selected ? (selected.network_scope === 'internal' ? <IconLock size={14} /> : <IconWorld size={14} />) : undefined}
        data={[
          { group: 'Локальные', items: profiles.filter((p) => p.network_scope === 'internal').map((p) => ({ value: String(p.profile_id), label: p.name })) },
          { group: 'Внешние сервисы', items: profiles.filter((p) => p.network_scope === 'external').map((p) => ({ value: String(p.profile_id), label: p.name })) },
        ].filter((g) => g.items.length)}
        renderOption={({ option, checked }) => {
          const p = profiles.find((x) => String(x.profile_id) === option.value)
          return (
            <Group gap={8} wrap="nowrap" style={{ width: '100%' }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <Text size="sm" fw={600}>{option.label}</Text>
                <Text size="xs" c="dimmed" className="mono" truncate>{p?.model}{p && !p.credential_configured ? ' · ключ не задан' : ''}</Text>
              </div>
              {checked && <IconCheck size={15} />}
            </Group>
          )
        }} />
      <Modal opened={confirm !== null} onClose={() => setConfirm(null)} title="Перейти на внешний сервис?" centered>
        <Text size="sm">Сейчас чат работает только с локальной моделью. С «{confirm?.name}» вопросы и контекст чата будут отправляться внешнему провайдеру.</Text>
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={() => setConfirm(null)}>Отмена</Button>
          <Button onClick={() => { if (confirm) onChange(confirm); setConfirm(null) }}>Перейти</Button>
        </Group>
      </Modal>
    </>
  )
}

/** О чём чат: вопросы о системе или разбор прогона. Для нового чата выбирается свободно, у начатого — только подключение прогона. */
export function ScopePicker({ scope, runId, latestRun, locked, onChange }: {
  scope: Scope
  runId: number | null
  latestRun: number | null
  /** Чат уже начат: разбор прогона назад в «знания» не переключается. */
  locked?: boolean
  onChange: (scope: Scope) => void
}) {
  const planning = scope === 'planning'
  const label = planning ? `Разбор прогона${runId !== null ? ` №${runId}` : ''}` : 'Вопросы о системе'
  const icon = planning ? <IconChartInfographic size={14} /> : <IconBook2 size={14} />
  if (locked && planning) return <Button size="compact-sm" variant="light" leftSection={icon} className="ai-chip-btn" style={{ pointerEvents: 'none' }}>{label}</Button>
  return (
    <Menu position="top-start" shadow="md" withinPortal>
      <Menu.Target>
        <Button size="compact-sm" variant="light" leftSection={icon} rightSection={<IconChevronDown size={13} />} className="ai-chip-btn">{label}</Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item leftSection={<IconBook2 size={16} />} disabled={locked} onClick={() => onChange('knowledge')}
          rightSection={!planning ? <IconCheck size={14} /> : null}>
          <Text size="sm" fw={600}>Вопросы о системе</Text>
          <Text size="xs" c="dimmed">Правила, формулы, данные. Прогон не нужен</Text>
        </Menu.Item>
        <Menu.Item leftSection={<IconChartInfographic size={16} />} disabled={latestRun === null} onClick={() => onChange('planning')}
          rightSection={planning ? <IconCheck size={14} /> : null}>
          <Text size="sm" fw={600}>{latestRun !== null ? `Разбор прогона №${latestRun}` : 'Разбор прогона'}</Text>
          <Text size="xs" c="dimmed">{latestRun !== null ? (locked ? 'Подключить прогон к этому чату' : 'Ответы по данным выбранного прогона') : 'Сначала загрузите датасет'}</Text>
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  )
}
