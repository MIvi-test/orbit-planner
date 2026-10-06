import { Select } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { fetchPiContexts, selectPiContext, selectedPiContext } from '../../api/client'

export function PiContextSelect() {
  const query = useQuery({ queryKey: ['pi-contexts'], queryFn: fetchPiContexts })
  const selected = selectedPiContext()
  const contexts = query.data?.contexts ?? []
  const active = selected
    ? contexts.find((row) => row.pi_id === selected.pi_id && row.scenario_id === selected.scenario_id)
    : contexts.find((row) => row.schema_name === 'public')

  return (
    <Select
      aria-label="PI и сценарий"
      placeholder="Выберите PI"
      w={170}
      size="sm"
      data={contexts.map((row) => ({
        value: `${row.pi_id}|${row.scenario_id}`,
        label: `${row.pi_id} / ${row.scenario_id}`,
      }))}
      value={active ? `${active.pi_id}|${active.scenario_id}` : null}
      onChange={(value) => {
        const context = contexts.find((row) => `${row.pi_id}|${row.scenario_id}` === value)
        if (context) selectPiContext(context.schema_name === 'public' ? null : context)
      }}
    />
  )
}
