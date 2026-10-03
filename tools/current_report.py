"""Reproducible input and database snapshot for the current PI model.

Run after loading the database: python tools/current_report.py [--output report.json]
The command reads one consistent PostgreSQL snapshot and never changes data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import __version__ as APP_VERSION  # noqa: E402
from app.db import connection  # noqa: E402
from app.planner import FORMULA_VERSION  # noqa: E402
from etl.config import ETL_VERSION, SOURCE_XLSX  # noqa: E402


def _revision() -> tuple[str, bool]:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        capture_output=True, check=False,
    )
    if result.returncode != 0:
        return "unknown", True
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
        text=True, capture_output=True, check=False,
    )
    return result.stdout.strip(), status.returncode != 0 or bool(status.stdout.strip())


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime, Decimal)):
        return str(value)
    raise TypeError(f"cannot encode {type(value).__name__}")


def build_report(source: Path) -> dict[str, object]:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    revision, dirty = _revision()
    with connection(read_only=True) as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")

        def one(sql: str) -> dict:
            cur.execute(sql)
            row = cur.fetchone()
            return dict(row) if row else {}

        batch = one("""
            SELECT batch_id, source_file, source_sha256, etl_version, pi_start,
                   row_counts FROM load_batches ORDER BY batch_id DESC LIMIT 1
        """)
        if not batch:
            raise RuntimeError("load_batches is empty: load the dataset first")
        if batch["source_sha256"] != digest:
            raise RuntimeError("Excel SHA256 differs from the loaded dataset")

        pi = one("""
            SELECT p.pi_id, p.start_date, p.end_date, p.sprint_count,
                   p.sprint_length_days, p.fte_hours_per_sprint,
                   f.factor AS pi_fund_factor,
                   (p.fte_hours_per_sprint * f.factor) AS fte_hours_per_pi
            FROM pi_periods p JOIN v_pi_fund_factor f USING (pi_id)
            ORDER BY p.pi_id LIMIT 1
        """)
        counts = one("""
            SELECT (SELECT count(*) FROM tasks) AS tasks,
                   (SELECT count(*) FROM engineers) AS engineers,
                   (SELECT count(*) FROM sprints) AS sprints,
                   (SELECT count(*) FROM task_role_estimates) AS role_estimates,
                   (SELECT count(*) FROM dq_issues) AS dq_issues
        """)
        run = one("""
            SELECT run_id, algorithm, params, status, as_of_sprint, created_at
            FROM plan_runs ORDER BY run_id DESC LIMIT 1
        """)
        return {
            "code_revision": revision,
            "working_tree_dirty": dirty,
            "app_version": APP_VERSION,
            "etl_version": ETL_VERSION,
            "formula_version": FORMULA_VERSION,
            "source": {"file": source.name, "sha256": digest},
            "loaded_batch": batch,
            "pi": pi,
            "counts": counts,
            "latest_run": run or None,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / SOURCE_XLSX)
    parser.add_argument("--output", type=Path, help="write JSON to this file")
    args = parser.parse_args()
    report = build_report(args.dataset.resolve())
    encoded = json.dumps(report, ensure_ascii=False, indent=2, default=_json_default) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
