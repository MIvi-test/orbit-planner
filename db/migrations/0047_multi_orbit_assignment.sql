-- A person can serve the same task and role from several team orbits in one sprint.
ALTER TABLE plan_assignments DROP CONSTRAINT plan_assignments_pkey;
ALTER TABLE plan_assignments ADD CONSTRAINT plan_assignments_pkey
    PRIMARY KEY (run_id, task_id, sprint_no, engineer_id, role_id, home_team_id);
