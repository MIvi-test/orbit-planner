import { useMemo, useState } from 'react'
import { ActionIcon, Badge, Button, Group, Loader, Menu, ScrollArea, Skeleton, Stack, Text, TextInput, UnstyledButton } from '@mantine/core'
import { IconBook2, IconChartInfographic, IconDots, IconLock, IconPencil, IconPlus, IconSearch, IconTrash, IconWorld } from '@tabler/icons-react'
import type { Conversation } from '../../api/assistant'
import { useConversationList } from './hooks'

/** История чатов: новые сверху, поиск по названию, подгрузка по курсору. */
export function ChatList({ activeId, onSelect, onNew, onRename, onDelete }: {
  activeId: string | null
  onSelect: (c: Conversation) => void
  onNew: () => void
  onRename: (c: Conversation) => void
  onDelete: (c: Conversation) => void
}) {
  const q = useConversationList()
  const [search, setSearch] = useState('')
  const items = useMemo(() => (q.data?.pages.flatMap((p) => p.items) ?? []), [q.data])
  const shown = items.filter((c) => !search || (c.title ?? 'Новый чат').toLowerCase().includes(search.toLowerCase()))
  return (
    <div className="ai-panel ai-history">
      <Button fullWidth leftSection={<IconPlus size={18} />} onClick={onNew}>Новый чат</Button>
      <TextInput mt="sm" placeholder="Поиск по чатам" leftSection={<IconSearch size={16} />} value={search} onChange={(e) => setSearch(e.currentTarget.value)} />
      <Text className="ai-label" mt="md" mb={6}>История {items.length > 0 && <span className="mono">({items.length})</span>}</Text>
      <ScrollArea style={{ flex: 1, minHeight: 0 }} type="auto" scrollbarSize={5}>
        <Stack gap={6}>
          {q.isPending && Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} height={54} radius={10} />)}
          {q.isError && <Text size="sm" c="dimmed">Не удалось загрузить историю: {q.error.message}</Text>}
          {!q.isPending && !q.isError && shown.length === 0 && (
            <Text size="sm" c="dimmed">{items.length === 0 ? 'Чатов пока нет. Начните новый — он сохранится здесь.' : 'Ничего не найдено.'}</Text>
          )}
          {shown.map((c) => (
            <div key={c.conversation_id} className="ai-history__row">
            <UnstyledButton className="ai-history__item" data-active={c.conversation_id === activeId || undefined} onClick={() => onSelect(c)}>
              <Group gap={8} wrap="nowrap" align="flex-start">
                <span className="ai-history__icon">{c.scope === 'planning' ? <IconChartInfographic size={17} /> : <IconBook2 size={17} />}</span>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <Text size="sm" fw={600} lineClamp={2} style={{ lineHeight: 1.3 }}>{c.title || 'Новый чат'}</Text>
                  <Group gap={6} mt={4} wrap="nowrap">
                    <Badge size="xs" variant="light" color={c.scope === 'planning' ? 'blue' : 'gray'}>{c.scope === 'planning' ? 'План' : 'Знания'}</Badge>
                    <span className="ai-history__meta" title={c.privacy_mode === 'local_only' ? 'Только локальная модель' : 'Настроенная модель'}>
                      {c.privacy_mode === 'local_only' ? <IconLock size={12} /> : <IconWorld size={12} />}
                    </span>
                    {c.newer_run_available && <Badge size="xs" color="yellow" variant="filled">Новый прогон</Badge>}
                  </Group>
                </div>
              </Group>
            </UnstyledButton>
            <Menu position="bottom-end" withinPortal shadow="md">
              <Menu.Target>
                <ActionIcon className="ai-history__menu" variant="subtle" color="gray" size="sm" aria-label="Действия с чатом"><IconDots size={16} /></ActionIcon>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item leftSection={<IconPencil size={15} />} onClick={() => onRename(c)}>Переименовать</Menu.Item>
                <Menu.Item color="red" leftSection={<IconTrash size={15} />} onClick={() => onDelete(c)}>Удалить</Menu.Item>
              </Menu.Dropdown>
            </Menu>
            </div>
          ))}
          {q.hasNextPage && (
            <Button variant="subtle" size="compact-sm" onClick={() => void q.fetchNextPage()} disabled={q.isFetchingNextPage} leftSection={q.isFetchingNextPage ? <Loader size={12} /> : undefined}>
              Показать ещё
            </Button>
          )}
        </Stack>
      </ScrollArea>
    </div>
  )
}
