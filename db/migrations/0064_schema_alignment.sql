-- B-7: выровнять схему, полученную обновлением миграциями, со схемой чистой установки.
-- Миграция 0045 добавила plan_assignments.work_hours как nullable без CHECK, а
-- базовая схема объявляет NOT NULL CHECK (work_hours > 0). После 0045 колонка
-- заполнена для всех строк, поэтому ограничения можно ставить.
ALTER TABLE plan_assignments ALTER COLUMN work_hours SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'plan_assignments'::regclass
          AND conname = 'plan_assignments_work_hours_check'
    ) THEN
        ALTER TABLE plan_assignments
            ADD CONSTRAINT plan_assignments_work_hours_check CHECK (work_hours > 0);
    END IF;
END
$$;
