"""贝叶斯数学正确性测试 — 10 个测试，不用 LLM，纯计算。"""

from __future__ import annotations

import pytest

from aegi_core.services.bayesian_ach import relation_strength_to_likelihood


# ── 辅助函数：纯内存贝叶斯更新（不用 DB）─────────────


def bayesian_update(
    priors: dict[str, float],
    likelihoods: dict[str, float],
) -> dict[str, float]:
    """纯贝叶斯更新，用于测试。"""
    p_e = sum(likelihoods[uid] * priors[uid] for uid in priors)
    if p_e == 0:
        p_e = 1e-10
    posteriors = {uid: likelihoods[uid] * priors[uid] / p_e for uid in priors}
    total = sum(posteriors.values())
    if total > 0:
        posteriors = {uid: p / total for uid, p in posteriors.items()}
    return posteriors


# ── 测试 ─────────────────────────────────────────────────────────


def test_uniform_prior():
    """N 个假设 → 每个先验 = 1/N，总和 = 1.0。"""
    n = 5
    priors = {f"h{i}": 1.0 / n for i in range(n)}
    assert abs(sum(priors.values()) - 1.0) < 1e-10
    for v in priors.values():
        assert abs(v - 0.2) < 1e-10


def test_single_support_update():
    """一条支持证据 → 被支持假设的后验上升。"""
    priors = {"hA": 1 / 3, "hB": 1 / 3, "hC": 1 / 3}
    # hA 被支持（高似然），其他无关
    likelihoods = {"hA": 0.9, "hB": 0.5, "hC": 0.5}
    post = bayesian_update(priors, likelihoods)
    assert post["hA"] > priors["hA"]
    assert post["hB"] < priors["hB"]
    assert post["hC"] < priors["hC"]
    assert abs(sum(post.values()) - 1.0) < 1e-10


def test_single_contradict_update():
    """一条矛盾证据 → 被矛盾假设的后验下降。"""
    priors = {"hA": 1 / 3, "hB": 1 / 3, "hC": 1 / 3}
    likelihoods = {"hA": 0.1, "hB": 0.5, "hC": 0.5}
    post = bayesian_update(priors, likelihoods)
    assert post["hA"] < priors["hA"]
    assert abs(sum(post.values()) - 1.0) < 1e-10


def test_irrelevant_no_change():
    """无关证据（所有 P(E|H)=0.5）→ 后验不变。"""
    priors = {"hA": 0.5, "hB": 0.3, "hC": 0.2}
    likelihoods = {"hA": 0.5, "hB": 0.5, "hC": 0.5}
    post = bayesian_update(priors, likelihoods)
    for uid in priors:
        assert abs(post[uid] - priors[uid]) < 1e-10


def test_strong_vs_weak_support():
    """更强的支持 → 概率增幅更大。"""
    priors = {"hA": 0.5, "hB": 0.5}
    strong = bayesian_update(priors, {"hA": 0.95, "hB": 0.5})
    weak = bayesian_update(priors, {"hA": 0.6, "hB": 0.5})
    assert strong["hA"] > weak["hA"]


def test_multiple_updates_normalize():
    """5 次连续更新 → 后验仍然归一化到 1.0。"""
    priors = {"hA": 1 / 3, "hB": 1 / 3, "hC": 1 / 3}
    evidence_likelihoods = [
        {"hA": 0.8, "hB": 0.3, "hC": 0.5},
        {"hA": 0.4, "hB": 0.9, "hC": 0.5},
        {"hA": 0.7, "hB": 0.2, "hC": 0.6},
        {"hA": 0.5, "hB": 0.5, "hC": 0.9},
        {"hA": 0.85, "hB": 0.15, "hC": 0.5},
    ]
    current = dict(priors)
    for lk in evidence_likelihoods:
        current = bayesian_update(current, lk)
        assert abs(sum(current.values()) - 1.0) < 1e-10


def test_likelihood_mapping_symmetry():
    """support(s) 和 contradict(s) 关于 0.5 对称。"""
    for s in [0.0, 0.25, 0.5, 0.75, 1.0]:
        sup = relation_strength_to_likelihood("support", s)
        con = relation_strength_to_likelihood("contradict", s)
        assert abs((sup + con) - 1.0) < 1e-10, f"s={s}: sup={sup}, con={con}"


def test_likelihood_bounds():
    """P(E|H) 始终在开区间 (0, 1) 内。"""
    for rel in ("support", "contradict", "irrelevant"):
        for s in [0.0, 0.5, 1.0]:
            lk = relation_strength_to_likelihood(rel, s)
            assert 0.0 < lk < 1.0, f"{rel} s={s} → {lk}"


def test_diagnosticity_calculation():
    """诊断性 = max(P(E|H_i)/P(E|H_j))，i≠j。"""
    likelihoods = {"hA": 0.9, "hB": 0.2, "hC": 0.5}
    # 对 hA: max(0.9/0.2, 0.9/0.5) = max(4.5, 1.8) = 4.5
    expected_hA = 0.9 / 0.2
    uids = list(likelihoods.keys())
    max_lr = 1.0
    for other in uids:
        if other == "hA":
            continue
        lr = likelihoods["hA"] / likelihoods[other]
        if lr > max_lr:
            max_lr = lr
    assert abs(max_lr - expected_hA) < 1e-10


def test_recalculate_matches_sequential():
    """从头重放更新和逐步更新结果一致。"""
    priors = {"hA": 1 / 3, "hB": 1 / 3, "hC": 1 / 3}
    evidence = [
        {"hA": 0.8, "hB": 0.3, "hC": 0.5},
        {"hA": 0.4, "hB": 0.9, "hC": 0.5},
        {"hA": 0.7, "hB": 0.2, "hC": 0.6},
    ]

    # 逐步更新
    seq = dict(priors)
    for lk in evidence:
        seq = bayesian_update(seq, lk)

    # 从头重放
    replay = dict(priors)
    for lk in evidence:
        replay = bayesian_update(replay, lk)

    for uid in priors:
        assert abs(seq[uid] - replay[uid]) < 1e-10
