BEGIN;
CREATE TABLE plan_decision_goal_map (
    decision TEXT PRIMARY KEY CHECK (decision IN ('in_quarter','deferred_next_pi','cancelled')),
    proposal_action TEXT NOT NULL CHECK (proposal_action IN ('pursue_goal','defer','recommend_cancel')),
    fallback_result_code TEXT REFERENCES ref_result_options(code)
);
INSERT INTO plan_decision_goal_map (decision, proposal_action, fallback_result_code) VALUES
  ('in_quarter', 'pursue_goal', NULL),
  ('deferred_next_pi', 'defer', 'NOT_IN_PI'),
  ('cancelled', 'recommend_cancel', 'NOT_IN_PI');
CREATE TABLE task_goal_confirmations (
    confirmation_id BIGSERIAL PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    goal_code TEXT REFERENCES ref_result_options(code),
    closure_code TEXT NOT NULL REFERENCES ref_closure_results(code),
    confirmed_by TEXT NOT NULL CHECK (btrim(confirmed_by) <> ''),
    note TEXT NOT NULL CHECK (btrim(note) <> ''),
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (closure_code <> 'ACHIEVED' OR (goal_code IS NOT NULL AND goal_code ~ '^R[1-6]$'))
);
CREATE INDEX ix_task_goal_confirmations_latest ON task_goal_confirmations(task_id, confirmed_at DESC, confirmation_id DESC);
CREATE VIEW v_plan_goal_outcome AS
WITH resolved AS (
    SELECT r.run_id, st.task_id, t.prodf_id, st.status, s.decision,
           t.result_planned, t.result_customer, t.result_executor,
           m.proposal_action,
           CASE WHEN m.proposal_action = 'pursue_goal'
                THEN COALESCE(t.result_executor, t.result_customer, t.result_planned)
                ELSE m.fallback_result_code END AS proposed_goal_code,
           COALESCE(c.closure_code, CASE WHEN st.status = 'Done' THEN t.result_final END)
               AS confirmed_closure_code,
           COALESCE(c.goal_code, CASE WHEN st.status = 'Done' AND t.result_final = 'ACHIEVED'
                THEN COALESCE(t.result_customer, t.result_executor, t.result_planned) END)
               AS confirmed_goal_code,
           CASE WHEN c.confirmation_id IS NOT NULL THEN 'user'
                WHEN st.status = 'Done' AND t.result_final IS NOT NULL THEN 'dataset'
                ELSE NULL END AS confirmation_source
    FROM plan_runs r
    JOIN task_state st ON st.run_id = r.run_id
    JOIN tasks t ON t.task_id = st.task_id
    LEFT JOIN plan_task_schedule s ON s.run_id = r.run_id AND s.task_id = st.task_id
    LEFT JOIN plan_decision_goal_map m ON m.decision = s.decision
    LEFT JOIN LATERAL (
        SELECT c.confirmation_id, c.goal_code, c.closure_code
        FROM task_goal_confirmations c
        WHERE c.task_id = st.task_id AND c.confirmed_at <= r.created_at
        ORDER BY c.confirmed_at DESC, c.confirmation_id DESC LIMIT 1
    ) c ON TRUE
)
SELECT x.*, requested.label AS requested_goal_label,
       proposed.label AS proposed_goal_label,
       confirmed.label AS confirmed_goal_label,
       closure.label AS confirmed_closure_label,
       CASE WHEN x.confirmed_closure_code = 'ACHIEVED' THEN 'confirmed_achieved'
            WHEN x.confirmed_closure_code = 'CANCELLED_BY_CUSTOMER' THEN 'customer_cancelled'
            WHEN x.confirmed_closure_code = 'NOT_ACHIEVED' THEN 'confirmed_not_achieved'
            WHEN x.status = 'Done' THEN 'unconfirmed_done'
            ELSE 'pending' END AS confirmation_state,
       CASE WHEN COALESCE(x.result_executor, x.result_customer, x.result_planned) ~ '^R[1-6]$'
            THEN substring(COALESCE(x.result_executor, x.result_customer, x.result_planned) FROM 2)::int END AS target_goal_rank,
       CASE WHEN x.confirmed_goal_code ~ '^R[1-6]$'
            THEN substring(x.confirmed_goal_code FROM 2)::int END AS confirmed_goal_rank
FROM resolved x
LEFT JOIN ref_result_options requested ON requested.code = COALESCE(x.result_executor, x.result_customer, x.result_planned)
LEFT JOIN ref_result_options proposed ON proposed.code = x.proposed_goal_code
LEFT JOIN ref_result_options confirmed ON confirmed.code = x.confirmed_goal_code
LEFT JOIN ref_closure_results closure ON closure.code = x.confirmed_closure_code;

CREATE VIEW v_initiative_goal_progress AS
SELECT run_id, prodf_id, COUNT(*) AS task_count,
       COUNT(*) FILTER (WHERE target_goal_rank IS NOT NULL) AS target_task_count,
       COUNT(*) FILTER (WHERE target_goal_rank IS NOT NULL
           AND confirmation_state = 'confirmed_achieved'
           AND confirmed_goal_rank >= target_goal_rank) AS confirmed_target_count,
       COUNT(*) FILTER (WHERE proposal_action = 'pursue_goal') AS proposed_in_pi_count,
       MAX(target_goal_rank) AS highest_requested_stage,
       CASE WHEN COUNT(*) FILTER (WHERE target_goal_rank IS NOT NULL) = 0 THEN 'goal_unknown'
            WHEN COUNT(*) FILTER (WHERE target_goal_rank IS NOT NULL
                 AND confirmation_state = 'confirmed_achieved'
                 AND confirmed_goal_rank >= target_goal_rank)
                 = COUNT(*) FILTER (WHERE target_goal_rank IS NOT NULL) THEN 'confirmed_achieved'
            WHEN COUNT(*) FILTER (WHERE proposal_action = 'pursue_goal'
                 OR confirmation_state = 'confirmed_achieved') = COUNT(*) THEN 'forecast_in_pi'
            ELSE 'at_risk' END AS quarter_goal_status
FROM v_plan_goal_outcome
GROUP BY run_id, prodf_id;

COMMIT;
