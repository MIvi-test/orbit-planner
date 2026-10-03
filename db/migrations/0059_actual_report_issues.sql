BEGIN;
CREATE TABLE actual_report_issues (
    upload_id INT NOT NULL REFERENCES actual_uploads(upload_id) ON DELETE CASCADE,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    role_id SMALLINT REFERENCES roles(role_id),
    issue_code TEXT NOT NULL CHECK (issue_code IN
        ('UNPLANNED_ROLE', 'ROLE_OVERRUN', 'TODO_WITH_HOURS', 'DONE_WITH_NEW_HOURS', 'STATUS_REGRESSION')),
    detail TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (btrim(reason) <> ''),
    resolved_revision_id BIGINT REFERENCES task_role_etc(revision_id)
);
CREATE INDEX ix_actual_report_issues_upload ON actual_report_issues(upload_id);
COMMIT;
