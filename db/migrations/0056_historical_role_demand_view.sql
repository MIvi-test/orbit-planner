BEGIN;
CREATE VIEW v_plan_role_demand_snapshot AS
SELECT d.run_id, d.task_id, d.role_id, r.canonical_name AS role_name,
       d.needed_hours
FROM plan_role_demand_snapshot d
JOIN roles r ON r.role_id = d.role_id;
COMMIT;
