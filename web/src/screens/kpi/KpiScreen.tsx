/**
 * KPI (docs/UI_DESIGN.md §5.5, docs/UI_SPEC.md §2.4, §8.3).
 * - Прогноз и факт — РАЗНЫЕ строки (`kind`), показываются рядом: это прямое
 *   требование ТЗ.
 * - Нормы берутся только из строки (`target_min`/`target_max`), не зашиваются.
 * - Bus Factor — счётчик, а не процент: отдельная плашка-число.
 * - `details.note` и `details.method` — готовый русский текст, как есть.
 */
import { useQuery } from '@tanstack/react-query'
import { Badge, Group, Paper, ScrollArea, SimpleGrid, Skeleton, Stack, Table, Text, Title } from '@mantine/core'
import { useRun } from '../../hooks/useRun'
import { useKpiSnapshots, useSprintForecastAccuracy, useSprints } from '../../hooks/useViews'
import { QueryError, anyPending, firstError } from '../../components/common/QueryError'
import { AsOfLabel } from '../../components/common/AsOfLabel'
import { KpiStamp, toneOf } from '../../components/common/KpiStamp'
import { sprintGridTemplate } from '../../components/common/sprintGrid'
import { RISK_COLOR } from '../../components/common/RiskRail'
import { fmtDateShort, fmtSp, num } from '../../api/wire'
import { fetchPlanQuality } from '../../api/client'
import type {
  BusFactorKpiDetails,
  KpiSnapshotRow,
  PiPredictabilityDetails,
  SayDoDetails,
  SprintForecastAccuracyRow,
} from '../../types/views'

const n = (v: string | null): number | null => (v === null ? null : num(v))

export function KpiScreen() {
  const { runId, runs } = useRun()
  const latestRunId = Math.max(0, ...runs.map((run) => run.run_id))
  const qualityQ = useQuery({
    queryKey: ['plan-quality', runId],
    queryFn: () => fetchPlanQuality(runId!),
    enabled: runId !== null && runId === latestRunId,
    retry: false,
  })
  const kpiQ = useKpiSnapshots(runId)
  const sprintsQ = useSprints()
  const accuracyQ = useSprintForecastAccuracy(runId)
  const queries = [kpiQ, sprintsQ]
  const error = firstError(queries)

  if (anyPending(queries)) {
    return (
      <Stack gap="md">
        <Title order={2}>KPI</Title>
        <Skeleton height={220} />
        <Skeleton height={220} />
      </Stack>
    )
  }
  if (error) {
    return (
      <Stack gap="md">
        <Title order={2}>KPI</Title>
        <QueryError error={error} title="Не удалось загрузить KPI" />
      </Stack>
    )
  }

  const rows = kpiQ.data?.items ?? []
  const sprints = sprintsQ.data?.items ?? []
  const pred = rows.filter((r) => r.kpi_code === 'pi_predictability')
  const sayDo = rows.filter((r) => r.kpi_code === 'say_do_ratio')
  const bus = rows.find((r) => r.kpi_code === 'bus_factor') ?? null

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <div>
          <Title order={2}>KPI</Title>
          <Text c="dimmed" mt={2}>
            Три показателя качества плана: насколько он выполняется, как идут спринты и как много зависит от одного человека.
          </Text>
        </div>
        <AsOfLabel iso={kpiQ.data?.as_of ?? null} />
      </Group>

      <Paper withBorder p="md" style={{ borderStyle: 'dashed' }}>
        <Text fw={700} mb={6} style={{ fontFamily: 'var(--font-heading)' }}>Как читать круги</Text>
        <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
          <Legendary title="Тонкое кольцо" text="Прогноз по текущему плану." />
          <Legendary title="Залитая дуга" text="Факт по загруженным спринтам." />
          <Legendary title="Засечки на круге" text="Границы нормы. Показатели жёсткие: смотрите их вместе с числом задач в квартале и списком ролей без людей." />
        </SimpleGrid>
      </Paper>

      {rows.length === 0 ? (
        <Paper withBorder p="md">
          <Text size="sm" c="dimmed">
            {sprints.length === 0
              ? 'Датасет ещё не загружен. Загрузите его — базовый план посчитает прогноз KPI.'
              : runId === null
                ? 'Датасет загружен, но базовый план ещё не рассчитан. Перезапустите стек или повторите загрузку.'
                : `В прогоне ${runId} KPI не рассчитаны. Выберите успешный прогон или пересчитайте план.`}
          </Text>
        </Paper>
      ) : (
        <>
          <PredictabilityBlock rows={pred} />
          <SayDoBlock rows={sayDo} sprints={sprints} accuracy={accuracyQ.data?.items ?? []} />
          {bus && <BusFactorBlock row={bus} />}
        </>
      )}
      {runId === latestRunId && <Paper withBorder p="lg">
        <Stack gap="md">
          <Title order={3}>Качество и потери плана</Title>
          {qualityQ.isPending ? <Text size="sm" c="dimmed">Считаем показатели…</Text>
            : qualityQ.error ? <QueryError error={qualityQ.error} title="Не удалось посчитать качество плана" />
            : <>
              <Text size="sm" c="dimmed">{qualityQ.data.method}</Text>
              <SimpleGrid cols={{ base: 2, md: 3, xl: 6 }}>
                <QualityNumber label="Подтверждённая ценность" value={`${qualityQ.data.completed_value.sp} SP`} detail={`${qualityQ.data.completed_value.tasks} задач`} />
                <QualityNumber label="Частичные инициативы" value={qualityQ.data.partial_initiatives.length} detail={qualityQ.data.partial_initiatives.map((item) => item.prodf_id).join(', ') || 'Нет'} />
                <QualityNumber label="Ожидание зависимостей" value={`${qualityQ.data.dependency_wait.earliest_wait_sprints} спринтов`} detail={`${qualityQ.data.dependency_wait.tasks} задач с нижней границей позже первого спринта`} />
                <QualityNumber label="Перенос обещанного" value={`${qualityQ.data.deferred_commitments.sp} SP`} detail={`${qualityQ.data.deferred_commitments.tasks} задач`} />
                <QualityNumber label="Внепланово завершено" value={`${qualityQ.data.unplanned_completed_sp} SP`} detail="Вне канонического обещания Недели 0" />
                <QualityNumber label="Смены исполнителей" value={qualityQ.data.people_switches.length} detail={qualityQ.data.people_switches.map((item) => item.task_id).join(', ') || 'Нет'} />
              </SimpleGrid>
              {qualityQ.data.scarce_unused_roles.length > 0 && <Fact label="Незадействованный фонд дефицитных ролей">{qualityQ.data.scarce_unused_roles.map((item) => `${item.role} ${item.unused_hh} ЧЧ`).join('; ')}</Fact>}
              <Title order={4} mt="sm">Сравнение режимов на одном входе</Title>
              <Text size="sm" c="dimmed">{qualityQ.data.mode_comparison.method}</Text>
              <Table striped withTableBorder verticalSpacing="xs">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Режим</Table.Th>
                    <Table.Th ta="right">Завершено инициатив</Table.Th>
                    <Table.Th ta="right">SP завершённых</Table.Th>
                    <Table.Th ta="right">Частичных</Table.Th>
                    <Table.Th ta="right">Задач в плане</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {Object.entries(qualityQ.data.mode_comparison.modes).map(([mode, result]) => (
                    <Table.Tr key={mode}>
                      <Table.Td className="mono">{mode}</Table.Td>
                      <Table.Td ta="right" className="mono">{result.complete_initiatives}</Table.Td>
                      <Table.Td ta="right" className="mono">{result.complete_initiative_sp}</Table.Td>
                      <Table.Td ta="right" className="mono">{result.partial_initiatives}</Table.Td>
                      <Table.Td ta="right" className="mono">{result.planned_tasks}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
              {qualityQ.data.mode_comparison.order_search.status === 'computed' ? <Text size="sm" c="dimmed">
                Перебрано порядков инициатив: {qualityQ.data.mode_comparison.order_search.permutations}. Лучший результат среди этих порядков:{' '}
                {Object.entries(qualityQ.data.mode_comparison.order_search.best_by_mode ?? {}).map(([mode, result]) =>
                  `${mode} ${result.complete_initiative_sp} SP`).join('; ')}. {qualityQ.data.mode_comparison.order_search.method}
              </Text> : <Text size="sm" c="dimmed">Эталонный перебор: {qualityQ.data.mode_comparison.order_search.reason}.</Text>}
            </>}
        </Stack>
      </Paper>}
    </Stack>
  )
}

function Legendary({ title, text }: { title: string; text: string }) {
  return (
    <div>
      <Text size="sm" fw={600}>{title}</Text>
      <Text size="sm" c="dimmed">{text}</Text>
    </div>
  )
}

/** Блок KPI: заголовок, формула отдельной плашкой, затем содержимое. */
function Panel({ title, formula, children }: { title: string; formula?: string | null; children: React.ReactNode }) {
  return (
    <Paper withBorder p="lg">
      <Stack gap="md">
        <div>
          <Title order={3}>{title}</Title>
          {formula && (
            <Text size="sm" c="dimmed" mt={6} px="sm" py={4} className="mono" style={{ border: '1px dashed var(--mantine-color-default-border)', borderRadius: 6, display: 'inline-block' }}>
              {formula}
            </Text>
          )}
        </div>
        {children}
      </Stack>
    </Paper>
  )
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(170px, 260px) 1fr', gap: 16, padding: '6px 0', borderTop: '1px dashed var(--mantine-color-default-border)' }}>
      <Text size="sm" c="dimmed">{label}</Text>
      <Text size="sm" component="div">{children}</Text>
    </div>
  )
}

function QualityNumber({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return <Paper withBorder p="md" h="100%"><Text size="sm" c="dimmed">{label}</Text><Text fw={800} style={{ fontSize: '1.6rem', lineHeight: 1.2, fontFamily: 'var(--font-heading)' }}>{value}</Text><Text size="sm" c="dimmed">{detail}</Text></Paper>
}

// ------------------------------------------------ процент выполнения квартала
function PredictabilityBlock({ rows }: { rows: KpiSnapshotRow[] }) {
  const forecast = rows.find((r) => r.kind === 'forecast')
  const actual = rows.find((r) => r.kind === 'actual')
  const any = actual ?? forecast
  if (!any) return null
  const fd = forecast?.details as unknown as PiPredictabilityDetails | undefined
  const ad = actual?.details as unknown as PiPredictabilityDetails | undefined
  const d = ad ?? fd
  // Промежуточный факт нельзя сравнивать с итоговой нормой квартала: после 1-го спринта 0% — это ход по плану (DA-30).
  const intermediate = actual !== undefined && ad?.final === false
  const cover = (ad ?? fd)?.coverage

  return (
    <Panel title="Процент выполнения квартального плана" formula={d?.formula}>
      <Group align="flex-start" gap="xl" wrap="wrap">
        <KpiStamp
          title="Инициативы квартала"
          forecast={forecast ? n(forecast.value) : null}
          actual={actual ? n(actual.value) : null}
          targetMin={n(any.target_min)}
          targetMax={n(any.target_max)}
          neutralActual={intermediate}
          caption={intermediate ? `Промежуточно. Норма ${normText(any)} — к концу квартала` : `Норма ${normText(any)}`}
        />
        <Stack gap="sm" style={{ flex: 1, minWidth: 260 }}>
          <Pair label="Прогноз" row={forecast} />
          <Pair label="Факт" row={actual} emptyText="Факт появится после загрузки первого спринта." neutral={intermediate} />
          {intermediate && ad && <ProgressVsPlan details={ad} />}
          {cover && <CoverageLine cover={cover} />}
          {d && (
            <Stack gap={0}>
              <Fact label="Обещано в первоначальном плане">
                <b className="mono">{d.committed_n}</b> {plural(d.committed_n, 'инициатива', 'инициативы', 'инициатив')}:{' '}
                <span className="mono">{d.committed_initiatives.join(', ') || '—'}</span>
              </Fact>
              {ad?.completed_initiatives && (
                <Fact label="Завершены по факту">
                  <span className="mono">{ad.completed_initiatives.join(', ') || 'Пока ни одна'}</span>
                </Fact>
              )}
              {fd?.on_track_initiatives && (
                <Fact label="По плану успевают">
                  <span className="mono">{fd.on_track_initiatives.join(', ') || 'Ни одна'}</span>
                </Fact>
              )}
              {d.partial_initiatives.length > 0 && (
                <Fact label="Частично в плане (не входят в знаменатель)">
                  <span className="mono">{d.partial_initiatives.join(', ')}</span>
                </Fact>
              )}
            </Stack>
          )}
        </Stack>
      </Group>
    </Panel>
  )
}

/** «Охват»: знаменатель мира рядом с процентом, чтобы 100% не читались как «всё сделано» (DA-29). */
function CoverageLine({ cover }: { cover: NonNullable<PiPredictabilityDetails['coverage']> }) {
  return (
    <Stack gap={0}>
      <Fact label="Охват обязательств">
        <b className="mono">{cover.committed}</b> из <b className="mono">{cover.initiatives_total}</b> инициатив квартала.
        Частично в плане <b className="mono">{cover.partial}</b>, не обещано <b className="mono">{cover.not_promised}</b>.
      </Fact>
      <Fact label="Как это читать">
        KPI измеряет выполнение обещанного, а не качество самого обещания. 100% на малом охвате — повод смотреть на роли
        без людей и перенесённые задачи, а не повод успокоиться.
      </Fact>
    </Stack>
  )
}

/** Промежуточный ход сравнивается с плановым накоплением к этому спринту (DA-30). */
function ProgressVsPlan({ details }: { details: PiPredictabilityDetails }) {
  const expected = details.expected_completed_by_now ?? 0
  const done = details.completed_n ?? 0
  const word =
    details.progress_vs_plan === 'ahead' ? 'Впереди плана' : details.progress_vs_plan === 'behind' ? 'Отстаём от плана' : 'По плану'
  return (
    <Fact label={`К концу спринта ${details.reported_through_sprint}`}>
      По плану должно быть завершено <b className="mono">{expected}</b>, завершено <b className="mono">{done}</b>:{' '}
      <Badge variant="light" color={details.progress_vs_plan === 'behind' ? 'red' : 'teal'} style={{ textTransform: 'none' }}>{word}</Badge>
    </Fact>
  )
}

function Pair({ label, row, emptyText, neutral = false }: { label: string; row?: KpiSnapshotRow; emptyText?: string; neutral?: boolean }) {
  if (!row) {
    return emptyText ? (
      <Text size="sm" c="dimmed">
        {label}: {emptyText}
      </Text>
    ) : null
  }
  const value = n(row.value)
  const tone = value === null || neutral ? null : toneOf(value, n(row.target_min), n(row.target_max))
  const note = (row.details as { note?: string } | null)?.note
  const statusText = neutral && value !== null ? 'Промежуточный ход, итоговая норма — к концу квартала'
    : row.calculation_status === 'no_commitment' ? 'Нет обязательств в базовом плане'
    : row.calculation_status === 'no_plan' ? 'На спринт ничего не планировали'
    : row.calculation_status === 'no_relevant_skills' ? 'Нет востребованных компетенций'
    : 'Не определено'
  return (
    <div style={{ borderLeft: `4px solid ${tone === null ? 'var(--line)' : RISK_COLOR[toneToRisk(tone)]}`, paddingLeft: 10 }}>
      <Text size="sm" component="div">
        {label}: <b className="mono">{value === null ? 'н/д' : `${value.toFixed(2)}%`}</b>{' '}
        {tone === null ? statusText : <span style={{ color: RISK_COLOR[toneToRisk(tone)] }}>{TONE_WORD[tone]}</span>}
      </Text>
      {note && (
        <Text size="xs" c="dimmed" component="div">
          {note}
        </Text>
      )}
    </div>
  )
}

// ------------------------------------------------- выполнение плана спринта
function SayDoBlock({ rows, sprints, accuracy }: {
  rows: KpiSnapshotRow[]
  sprints: { sprint_no: number; start_date: string; end_date: string }[]
  accuracy: SprintForecastAccuracyRow[]
}) {
  if (rows.length === 0 || sprints.length === 0) return null
  const bySprint = new Map(rows.map((r) => [r.sprint_no, r]))
  const accuracyBySprint = new Map(accuracy.map((a) => [a.sprint_no, a]))
  const lastActual = [...rows].filter((r) => r.kind === 'actual').sort((a, b) => b.sprint_no - a.sprint_no)[0]
  const formula = (rows[0].details as unknown as SayDoDetails | null)?.formula
  // Шкала чуть выше верхней нормы, чтобы засечка 105% была видна; всё, что выше, — полное кольцо.
  const maxNorm = Math.max(...rows.map((r) => n(r.target_max) ?? 100))
  const domainMax = Math.ceil((maxNorm * 1.15) / 10) * 10

  return (
    <Panel title="Выполнение плана спринта" formula={formula}>
      <Stack gap={0}>
        <Fact label="Откуда данные">
          {lastActual ? `Факт загружен по спринт ${lastActual.sprint_no}, дальше прогноз.` : 'Факта пока нет, везде прогноз.'}{' '}
          Значение выше шкалы рисует полное кольцо, число в центре точное.
        </Fact>
        <Fact label="План завершений">SP задач, которые первоначальный план закрывает в спринте.</Fact>
        <Fact label="Бюджет работ">
          Доли SP, которые текущий план тратит в спринте (длинная задача распределена по спринтам), поэтому два числа
          могут не совпадать.
        </Fact>
        <Fact label="Закрытые спринты">
          Показан прогноз, сделанный перед спринтом, против факта: пересчёт прошлое обещание не улучшает.
        </Fact>
      </Stack>
      <ScrollArea type="auto">
        <div style={{ display: 'grid', gridTemplateColumns: sprintGridTemplate(sprints.length, '110px', '0px'), minWidth: 900 }}>
          <Cell head>Спринт</Cell>
          {sprints.map((s) => (
            <Cell key={s.sprint_no} head center>
              <div style={{ fontWeight: 700, color: 'var(--ink)' }}>Спринт {s.sprint_no}</div>
              <Text size="xs" c="dimmed" className="mono">
                {fmtDateShort(s.start_date)} – {fmtDateShort(s.end_date)}
              </Text>
            </Cell>
          ))}
          <div />

          <Cell>
            <Text size="sm" c="dimmed">
              Прогноз / факт
            </Text>
          </Cell>
          {sprints.map((s) => {
            const r = bySprint.get(s.sprint_no)
            if (!r) return <Cell key={s.sprint_no} center>—</Cell>
            const d = r.details as unknown as SayDoDetails
            const v = n(r.value)
            return (
              <Cell key={s.sprint_no} center>
                <div style={{ transform: 'scale(0.82)', transformOrigin: 'top center', height: 150 }}>
                  <KpiStamp
                    title={r.kind === 'actual' ? 'Факт' : 'Прогноз'}
                    forecast={r.kind === 'forecast' ? v : null}
                    actual={r.kind === 'actual' ? v : null}
                    targetMin={n(r.target_min)}
                    targetMax={n(r.target_max)}
                    domainMax={domainMax}
                  />
                </div>
                <Text size="xs" className="mono tabular">
                  {fmtSp(d.done_sp)} из {fmtSp(d.planned_sp)} SP
                </Text>
                {r.kind === 'forecast' && d.work_budget_sp != null && (
                  <Text size="xs" c="dimmed">
                    Бюджет работ {fmtSp(d.work_budget_sp)} SP
                  </Text>
                )}
                {r.kind === 'actual' && accuracyBySprint.get(s.sprint_no)?.forecast_done_sp != null && (
                  <Text size="xs" c="dimmed">
                    Перед спринтом ждали {fmtSp(accuracyBySprint.get(s.sprint_no)?.forecast_done_sp)} SP
                  </Text>
                )}
                {num(d.planned_sp) === 0 && (
                  <Text size="xs" c="dimmed">
                    План был пуст{num(d.unplanned_sp ?? '0') > 0 ? `; вне плана ${fmtSp(d.unplanned_sp)} SP` : ''}
                  </Text>
                )}
              </Cell>
            )
          })}
          <div />
        </div>
      </ScrollArea>
    </Panel>
  )
}

function Cell({ children, head, center }: { children?: React.ReactNode; head?: boolean; center?: boolean }) {
  return (
    <div
      style={{
        padding: '10px 8px',
        borderBottom: head ? '2px solid var(--ink)' : '1px solid var(--line)',
        textAlign: center ? 'center' : 'left',
        fontSize: 13,
        fontWeight: head ? 600 : 400,
        color: head ? 'var(--muted)' : undefined,
      }}
    >
      {children}
    </div>
  )
}

// ---------------------------------------------------------------- Bus Factor
function BusFactorBlock({ row }: { row: KpiSnapshotRow }) {
  const d = row.details as unknown as BusFactorKpiDetails
  const value = n(row.value)
  const min = n(row.target_min)
  const tone = value === null ? null : toneOf(value, min, n(row.target_max))
  const color = tone === null ? 'var(--line)' : RISK_COLOR[toneToRisk(tone)]
  return (
    <Panel title="Bus Factor" formula={null}>
      <Text size="sm" c="dimmed" mt={-8}>
        Счётчик людей, а не процент. Подробная карта на экране «Звёздная карта».
      </Text>
      <Group align="flex-start" gap="xl" wrap="wrap">
        <div style={{ borderLeft: `4px solid ${color}`, paddingLeft: 12, minWidth: 150 }}>
          <Text className="mono" style={{ fontSize: 44, lineHeight: 1, fontWeight: 600 }}>
            {value === null ? 'н/д' : fmtSp(value)}
          </Text>
          <Text size="sm" mt={6} style={{ color }}>
            {tone === null ? 'Нет востребованных компетенций' : TONE_WORD[tone]}
          </Text>
          <Text size="xs" c="dimmed">
            Норма {normText(row, '')}
          </Text>
        </div>
        <Stack gap={0} style={{ flex: 1, minWidth: 260 }}>
          <Fact label="Как считается">{d.method}</Fact>
          <Fact label="Компетенции">
            Всего <b className="mono">{d.competencies_n}</b>, с одним носителем <b className="mono">{d.single_holder_n}</b>,
            критичных <b className="mono">{d.critical_n}</b>.
          </Fact>
          {d.roles_without_staff.length > 0 && (
            <Fact label="Роли без людей в штате">
              <b className="mono">{d.roles_without_staff.length}</b>: {d.roles_without_staff.join(', ')}
            </Fact>
          )}
          {d.critical.length > 0 && (
            <Fact label={`Критичные компетенции (${d.critical.length})`}>{d.critical.join(', ')}</Fact>
          )}
          <Fact label="Примечание">{d.note}</Fact>
        </Stack>
      </Group>
    </Panel>
  )
}

// ------------------------------------------------------------------ helpers
type Tone = ReturnType<typeof toneOf>
const TONE_WORD: Record<Tone, string> = { ok: 'В норме', warning: 'Выше нормы', critical: 'Ниже нормы' }
function toneToRisk(t: Tone): Tone {
  return t
}

function normText(row: KpiSnapshotRow, unit = '%'): string {
  const lo = n(row.target_min)
  const hi = n(row.target_max)
  if (lo !== null && hi !== null) return `${fmtSp(lo)}–${fmtSp(hi)}${unit}`
  if (lo !== null) return `не ниже ${fmtSp(lo)}${unit}`
  if (hi !== null) return `не выше ${fmtSp(hi)}${unit}`
  return 'не задана'
}

function plural(k: number, one: string, few: string, many: string): string {
  const m10 = k % 10
  const m100 = k % 100
  if (m10 === 1 && m100 !== 11) return one
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few
  return many
}
