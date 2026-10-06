import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { allMessages, assistantApi } from '../../api/assistant'

export const AI_KEYS = {
  profiles: ['assistant', 'profiles'] as const,
  list: ['assistant', 'conversations'] as const,
  conv: (id: string) => ['assistant', 'conversation', id] as const,
  messages: (id: string) => ['assistant', 'messages', id] as const,
  recs: (id: string) => ['assistant', 'recommendations', id] as const,
  evidence: (id: string) => ['assistant', 'evidence', id] as const,
  kb: ['assistant', 'kb'] as const,
  myPrompt: ['assistant', 'prompt', 'me'] as const,
  defaultPrompt: ['assistant', 'prompt', 'default'] as const,
}

export const useProfiles = () => useQuery({ queryKey: AI_KEYS.profiles, queryFn: assistantApi.profiles, retry: false })

export const useConversationList = () =>
  useInfiniteQuery({
    queryKey: AI_KEYS.list,
    queryFn: ({ pageParam }) => assistantApi.conversations(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: false,
  })

export const useConversation = (id: string | null) =>
  useQuery({ queryKey: AI_KEYS.conv(id ?? ''), queryFn: () => assistantApi.conversation(id!), enabled: id !== null, retry: false })

export const useMessages = (id: string | null) =>
  useQuery({ queryKey: AI_KEYS.messages(id ?? ''), queryFn: () => allMessages(id!), enabled: id !== null, retry: false })

export const useRecommendations = (id: string | null) =>
  useQuery({ queryKey: AI_KEYS.recs(id ?? ''), queryFn: () => assistantApi.recommendations(id!), enabled: id !== null, retry: false })

export const useEvidence = (id: string | null) =>
  useQuery({ queryKey: AI_KEYS.evidence(id ?? ''), queryFn: () => assistantApi.evidence(id!), enabled: id !== null, retry: false })

export const useKbStatus = (enabled: boolean) =>
  useQuery({ queryKey: AI_KEYS.kb, queryFn: assistantApi.kbStatus, enabled, retry: false })
