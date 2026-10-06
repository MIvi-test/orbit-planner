-- B-6: остаток без ETC = смета − факт (предварительный), а не «неизвестно».
-- Раньше любая роль с потраченными часами без ETC получала остаток 0 и флаг
-- remaining_unknown: на выданном датасете это откладывало все задачи в работе
-- (в том числе DB-202 из онбординга). Теперь:
--   * есть ETC            -> остаток = ETC;
--   * ETC нет, смета > факт -> остаток = смета − факт, remaining_provisional = true;
--   * ETC нет, факт >= смета (смета исчерпана) -> остаток 0, remaining_unknown = true.
-- Новая колонка добавляется в конец: зависимые витрины не пересоздаются.
CREATE OR REPLACE VIEW v_task_remaining_hh AS
SELECT COALESCE(e.task_id, s.task_id)                            AS task_id,
       COALESCE(e.role_id, s.role_id)                            AS role_id,
       COALESCE(e.hours, 0)                                      AS estimated_hours,
       COALESCE(s.hours, 0)                                      AS spent_hours,
       COALESCE(etc.remaining_hours,
                GREATEST(COALESCE(e.hours, 0) - COALESCE(s.hours, 0), 0)) AS remaining_hours,
       (etc.revision_id IS NULL AND t.status <> 'Done'
        AND COALESCE(s.hours, 0) > 0
        AND COALESCE(s.hours, 0) >= COALESCE(e.hours, 0))        AS remaining_unknown,
       etc.reason                                                AS etc_reason,
       (etc.revision_id IS NULL AND t.status <> 'Done'
        AND COALESCE(s.hours, 0) > 0
        AND COALESCE(e.hours, 0) > COALESCE(s.hours, 0))         AS remaining_provisional
FROM task_role_estimates e
FULL OUTER JOIN task_role_spent s
  ON s.task_id = e.task_id AND s.role_id = e.role_id
JOIN tasks t ON t.task_id = COALESCE(e.task_id, s.task_id)
LEFT JOIN LATERAL (
    SELECT x.revision_id, x.remaining_hours, x.reason FROM task_role_etc x
    WHERE x.task_id = e.task_id AND x.role_id = e.role_id
    ORDER BY x.revision_id DESC LIMIT 1
) etc ON TRUE;

COMMENT ON VIEW v_task_remaining_hh IS
 'Остаток часов по задаче и роли. ETC (task_role_etc) главнее; без ETC остаток = смета − факт '
 '(remaining_provisional = факт есть, но прогресс не подтверждён). remaining_unknown — смета роли '
 'исчерпана у незакрытой задачи: нужен ETC, сам по себе остаток 0 не означает готовность.';
