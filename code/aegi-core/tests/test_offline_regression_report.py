# Author: msq

from __future__ import annotations

import json
from pathlib import Path

from aegi_core.regression.report import write_regression_report


def test_write_regression_report_outputs_json_and_text(tmp_path: Path) -> None:
    fixtures_root = Path(__file__).parent / "fixtures"
    out = write_regression_report(fixtures_root, tmp_path)

    report_json = json.loads((tmp_path / out["json"]).read_text(encoding="utf-8"))
    assert report_json["version"] == 1
    assert "thresholds" in report_json
    assert "fixtures" in report_json
    assert report_json["fixtures"]

    report_text = (tmp_path / out["text"]).read_text(encoding="utf-8")
    assert "anchor_locate_rate" in report_text
    assert "claim_grounding_rate" in report_text
