"""动态深度控制测试。

测试章节类型与深度策略的动态绑定。
"""

from __future__ import annotations

from baize_core.schemas.storm import (
    BACKGROUND_SECTION_DEPTH_POLICY,
    CORE_SECTION_DEPTH_POLICY,
    SUMMARY_SECTION_DEPTH_POLICY,
    DepthPolicy,
    SectionType,
    StormSectionSpec,
    get_depth_policy_for_section_type,
)


class TestSectionTypeDepthPolicies:
    """章节类型预设策略测试。"""

    def test_核心章节使用深挖策略(self) -> None:
        """核心章节（战略前景、力量部署）使用深挖策略。"""
        policy = get_depth_policy_for_section_type(SectionType.STRATEGIC_OUTLOOK)

        assert policy.min_sources >= 10
        assert policy.max_iterations >= 4
        assert policy.require_primary_sources is True

    def test_背景章节使用浅挖策略(self) -> None:
        """背景章节使用浅挖策略。"""
        policy = get_depth_policy_for_section_type(SectionType.BACKGROUND)

        assert policy.min_sources <= 5
        assert policy.max_iterations <= 2

    def test_摘要章节使用最小策略(self) -> None:
        """摘要章节使用最小策略。"""
        policy = get_depth_policy_for_section_type(SectionType.SUMMARY)

        assert policy.min_sources <= 2
        assert policy.max_iterations <= 1

    def test_默认章节使用默认策略(self) -> None:
        """未知章节类型使用默认策略。"""
        policy = get_depth_policy_for_section_type(SectionType.DEFAULT)

        default = DepthPolicy()
        assert policy.min_sources == default.min_sources
        assert policy.max_iterations == default.max_iterations


class TestStormSectionSpecDepthPolicy:
    """StormSectionSpec 有效深度策略测试。"""

    def test_自定义策略覆盖类型策略(self) -> None:
        """章节自定义策略优先于类型预设。"""
        custom_policy = DepthPolicy(min_sources=20, max_iterations=10)
        section = StormSectionSpec(
            title="自定义策略章节",
            question="测试问题",
            section_type=SectionType.BACKGROUND,
            depth_policy=custom_policy,
        )

        effective = section.get_effective_depth_policy()

        # 应该使用自定义策略，而非 BACKGROUND 预设
        assert effective.min_sources == 20
        assert effective.max_iterations == 10

    def test_默认策略时使用类型预设(self) -> None:
        """未自定义时使用类型预设策略。"""
        section = StormSectionSpec(
            title="核心章节",
            question="战略前景问题",
            section_type=SectionType.STRATEGIC_OUTLOOK,
            # 使用默认 depth_policy
        )

        effective = section.get_effective_depth_policy()

        # 应该使用 CORE_SECTION_DEPTH_POLICY
        assert effective.min_sources >= 10
        assert effective.require_primary_sources is True

    def test_力量部署章节深挖(self) -> None:
        """力量部署章节使用深挖策略。"""
        section = StormSectionSpec(
            title="力量与部署",
            question="目标区域的军事力量和部署情况",
            section_type=SectionType.FORCE_POSTURE,
        )

        effective = section.get_effective_depth_policy()

        assert effective.min_sources >= 10
        assert effective.max_iterations >= 4

    def test_观察指标章节中等深度(self) -> None:
        """观察指标章节使用默认深度。"""
        section = StormSectionSpec(
            title="观察指标",
            question="需要持续关注的指标",
            section_type=SectionType.WATCHLIST,
        )

        effective = section.get_effective_depth_policy()

        # WATCHLIST 没有预设，使用默认
        default = DepthPolicy()
        assert effective.min_sources == default.min_sources


class TestDepthPolicyPresets:
    """深度策略预设值测试。"""

    def test_核心策略参数正确(self) -> None:
        """核心章节深挖策略参数正确。"""
        assert CORE_SECTION_DEPTH_POLICY.min_sources >= 10
        assert CORE_SECTION_DEPTH_POLICY.max_iterations >= 4
        assert CORE_SECTION_DEPTH_POLICY.require_primary_sources is True

    def test_背景策略参数正确(self) -> None:
        """背景章节浅挖策略参数正确。"""
        assert BACKGROUND_SECTION_DEPTH_POLICY.min_sources <= 5
        assert BACKGROUND_SECTION_DEPTH_POLICY.max_iterations <= 2

    def test_摘要策略参数正确(self) -> None:
        """摘要章节最小策略参数正确。"""
        assert SUMMARY_SECTION_DEPTH_POLICY.min_sources <= 2
        assert SUMMARY_SECTION_DEPTH_POLICY.max_iterations <= 1
