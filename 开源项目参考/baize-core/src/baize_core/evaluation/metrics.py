"""评测指标计算。

实现架构设计文档第 6 节定义的评测指标，分为三类：
1. 抽取质量指标（实体/事件/地理位置）
2. 证据与一致性指标（引用/覆盖/冲突）
3. 运维与成本指标（成功率/封禁率/缓存/时延）
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from baize_core.evaluation.datasets.schema import (
    EvaluationCase,
    ExpectedEntity,
    ExpectedEvent,
    ExpectedLocation,
)
from baize_core.schemas.evidence import Claim, Evidence, Report
from baize_core.schemas.storm import CoverageItem


@dataclass
class MetricsResult:
    """指标计算结果。"""

    # 抽取质量指标
    entity_precision: float = 0.0
    entity_recall: float = 0.0
    entity_f1: float = 0.0
    event_precision: float = 0.0
    event_recall: float = 0.0
    event_f1: float = 0.0
    geolocation_match_rate: float = 0.0

    # 证据与一致性指标
    citation_hit_rate: float = 0.0
    coverage_score: float = 0.0
    source_diversity: int = 0
    fact_consistency: float = 0.0
    timeline_consistency: float = 0.0
    conflict_table_coverage: float = 0.0

    # 运维与成本指标
    deduplication_rate: float = 0.0
    crawl_success_rate: float = 0.0
    block_rate: float = 0.0
    cache_hit_rate: float = 0.0
    latency_seconds: float = 0.0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "extraction": {
                "entity_precision": self.entity_precision,
                "entity_recall": self.entity_recall,
                "entity_f1": self.entity_f1,
                "event_precision": self.event_precision,
                "event_recall": self.event_recall,
                "event_f1": self.event_f1,
                "geolocation_match_rate": self.geolocation_match_rate,
            },
            "evidence": {
                "citation_hit_rate": self.citation_hit_rate,
                "coverage_score": self.coverage_score,
                "source_diversity": self.source_diversity,
                "fact_consistency": self.fact_consistency,
                "timeline_consistency": self.timeline_consistency,
                "conflict_table_coverage": self.conflict_table_coverage,
            },
            "operations": {
                "deduplication_rate": self.deduplication_rate,
                "crawl_success_rate": self.crawl_success_rate,
                "block_rate": self.block_rate,
                "cache_hit_rate": self.cache_hit_rate,
                "latency_seconds": self.latency_seconds,
                "total_tokens": self.total_tokens,
                "estimated_cost_usd": self.estimated_cost_usd,
            },
        }


@dataclass
class ExtractedData:
    """抽取的数据（用于评测比对）。"""

    entity_names: list[str] = field(default_factory=list)
    entity_types: dict[str, str] = field(default_factory=dict)
    event_types: list[str] = field(default_factory=list)
    event_descriptions: list[str] = field(default_factory=list)
    locations: list[tuple[str, float | None, float | None]] = field(
        default_factory=list
    )


class MetricsCalculator:
    """指标计算器。"""

    def calculate_all(
        self,
        case: EvaluationCase,
        extracted: ExtractedData,
        evidence: Sequence[Evidence],
        claims: Sequence[Claim],
        report: Report | None,
        coverage_checklist: Sequence[CoverageItem] | None = None,
        tool_stats: dict[str, Any] | None = None,
    ) -> MetricsResult:
        """计算所有指标。

        Args:
            case: 评测用例
            extracted: 抽取的数据
            evidence: 证据列表
            claims: 声明列表
            report: 报告
            coverage_checklist: 覆盖清单
            tool_stats: 工具调用统计

        Returns:
            MetricsResult 指标结果
        """
        result = MetricsResult()

        # 抽取质量指标
        entity_metrics = self.entity_extraction_f1(
            case.expected_entities, extracted.entity_names, extracted.entity_types
        )
        result.entity_precision = entity_metrics["precision"]
        result.entity_recall = entity_metrics["recall"]
        result.entity_f1 = entity_metrics["f1"]

        event_metrics = self.event_extraction_f1(
            case.expected_events, extracted.event_types, extracted.event_descriptions
        )
        result.event_precision = event_metrics["precision"]
        result.event_recall = event_metrics["recall"]
        result.event_f1 = event_metrics["f1"]

        result.geolocation_match_rate = self.geolocation_match_rate(
            case.expected_locations, extracted.locations
        )

        # 证据与一致性指标
        result.citation_hit_rate = self.citation_hit_rate(claims, evidence)
        result.coverage_score = self.coverage_score(coverage_checklist)
        result.source_diversity = self.source_diversity(evidence)
        result.fact_consistency = self.fact_consistency(claims, evidence)
        result.timeline_consistency = self.timeline_consistency(evidence)
        result.conflict_table_coverage = self.conflict_table_coverage(evidence, report)

        # 运维与成本指标
        if tool_stats:
            result.deduplication_rate = self.deduplication_rate(tool_stats)
            result.crawl_success_rate = self.crawl_success_rate(tool_stats)
            result.block_rate = self.block_rate(tool_stats)
            result.cache_hit_rate = self.cache_hit_rate(tool_stats)
            result.latency_seconds = tool_stats.get("total_latency_seconds", 0.0)
            result.total_tokens = tool_stats.get("total_tokens", 0)
            result.estimated_cost_usd = tool_stats.get("estimated_cost_usd", 0.0)

        return result

    # ========== 抽取质量指标 ==========

    def entity_extraction_f1(
        self,
        expected: Sequence[ExpectedEntity],
        extracted_names: Sequence[str],
        extracted_types: dict[str, str],
    ) -> dict[str, float]:
        """计算实体抽取的 Precision/Recall/F1。

        Args:
            expected: 预期实体列表
            extracted_names: 抽取的实体名称
            extracted_types: 抽取的实体类型映射

        Returns:
            {"precision": float, "recall": float, "f1": float}
        """
        if not expected:
            return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

        extracted_set = set(extracted_names)
        true_positives = 0
        required_count = 0

        for exp in expected:
            if exp.required:
                required_count += 1
            # 检查名称或别名是否匹配
            matched = exp.name in extracted_set or any(
                alias in extracted_set for alias in exp.aliases
            )
            if matched:
                true_positives += 1

        # Precision: 抽取的实体中有多少是预期的
        precision = true_positives / len(extracted_names) if extracted_names else 0.0
        # Recall: 预期实体中有多少被抽取到
        recall = true_positives / len(expected) if expected else 0.0
        # F1
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        return {"precision": precision, "recall": recall, "f1": f1}

    def event_extraction_f1(
        self,
        expected: Sequence[ExpectedEvent],
        extracted_types: Sequence[str],
        extracted_descriptions: Sequence[str],
    ) -> dict[str, float]:
        """计算事件抽取的 Precision/Recall/F1。

        Args:
            expected: 预期事件列表
            extracted_types: 抽取的事件类型
            extracted_descriptions: 抽取的事件描述

        Returns:
            {"precision": float, "recall": float, "f1": float}
        """
        if not expected:
            return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

        extracted_type_set = set(extracted_types)
        true_positives = 0

        for exp in expected:
            # 按类型匹配
            if exp.event_type in extracted_type_set:
                true_positives += 1

        precision = true_positives / len(extracted_types) if extracted_types else 0.0
        recall = true_positives / len(expected) if expected else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        return {"precision": precision, "recall": recall, "f1": f1}

    def geolocation_match_rate(
        self,
        expected: Sequence[ExpectedLocation],
        extracted: Sequence[tuple[str, float | None, float | None]],
    ) -> float:
        """计算地理定位匹配率。

        Args:
            expected: 预期地点列表
            extracted: 抽取的地点列表 [(name, lat, lon), ...]

        Returns:
            匹配率 (0.0 - 1.0)
        """
        if not expected:
            return 1.0

        extracted_names = {name.lower() for name, _, _ in extracted}
        matched = 0

        for exp in expected:
            # 名称匹配（忽略大小写）
            if exp.name.lower() in extracted_names:
                matched += 1
                continue
            # 坐标匹配（如果有坐标）
            if exp.latitude is not None and exp.longitude is not None:
                for _, lat, lon in extracted:
                    if lat is not None and lon is not None:
                        distance = self._haversine_distance(
                            exp.latitude, exp.longitude, lat, lon
                        )
                        if distance <= exp.tolerance_km:
                            matched += 1
                            break

        return matched / len(expected)

    def _haversine_distance(
        self, lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """计算两点间的 Haversine 距离（公里）。"""
        import math

        R = 6371.0  # 地球半径（公里）
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    # ========== 证据与一致性指标 ==========

    def citation_hit_rate(
        self,
        claims: Sequence[Claim],
        evidence: Sequence[Evidence],
    ) -> float:
        """计算引用命中率。

        检查 claim 是否都能追溯到 evidence。

        Args:
            claims: 声明列表
            evidence: 证据列表

        Returns:
            命中率 (0.0 - 1.0)
        """
        if not claims:
            return 1.0

        evidence_uids = {e.evidence_uid for e in evidence}
        hit_count = 0

        for claim in claims:
            # 检查 claim 的 evidence_uids 是否存在于证据池中
            if claim.evidence_uids and any(
                uid in evidence_uids for uid in claim.evidence_uids
            ):
                hit_count += 1

        return hit_count / len(claims)

    def coverage_score(
        self,
        checklist: Sequence[CoverageItem] | None,
    ) -> float:
        """计算覆盖度（coverage checklist 达成率）。

        Args:
            checklist: 覆盖清单

        Returns:
            覆盖率 (0.0 - 1.0)
        """
        if not checklist:
            return 1.0

        covered_count = len([item for item in checklist if item.covered])
        return covered_count / len(checklist)

    def source_diversity(
        self,
        evidence: Sequence[Evidence],
    ) -> int:
        """计算来源多样性（独立域名数）。

        Args:
            evidence: 证据列表

        Returns:
            独立域名数量
        """
        domains: set[str] = set()
        for e in evidence:
            if e.uri:
                try:
                    parsed = urlparse(e.uri)
                    if parsed.netloc:
                        domains.add(parsed.netloc.lower())
                except Exception:
                    pass
            if e.source:
                domains.add(e.source.lower())

        return len(domains)

    def fact_consistency(
        self,
        claims: Sequence[Claim],
        evidence: Sequence[Evidence],
    ) -> float:
        """计算事实一致性。

        无冲突标记的 claim 比例。

        Args:
            claims: 声明列表
            evidence: 证据列表

        Returns:
            一致性比例 (0.0 - 1.0)
        """
        if not claims:
            return 1.0

        # 收集有冲突的证据 UID
        conflicted_evidence_uids: set[str] = set()
        for e in evidence:
            if e.conflict_types:
                conflicted_evidence_uids.add(e.evidence_uid)

        # 统计无冲突的 claim
        consistent_count = 0
        for claim in claims:
            has_conflict = any(
                uid in conflicted_evidence_uids for uid in claim.evidence_uids
            )
            if not has_conflict:
                consistent_count += 1

        return consistent_count / len(claims)

    def timeline_consistency(
        self,
        evidence: Sequence[Evidence],
    ) -> float:
        """计算时间线一致性。

        统计时间线矛盾的比例。

        Args:
            evidence: 证据列表

        Returns:
            一致性比例 (0.0 - 1.0)，1.0 表示完全一致
        """
        if not evidence:
            return 1.0

        # 统计有时间线冲突标记的证据
        timeline_conflict_count = 0
        for e in evidence:
            if e.conflict_types and "temporal" in e.conflict_types:
                timeline_conflict_count += 1

        contradiction_rate = timeline_conflict_count / len(evidence)
        return 1.0 - contradiction_rate

    def conflict_table_coverage(
        self,
        evidence: Sequence[Evidence],
        report: Report | None,
    ) -> float:
        """计算冲突表覆盖率。

        存在冲突的证据是否都被呈现在冲突表中。

        Args:
            evidence: 证据列表
            report: 报告

        Returns:
            覆盖率 (0.0 - 1.0)
        """
        # 统计有冲突的证据数量
        conflicted_evidence = [e for e in evidence if e.conflict_types]
        if not conflicted_evidence:
            return 1.0

        # 检查报告是否有冲突表
        if not report or not report.conflict_notes:
            return 0.0

        # 简单检查：冲突表非空即认为覆盖
        # 更精确的实现需要解析冲突表内容
        return 1.0 if report.conflict_notes else 0.0

    # ========== 运维与成本指标 ==========

    def deduplication_rate(self, stats: dict[str, Any]) -> float:
        """计算去重率。

        Args:
            stats: 工具统计

        Returns:
            去重率 (0.0 - 1.0)
        """
        total_urls = stats.get("total_urls", 0)
        unique_urls = stats.get("unique_urls", 0)
        if total_urls == 0:
            return 0.0
        return 1.0 - (unique_urls / total_urls)

    def crawl_success_rate(self, stats: dict[str, Any]) -> float:
        """计算抓取成功率。

        Args:
            stats: 工具统计

        Returns:
            成功率 (0.0 - 1.0)
        """
        total_crawls = stats.get("total_crawls", 0)
        successful_crawls = stats.get("successful_crawls", 0)
        if total_crawls == 0:
            return 1.0
        return successful_crawls / total_crawls

    def block_rate(self, stats: dict[str, Any]) -> float:
        """计算封禁率（403/429/验证码拦截）。

        Args:
            stats: 工具统计

        Returns:
            封禁率 (0.0 - 1.0)
        """
        total_crawls = stats.get("total_crawls", 0)
        blocked_crawls = stats.get("blocked_crawls", 0)
        if total_crawls == 0:
            return 0.0
        return blocked_crawls / total_crawls

    def cache_hit_rate(self, stats: dict[str, Any]) -> float:
        """计算缓存命中率。

        Args:
            stats: 工具统计

        Returns:
            缓存命中率 (0.0 - 1.0)
        """
        total_requests = stats.get("total_cache_requests", 0)
        cache_hits = stats.get("cache_hits", 0)
        if total_requests == 0:
            return 0.0
        return cache_hits / total_requests


def compute_metrics_for_case(
    case: EvaluationCase,
    evidence: Sequence[Evidence],
    claims: Sequence[Claim],
    report: Report | None,
    extracted: ExtractedData | None = None,
    coverage_checklist: Sequence[CoverageItem] | None = None,
    tool_stats: dict[str, Any] | None = None,
) -> MetricsResult:
    """计算单个用例的所有指标。

    便捷函数，封装 MetricsCalculator。

    Args:
        case: 评测用例
        evidence: 证据列表
        claims: 声明列表
        report: 报告
        extracted: 抽取的数据
        coverage_checklist: 覆盖清单
        tool_stats: 工具统计

    Returns:
        MetricsResult 指标结果
    """
    calculator = MetricsCalculator()
    if extracted is None:
        extracted = ExtractedData()
    return calculator.calculate_all(
        case=case,
        extracted=extracted,
        evidence=evidence,
        claims=claims,
        report=report,
        coverage_checklist=coverage_checklist,
        tool_stats=tool_stats,
    )
