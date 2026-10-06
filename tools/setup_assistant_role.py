"""Provision the worker role using an administrator DSN; never print credentials."""
from __future__ import annotations
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from psycopg import sql
from app import db

ROLE = 'pi_assistant_worker'
READ = ('assistant_dataset_generations', 'assistant_input_snapshots', 'assistant_prompt_versions',
        'assistant_provider_profiles', 'assistant_conversations', 'assistant_context_revisions',
        'assistant_messages', 'assistant_jobs', 'assistant_evidence', 'assistant_recommendations',
        'assistant_scenario_results', 'assistant_kb_embedding_spaces', 'assistant_kb_revisions',
        'assistant_kb_documents', 'assistant_kb_chunks', 'assistant_kb_chunk_embeddings',
        'assistant_kb_revision_documents')
INSERT = ('assistant_messages', 'assistant_evidence', 'assistant_scenario_results', 'assistant_recommendations',
          'assistant_kb_embedding_spaces', 'assistant_kb_revisions', 'assistant_kb_documents',
          'assistant_kb_chunks', 'assistant_kb_chunk_embeddings', 'assistant_kb_revision_documents')
UPDATE = {
    'assistant_jobs': ('status', 'attempt_count', 'lease_until', 'updated_at', 'result_payload', 'error_payload'),
    'assistant_conversations': ('updated_at',), 'assistant_recommendations': ('freshness',),
    'assistant_kb_documents': ('status',), 'assistant_kb_revisions': ('active',),
}


def setup() -> None:
    password = os.environ.get('ASSISTANT_DB_PASSWORD', '')
    if len(password) < 32:
        raise ValueError('ASSISTANT_DB_PASSWORD must contain at least 32 characters')
    role = sql.Identifier(ROLE)
    with db.transaction(operation='assistant_role_setup') as cur:
        cur.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', (ROLE,))
        if cur.fetchone() is None:
            cur.execute(sql.SQL('CREATE ROLE {} LOGIN').format(role))
        cur.execute(sql.SQL('ALTER ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD {}').format(role, sql.Literal(password)))
        cur.execute(sql.SQL('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {}').format(role))
        cur.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(role))
        for table in READ:
            cur.execute(sql.SQL('GRANT SELECT ON public.{} TO {}').format(sql.Identifier(table), role))
        cur.execute(sql.SQL('GRANT SELECT (user_id, name, role, active) ON public.app_users TO {}').format(role))
        for table in INSERT:
            cur.execute(sql.SQL('GRANT INSERT ON public.{} TO {}').format(sql.Identifier(table), role))
        for table, columns in UPDATE.items():
            cur.execute(sql.SQL('GRANT UPDATE ({}) ON public.{} TO {}').format(
                sql.SQL(', ').join(map(sql.Identifier, columns)), sql.Identifier(table), role))
    print('assistant database role configured')


if __name__ == '__main__':
    setup()
