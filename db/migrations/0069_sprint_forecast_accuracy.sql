-- DA-32: прогноз перед спринтом против факта.
DROP VIEW IF EXISTS v_sprint_forecast_accuracy;
-- --------------------------------------------------------------------
--  Точность прогона «выполнение плана спринта» (DA-32): что план обещал ПЕРЕД спринтом и что
--  получилось. Прогноз берётся из последнего прогона, действовавшего на старте спринта
--  (as_of_sprint <= спринта, построенного на факте строго предыдущих спринтов).
-- --------------------------------------------------------------------
CREATE VIEW v_sprint_forecast_accuracy AS
SELECT a.run_id, a.sprint_no,
       (a.details->>'planned_sp')::numeric   AS planned_sp,
       f.run_id                              AS forecast_run_id,
       (f.details->>'done_sp')::numeric      AS forecast_done_sp,
       (a.details->>'done_sp')::numeric      AS actual_done_sp,
       f.value                               AS forecast_value,
       a.value                               AS actual_value
FROM kpi_snapshots a
LEFT JOIN LATERAL (
    SELECT k.run_id, k.details, k.value
    FROM kpi_snapshots k
    JOIN plan_runs p ON p.run_id = k.run_id
    WHERE k.kpi_code = 'say_do_ratio' AND k.kind = 'forecast' AND k.sprint_no = a.sprint_no
      AND p.status IN ('ok', 'infeasible') AND p.run_id < a.run_id AND p.as_of_sprint <= a.sprint_no
      AND (p.actuals_upload_id IS NULL OR EXISTS (
            SELECT 1 FROM actual_uploads u WHERE u.upload_id = p.actuals_upload_id AND u.sprint_no < a.sprint_no))
    ORDER BY p.run_id DESC LIMIT 1
) f ON TRUE
WHERE a.kpi_code = 'say_do_ratio' AND a.kind = 'actual';
COMMENT ON VIEW v_sprint_forecast_accuracy IS
 'По каждому закрытому спринту: прогноз, сделанный перед ним (SP к закрытию), против факта. Помогает отличить '
 'провал исполнения от плохого прогноза; позднее пересчёт прошлое обещание не улучшает.';
