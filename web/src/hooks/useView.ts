/**
 * Единая точка входа к витринам. КРИТИЧНО: у react-query кэш по `queryKey`,
 * а не по `queryFn` — если два места запросят один и тот же `queryKey` с
 * РАЗНОЙ формой ответа (например, один ждёт конверт, другой — `.items`),
 * второй молча получит данные первого и упадёт на чужой форме. Единственная
 * защита — один хук на все витрины, всегда возвращающий конверт целиком,
 * и ключ, целиком выведенный из имени витрины и параметров запроса.
 */
import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { fetchView, type ViewEnvelope, type ViewParams } from '../api/client'

async function fetchCompleteView<T>(name: string, params: ViewParams): Promise<ViewEnvelope<T>> {
  const first = await fetchView<T>(name, params)
  if (!first.has_more) return first

  const items = [...first.items]
  let page = first
  while (page.has_more) {
    const offset = page.offset + page.returned
    if (page.returned === 0) throw new Error(`${name}: сервер вернул пустую непоследнюю страницу`)
    page = await fetchView<T>(name, {
      ...params,
      runId: first.run_id ?? params.runId,
      offset,
    })
    if (page.count !== first.count || page.run_id !== first.run_id) {
      throw new Error(`${name}: данные изменились во время загрузки страниц`)
    }
    items.push(...page.items)
  }
  if (items.length !== first.count - first.offset) {
    throw new Error(`${name}: получены не все строки витрины`)
  }
  return { ...first, items, returned: items.length, truncated: false, has_more: false }
}

export function useView<T>(name: string, params: ViewParams = {}): UseQueryResult<ViewEnvelope<T>> {
  return useQuery({
    queryKey: ['view', name, params.runId ?? null, params.limit ?? null, params.offset ?? null, params.order ?? null],
    queryFn: () => fetchCompleteView<T>(name, params),
  })
}
