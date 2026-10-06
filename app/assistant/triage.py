"""Deterministic issue ranking over a pinned snapshot; no model-controlled actions."""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any
from uuid import UUID, uuid4

from app import db
from app.assistant import facts, snapshots

PAGE_SIZE = 10
POLICY = 'critical-problems-v1'
STEPS = {
    'data_quality': ('Сначала уточнить исходные данные', 'Подтвердите остаток работ и спорные оценки у владельца задачи.'),
    'cascade_shift': ('Сначала разобрать блокирующую зависимость', 'Проверьте состояние предшественников и актуальность связей задач.'),
    'deadline_miss': ('Затем разобрать риск срока инициативы', 'Проверьте перенесённые задачи и причины переноса; эффект мер требует сценарного расчёта.'),
    'role_deficit': ('Затем разобрать дефицит ресурсов', 'Сопоставьте ролевой спрос с доступностью; отдельно рассчитайте подходящие меры.'),
}


def previous(conversation_id: UUID, revision: int, snapshot_id: UUID) -> dict[str, Any] | None:
    row = db.query_one("SELECT payload FROM public.assistant_messages WHERE conversation_id = %s "
                       "AND context_revision = %s AND role = 'assistant' AND payload ? 'triage' "
                       "ORDER BY sequence_no DESC LIMIT 1", (conversation_id, revision))
    value = (row or {}).get('payload', {}).get('triage')
    return value if value and value.get('snapshot_id') == str(snapshot_id) and value.get('policy') == POLICY else None


def requested(question: str, saved: dict[str, Any] | None) -> bool:
    text = question.casefold()
    return bool(re.search(r'критич\w*.*(?:проблем|ошиб|риск)|(?:проблем|риск)\w*.*(?:критич|приорит|поряд)|с чего начать|порядок.*разбор', text)
                or saved and re.search(r'подроб|перв|втор|трет|следующ|ещ[её]|проблем\w*\s*(?:№|номер)?\s*\d|issue-', text))


def collect(snapshot_id: UUID) -> dict[str, Any]:
    inputs, plan, _, _ = snapshots.load(snapshot_id)
    tasks = {task.task_id: task for task in inputs.tasks}
    children: dict[str, set[str]] = defaultdict(set)
    for blocking, blocked, _gap in inputs.all_deps:
        children[blocking].add(blocked)
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for alert in plan.alerts:
        if alert.level not in {'red', 'orange', 'yellow', 'critical', 'error', 'warning'}:
            continue
        key = (alert.alert_type, alert.entity_type, alert.entity_id)
        item = groups.setdefault(key, {'kind': alert.alert_type, 'entity_type': alert.entity_type,
            'entity_id': alert.entity_id, 'level': alert.level, 'source_alerts': [], 'task_ids': set()})
        item['source_alerts'].append(facts.plain(alert))
        if alert.entity_type == 'task' and alert.entity_id in tasks:
            item['task_ids'].add(alert.entity_id)
        if alert.entity_type == 'initiative':
            item['task_ids'].update(t.task_id for t in tasks.values() if t.prodf_id == alert.entity_id)
        for field in ('tasks', 'deferred_tasks', 'affected_dependents'):
            item['task_ids'].update(t for t in alert.payload.get(field, []) if t in tasks)
    for task in tasks.values():
        if task.estimate_disputed or task.remaining_unknown:
            groups[('data_quality', 'task', task.task_id)] = {
                'kind': 'data_quality', 'entity_type': 'task', 'entity_id': task.task_id,
                'level': 'red', 'task_ids': {task.task_id}, 'source_alerts': [],
                'data_quality': {'estimate_disputed': task.estimate_disputed, 'remaining_unknown': task.remaining_unknown}}
    issues = []
    for key, item in groups.items():
        seen = set(item['task_ids'])
        pending = list(seen)
        while pending:
            for child in children.get(pending.pop(), ()):
                if child not in seen:
                    seen.add(child)
                    pending.append(child)
        item['affected_task_ids'] = sorted(seen & tasks.keys())
        item['task_ids'] = sorted(item['task_ids'])
        item['affected_count'] = len(item['affected_task_ids'])
        item['issue_id'] = 'issue-' + hashlib.sha256((str(snapshot_id) + json.dumps(key)).encode()).hexdigest()[:16]
        item['priority_reason'], item['first_step'] = STEPS.get(item['kind'],
            ('Проверить предупреждение после основных блокировок', 'Проверьте исходные данные предупреждения.'))
        item['category_order'] = {'data_quality': 0, 'cascade_shift': 1, 'deadline_miss': 2, 'role_deficit': 3}.get(item['kind'], 4)
        issues.append(item)
    issues.sort(key=lambda i: (i['category_order'], {'red': 0, 'critical': 0, 'error': 0, 'orange': 1}.get(i['level'], 2),
                               -i['affected_count'], i['entity_type'], i['entity_id'], i['issue_id']))
    for rank, item in enumerate(issues, 1):
        item['rank'] = rank
    return {'operation': 'critical_problems', 'snapshot_id': str(snapshot_id), 'policy': POLICY,
            'issues': issues, 'total': len(issues), 'complete_selection': True,
            'scope': 'Предупреждения прогона и задачи со спорным или неизвестным остатком. Зависимые задачи — потенциальный охват, не прогноз ущерба.'}


def answer(snapshot_id: UUID, question: str, saved: dict[str, Any] | None,
           revision: int, newer: bool | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report = collect(snapshot_id)
    text = question.casefold()
    start = 0
    detail = None
    if saved:
        match = re.search(r'(?:проблем\w*|пункт\w*|номер|№)\s*(?:№|номер)?\s*(\d+)', text)
        if match:
            detail = int(match[1])
        for word, rank in (('перв', 1), ('втор', 2), ('трет', 3), ('четверт', 4), ('пят', 5), ('шест', 6), ('седьм', 7), ('восьм', 8), ('девят', 9), ('десят', 10)):
            if word in text:
                detail = rank
                break
        by_id = re.search(r'issue-[0-9a-f]{16}', text)
        if by_id:
            detail = next((i['rank'] for i in report['issues'] if i['issue_id'] == by_id[0]), -1)
        if re.search(r'следующ|ещ[её]', text) and detail is None:
            start = saved.get('next_offset', 0)
    if detail is not None and not 1 <= detail <= report['total']:
        return ({'status': 'needs_clarification', 'summary': 'Такой проблемы нет в закреплённом списке.',
                 'explanation': '', 'clarification': 'Укажите номер проблемы из последнего списка.',
                 'fact_refs': [], 'recommendations': [], 'evidence_ids': [], 'entity_refs': [],
                 'context_revision': revision, 'newer_run_available': newer, 'limitations': []}, [])
    shown = report['issues'][detail - 1:detail] if detail else report['issues'][start:start + PAGE_SIZE]
    evidence_id = uuid4()
    # Values are rendered as plain Text in the UI; model prose never supplies these facts.
    rows = [{**i, 'source_alerts': i['source_alerts'][:5 if detail else 1],
             'task_ids': i['task_ids'][:20], 'affected_task_ids': i['affected_task_ids'][:20],
             'details_limited': len(i['source_alerts']) > (5 if detail else 1) or len(i['affected_task_ids']) > 20}
            for i in shown]
    result = {'status': 'answered', 'summary': f"Найдено проблем: {report['total']}. Показано: {len(shown)}.",
              'explanation': 'Порядок рассчитан по правилам: качество данных, зависимости, сроки, ресурсы; затем серьёзность и охват задач.',
              'clarification': '', 'fact_refs': [], 'recommendations': [], 'evidence_ids': [str(evidence_id)],
              'entity_refs': [], 'context_revision': revision, 'newer_run_available': newer,
              'limitations': [report['scope'], 'Эффект изменений не рассчитан; опубликованный план не изменён.'],
              'triage': {'snapshot_id': str(snapshot_id), 'policy': POLICY, 'total': report['total'],
                         'next_offset': saved.get('next_offset', 0) if detail and saved else min(start + len(shown), report['total']),
                         'issues': rows}}
    records = [{'evidence_id': evidence_id, 'source_type': 'snapshot', 'source_ref': str(snapshot_id), 'payload': report}]
    return result, records
