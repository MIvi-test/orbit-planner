BEGIN;
CREATE TABLE IF NOT EXISTS dq_issue_reviews (
    review_id BIGSERIAL PRIMARY KEY,
    issue_id INT NOT NULL REFERENCES dq_issues(issue_id) ON DELETE CASCADE,
    decision TEXT NOT NULL CHECK (decision IN ('acknowledged', 'resolved', 'reopened')),
    reviewer TEXT NOT NULL CHECK (length(trim(reviewer)) > 0),
    note TEXT NOT NULL CHECK (length(trim(note)) > 0),
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_dq_issue_reviews_issue ON dq_issue_reviews(issue_id, review_id DESC);
COMMENT ON TABLE dq_issue_reviews IS 'История решений по находке. Исходная находка ETL не перезаписывается.';

CREATE OR REPLACE VIEW v_dq_issue_worklist AS
SELECT i.issue_id, i.batch_id, i.entity, i.entity_id, i.rule_code,
       i.severity, i.detail,
       COALESCE(r.decision, 'open') AS review_status,
       r.reviewer, r.note AS review_note, r.reviewed_at,
       (i.severity = 'error' AND COALESCE(r.decision, 'open') <> 'resolved') AS is_blocking
FROM dq_issues i
LEFT JOIN LATERAL (
    SELECT decision, reviewer, note, reviewed_at
    FROM dq_issue_reviews WHERE issue_id = i.issue_id
    ORDER BY review_id DESC LIMIT 1
) r ON TRUE;
COMMIT;
