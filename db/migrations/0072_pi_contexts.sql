BEGIN;
CREATE TABLE IF NOT EXISTS public.pi_contexts (
    pi_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    schema_name TEXT NOT NULL UNIQUE,
    dataset_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (pi_id, scenario_id)
);
INSERT INTO public.pi_contexts (pi_id, scenario_id, schema_name, dataset_version)
SELECT p.pi_id, 'main', 'public', COALESCE(
    (SELECT source_sha256 FROM load_batches ORDER BY batch_id DESC LIMIT 1), 'unloaded')
FROM pi_periods p
WHERE current_schema() = 'public'
ON CONFLICT (pi_id, scenario_id) DO NOTHING;
COMMIT;
