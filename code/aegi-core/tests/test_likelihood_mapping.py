"""似然映射测试 — 5 个测试。"""

from __future__ import annotations

import pytest

from aegi_core.services.bayesian_ach import relation_strength_to_likelihood


def test_support_range():
    """support strength 0→1 映射到 0.55→0.95。"""
    assert abs(relation_strength_to_likelihood("support", 0.0) - 0.55) < 1e-10
    assert abs(relation_strength_to_likelihood("support", 1.0) - 0.95) < 1e-10
    # 中点
    assert abs(relation_strength_to_likelihood("support", 0.5) - 0.75) < 1e-10


def test_contradict_range():
    """contradict strength 0→1 映射到 0.45→0.05。"""
    assert abs(relation_strength_to_likelihood("contradict", 0.0) - 0.45) < 1e-10
    assert abs(relation_strength_to_likelihood("contradict", 1.0) - 0.05) < 1e-10
    assert abs(relation_strength_to_likelihood("contradict", 0.5) - 0.25) < 1e-10


def test_irrelevant_fixed():
    """irrelevant 不管 strength 多少都返回 0.50。"""
    for s in [0.0, 0.25, 0.5, 0.75, 1.0]:
        assert abs(relation_strength_to_likelihood("irrelevant", s) - 0.50) < 1e-10


def test_clamp_out_of_range():
    """strength < 0 或 > 1 会被 clamp。"""
    # strength=-0.5 应 clamp 到 0
    assert abs(relation_strength_to_likelihood("support", -0.5) - 0.55) < 1e-10
    # strength=1.5 应 clamp 到 1
    assert abs(relation_strength_to_likelihood("support", 1.5) - 0.95) < 1e-10


def test_custom_range():
    """自定义 support/contradict 范围生效。"""
    lk = relation_strength_to_likelihood(
        "support",
        1.0,
        support_range=(0.6, 0.9),
    )
    assert abs(lk - 0.9) < 1e-10

    lk2 = relation_strength_to_likelihood(
        "contradict",
        1.0,
        contradict_range=(0.1, 0.4),
    )
    assert abs(lk2 - 0.1) < 1e-10
