BEGIN;
ALTER TABLE pi_periods ALTER COLUMN sprint_count SET DEFAULT 6;
COMMENT ON TABLE pi_periods IS
 'PI начинается 01.07.2026 и длится шесть двухнедельных спринтов до 22.09.2026 (ADR-025). '
 'Фонд ставки = 6 × 80 = 480 ЧЧ; остаток календарного квартала не входит в PI.';
COMMENT ON TABLE sprints IS
 'Шесть двухнедельных спринтов от PI_START до PI_END; календарь задаётся текущей спецификацией.';
COMMIT;
