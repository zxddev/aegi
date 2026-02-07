# Author: msq

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from aegi_core.regression.metrics import compute_metrics_for_fixture


P0_THRESHOLDS = {
    "anchor_locate_rate": 0.98,
    "claim_grounding_rate": 0.95,
}


def generate_regression_report(fixtures_root: Path) -> dict:
    manifest_path = fixtures_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list):
        fixtures = []

    per_fixture = []
    for item in fixtures:
        if not isinstance(item, dict):
            continue
        if "artifact" not in item:
            continue
        metrics = compute_metrics_for_fixture(fixtures_root, item)
        per_fixture.append(
            {
                "fixture_id": item.get("fixture_id"),
                "domain": item.get("domain"),
                "metrics": metrics,
            }
        )

    anchor_min = min(
        (f["metrics"]["anchor_locate_rate"] for f in per_fixture), default=0.0
    )
    grounding_min = min(
        (f["metrics"]["claim_grounding_rate"] for f in per_fixture), default=0.0
    )

    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "thresholds": dict(P0_THRESHOLDS),
        "fixtures": per_fixture,
        "summary": {
            "fixtures_count": len(per_fixture),
            "anchor_locate_rate_min": anchor_min,
            "claim_grounding_rate_min": grounding_min,
        },
    }


def render_regression_report_text(report: dict) -> str:
    summary = report.get("summary") if isinstance(report, dict) else None
    if not isinstance(summary, dict):
        summary = {}

    thresholds = report.get("thresholds") if isinstance(report, dict) else None
    if not isinstance(thresholds, dict):
        thresholds = {}

    lines = []
    lines.append("AEGI P0 Offline Regression Report")
    lines.append(f"fixtures_count: {summary.get('fixtures_count')}")
    lines.append(
        "anchor_locate_rate_min: "
        f"{summary.get('anchor_locate_rate_min')} (threshold {thresholds.get('anchor_locate_rate')})"
    )
    lines.append(
        "claim_grounding_rate_min: "
        f"{summary.get('claim_grounding_rate_min')} (threshold {thresholds.get('claim_grounding_rate')})"
    )
    return "\n".join(lines) + "\n"


def write_regression_report(fixtures_root: Path, out_dir: Path) -> dict[str, str]:
    report = generate_regression_report(fixtures_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_name = "report.json"
    text_name = "report.txt"

    (out_dir / json_name).write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / text_name).write_text(
        render_regression_report_text(report), encoding="utf-8"
    )

    return {"json": json_name, "text": text_name}
