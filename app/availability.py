"""Sprint-specific engineer availability for the active PI."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app import db, ingest


def set_rate(engineer_id: str, team_id: str, sprint_no: int, rate: Decimal | None,
             source_text: str) -> dict[str, Any]:
    engineer_id, team_id, source_text = engineer_id.strip(), team_id.strip(), source_text.strip()
    if not engineer_id or not team_id or sprint_no < 1:
        raise ingest.UploadError("укажите инженера, команду и спринт")
    if rate is not None and (not rate.is_finite() or rate < 0 or rate > 1 or not source_text):
        raise ingest.UploadError("ставка должна быть от 0 до 1; укажите источник изменения")
    with ingest.WRITE_LOCK, db.atomic_transaction():
        pi = ingest._pi()
        with db.transaction() as cur:
            cur.execute(
                """SELECT o.capacity_rate, e.total_capacity_rate FROM engineer_orbits o
                   JOIN engineers e USING (engineer_id)
                   WHERE o.engineer_id = %s AND o.team_id = %s""",
                (engineer_id, team_id),
            )
            orbit = cur.fetchone()
            if orbit is None:
                raise ingest.UploadError("орбита инженера не найдена")
            cur.execute("SELECT 1 FROM sprints WHERE pi_id = %s AND sprint_no = %s",
                        (pi["pi_id"], sprint_no))
            if cur.fetchone() is None:
                raise ingest.UploadError("спринт не входит в выбранный PI")
            if rate is None:
                cur.execute("""DELETE FROM engineer_orbit_availability
                               WHERE engineer_id = %s AND team_id = %s AND pi_id = %s AND sprint_no = %s""",
                            (engineer_id, team_id, pi["pi_id"], sprint_no))
            else:
                cur.execute(
                    """INSERT INTO engineer_orbit_availability
                           (engineer_id, team_id, pi_id, sprint_no, available_rate, source_text)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (engineer_id, team_id, pi_id, sprint_no) DO UPDATE SET
                           available_rate = EXCLUDED.available_rate,
                           source_text = EXCLUDED.source_text, recorded_at = now()""",
                    (engineer_id, team_id, pi["pi_id"], sprint_no, rate, source_text),
                )
            cur.execute(
                """SELECT SUM(COALESCE(a.available_rate, o.capacity_rate)) AS total_rate
                   FROM engineer_orbits o LEFT JOIN engineer_orbit_availability a
                     ON a.engineer_id = o.engineer_id AND a.team_id = o.team_id
                    AND a.pi_id = %s AND a.sprint_no = %s
                   WHERE o.engineer_id = %s""",
                (pi["pi_id"], sprint_no, engineer_id),
            )
            if Decimal(cur.fetchone()["total_rate"]) > Decimal(orbit["total_capacity_rate"]):
                raise ingest.UploadError("сумма ставок орбит превышает ставку инженера в этом спринте")
        plan = ingest.run_plan(min(ingest._last_sprint(pi["pi_id"]) + 1, int(pi["sprint_count"]) + 1))
    return {"engineer_id": engineer_id, "team_id": team_id, "sprint_no": sprint_no,
            "available_rate": str(rate) if rate is not None else None, "plan": plan}
