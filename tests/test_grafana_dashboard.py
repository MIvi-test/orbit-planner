"""Статические проверки provisioned dashboard без запущенной Grafana."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "ops/grafana/dashboards/pi-planner-overview.json"


def test_overview_dashboard_is_wired_to_prometheus() -> None:
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panels = dashboard["panels"]
    expressions = [target["expr"] for panel in panels for target in panel.get("targets", [])]

    assert dashboard["uid"] == "pi-planner-overview"
    assert len(panels) >= 10
    assert len({panel["id"] for panel in panels}) == len(panels)
    assert all(panel["datasource"]["uid"] == "prometheus" for panel in panels)
    assert any('up{job="pi-planner"}' in expression for expression in expressions)
    assert any("pi_planner_plan_kpi_value" in expression for expression in expressions)
    kpi_panel = next(panel for panel in panels if panel["title"] == "KPI")
    assert "max by (kpi, sprint)" not in kpi_panel["targets"][0]["expr"]
    assert "{{kind}}" in kpi_panel["targets"][0]["legendFormat"]

    provider = (
        ROOT / "ops/grafana/provisioning/dashboards/pi-planner.yml"
    ).read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yaml").read_text(encoding="utf-8")
    assert "/etc/grafana/dashboards-json" in provider
    assert "./ops/grafana/dashboards:/etc/grafana/dashboards-json:ro" in compose
