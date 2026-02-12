# Author: msq
"""CAMEO 编码映射测试。"""

from __future__ import annotations

from aegi_core.infra.cameo import (
    CAMEO_CATEGORY,
    CAMEO_ROOT_LABELS,
    cameo_category,
    cameo_root_label,
    is_high_conflict,
)


def test_root_label() -> None:
    for code, label in CAMEO_ROOT_LABELS.items():
        assert cameo_root_label(code) == label


def test_category() -> None:
    for code, category in CAMEO_CATEGORY.items():
        assert cameo_category(code) == category


def test_is_high_conflict() -> None:
    for code in ["14", "15", "17", "18", "19", "20"]:
        assert is_high_conflict(code) is True
    for code in ["01", "02", "10", "11", "13"]:
        assert is_high_conflict(code) is False


def test_unknown_code() -> None:
    assert cameo_root_label("99") == "未知(99)"
    assert cameo_category("99") == "unknown"
    assert is_high_conflict("invalid") is False
