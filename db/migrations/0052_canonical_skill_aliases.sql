CREATE TABLE IF NOT EXISTS skill_aliases (
    alias_key TEXT NOT NULL,
    skill_id INT NOT NULL REFERENCES skills(skill_id) ON DELETE CASCADE,
    alias_text TEXT NOT NULL,
    rule TEXT NOT NULL CHECK (rule IN ('synonym','composite')),
    PRIMARY KEY (alias_key, skill_id)
);
CREATE TABLE IF NOT EXISTS engineer_skill_declarations (
    declaration_id BIGSERIAL PRIMARY KEY,
    engineer_id TEXT NOT NULL REFERENCES engineers(engineer_id) ON DELETE CASCADE,
    raw_text TEXT NOT NULL,
    skill_id INT NOT NULL REFERENCES skills(skill_id),
    source_row INT,
    UNIQUE (engineer_id, raw_text, skill_id, source_row)
);

-- Existing installations retain the original label before IDs are normalized.
INSERT INTO engineer_skill_declarations (engineer_id, raw_text, skill_id)
SELECT es.engineer_id, s.name, s.skill_id
FROM engineer_skills es JOIN skills s USING (skill_id)
WHERE NOT EXISTS (
    SELECT 1 FROM engineer_skill_declarations d
    WHERE d.engineer_id = es.engineer_id AND d.skill_id = s.skill_id
);

CREATE TEMP TABLE tmp_skill_expansions (
    alias_key TEXT, canonical_name TEXT, rule TEXT,
    PRIMARY KEY (alias_key, canonical_name)
) ON COMMIT DROP;
INSERT INTO tmp_skill_expansions VALUES
    ('apache kafka', 'Kafka', 'synonym'),
    ('core spring', 'Spring Core', 'synonym'),
    ('микросервисы', 'Microservices', 'synonym'),
    ('rest/grpc', 'REST', 'composite'),
    ('rest/grpc', 'gRPC', 'composite'),
    ('rest/soap интеграции', 'REST', 'composite'),
    ('rest/soap интеграции', 'SOAP', 'composite'),
    ('ci/cd (gitlab, jenkins)', 'CI/CD', 'composite'),
    ('ci/cd (gitlab, jenkins)', 'GitLab', 'composite'),
    ('ci/cd (gitlab, jenkins)', 'Jenkins', 'composite');

INSERT INTO skills (name, normalized_name)
SELECT DISTINCT canonical_name, lower(canonical_name)
FROM tmp_skill_expansions
ON CONFLICT (normalized_name) DO NOTHING;

INSERT INTO skill_aliases (alias_key, skill_id, alias_text, rule)
SELECT x.alias_key, target.skill_id, COALESCE(source.name, x.alias_key), x.rule
FROM tmp_skill_expansions x
JOIN skills target ON target.normalized_name = lower(x.canonical_name)
LEFT JOIN skills source ON source.normalized_name = x.alias_key
ON CONFLICT (alias_key, skill_id) DO NOTHING;

INSERT INTO engineer_skills (engineer_id, skill_id)
SELECT DISTINCT es.engineer_id, target.skill_id
FROM engineer_skills es
JOIN skills source ON source.skill_id = es.skill_id
JOIN tmp_skill_expansions x ON x.alias_key = source.normalized_name
JOIN skills target ON target.normalized_name = lower(x.canonical_name)
ON CONFLICT DO NOTHING;

INSERT INTO task_role_skill_requirements (task_id, role_id, skill_id, source_text)
SELECT DISTINCT q.task_id, q.role_id, target.skill_id, q.source_text
FROM task_role_skill_requirements q
JOIN skills source ON source.skill_id = q.skill_id
JOIN tmp_skill_expansions x ON x.alias_key = source.normalized_name
JOIN skills target ON target.normalized_name = lower(x.canonical_name)
ON CONFLICT DO NOTHING;

INSERT INTO engineer_skill_declarations (engineer_id, raw_text, skill_id, source_row)
SELECT DISTINCT d.engineer_id, d.raw_text, target.skill_id, d.source_row
FROM engineer_skill_declarations d
JOIN skills source ON source.skill_id = d.skill_id
JOIN tmp_skill_expansions x ON x.alias_key = source.normalized_name
JOIN skills target ON target.normalized_name = lower(x.canonical_name)
WHERE NOT EXISTS (
    SELECT 1 FROM engineer_skill_declarations existing
    WHERE existing.engineer_id = d.engineer_id AND existing.raw_text = d.raw_text
      AND existing.skill_id = target.skill_id
      AND existing.source_row IS NOT DISTINCT FROM d.source_row
);

DELETE FROM task_role_skill_requirements q USING skills s, tmp_skill_expansions x
WHERE q.skill_id = s.skill_id AND s.normalized_name = x.alias_key;
DELETE FROM engineer_skill_declarations d USING skills s, tmp_skill_expansions x
WHERE d.skill_id = s.skill_id AND s.normalized_name = x.alias_key;
DELETE FROM engineer_skills es USING skills s, tmp_skill_expansions x
WHERE es.skill_id = s.skill_id AND s.normalized_name = x.alias_key;
DELETE FROM skills s USING tmp_skill_expansions x
WHERE s.normalized_name = x.alias_key
  AND NOT EXISTS (SELECT 1 FROM task_role_skill_requirements q WHERE q.skill_id = s.skill_id)
  AND NOT EXISTS (SELECT 1 FROM engineer_skill_declarations d WHERE d.skill_id = s.skill_id)
  AND NOT EXISTS (SELECT 1 FROM engineer_skills es WHERE es.skill_id = s.skill_id);
