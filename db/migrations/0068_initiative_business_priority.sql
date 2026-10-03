-- DA-11: явный бизнес-приоритет инициативы. Приоритет из датасета (priority_rung = MAX(rung) задач,
-- ADR-005) остаётся эвристикой; business_priority задаёт человек и главнее любой стратегии (ADR-032).
ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS business_priority SMALLINT
    CHECK (business_priority BETWEEN 0 AND 1000);
ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS business_priority_by TEXT;
ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS business_priority_at TIMESTAMPTZ;
ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS business_priority_note TEXT;
COMMENT ON COLUMN initiatives.business_priority IS
 'Явный приоритет инициативы, заданный человеком (в шкале rung); NULL — берётся priority_rung из датасета.';
