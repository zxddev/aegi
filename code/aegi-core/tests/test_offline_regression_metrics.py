# Author: msq
from __future__ import annotations

import json
from pathlib import Path

from aegi_core.regression.metrics import compute_metrics_for_fixture


def test_offline_regression_metrics_meet_p0_thresholds() -> None:
    fixtures_root = Path(__file__).parent / "fixtures"
    manifest_path = fixtures_root / "manifest.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixtures = manifest["fixtures"]
    assert fixtures

    for item in fixtures:
        metrics = compute_metrics_for_fixture(fixtures_root, item)
        assert metrics["anchor_locate_rate"] >= 0.98
        assert metrics["claim_grounding_rate"] >= 0.95
