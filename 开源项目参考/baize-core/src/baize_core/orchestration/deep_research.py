"""Deep Research Loop 独立模块。

将递归深挖逻辑从 STORM 中抽取为独立可复用模块。

核心流程：
search -> read -> extract_evidence -> critic_review -> gap_detection -> 循环
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from baize_core.llm.runner import LlmRunner
from baize_core.orchestration.research_state import ResearchState
from baize_core.policy.depth import DepthController, DepthLevel, DepthState
from baize_core.schemas.evidence import Artifact, Chunk, Evidence
from baize_core.schemas.mcp_toolchain import (
    ArchiveUrlOutput,
    DocParseOutput,
    MetaSearchOutput,
    WebCrawlOutput,
)
from baize_core.schemas.policy import StageType
from baize_core.schemas.storm import DepthPolicy, StormIteration
from baize_core.storage.postgres import PostgresStore
from baize_core.tools.runner import ToolRunner

logger = logging.getLogger(__name__)

# 高质量欧美军事/新闻/智库网站域名白名单
PREFERRED_DOMAINS: set[str] = {
    # 主流新闻媒体
    "reuters.com", "www.reuters.com",
    "apnews.com", "www.apnews.com",
    "bbc.com", "www.bbc.com", "bbc.co.uk", "www.bbc.co.uk",
    "theguardian.com", "www.theguardian.com",
    "nytimes.com", "www.nytimes.com",
    "washingtonpost.com", "www.washingtonpost.com",
    "cnn.com", "www.cnn.com", "edition.cnn.com",
    "aljazeera.com", "www.aljazeera.com",
    "ft.com", "www.ft.com",
    "economist.com", "www.economist.com",
    "wsj.com", "www.wsj.com",
    "bloomberg.com", "www.bloomberg.com",
    "politico.com", "www.politico.com",
    "foreignpolicy.com", "www.foreignpolicy.com",
    "foreignaffairs.com", "www.foreignaffairs.com",
    # 军事/国防专业网站
    "defensenews.com", "www.defensenews.com",
    "janes.com", "www.janes.com",
    "defense.gov", "www.defense.gov",
    "militarytimes.com", "www.militarytimes.com",
    "airforcemag.com", "www.airforcemag.com",
    "navytimes.com", "www.navytimes.com",
    "armytimes.com", "www.armytimes.com",
    "marinecorpstimes.com", "www.marinecorpstimes.com",
    "breakingdefense.com", "www.breakingdefense.com",
    "nationaldefensemagazine.org", "www.nationaldefensemagazine.org",
    "defensepriorities.org", "www.defensepriorities.org",
    "defenseone.com", "www.defenseone.com",
    "thedrive.com", "www.thedrive.com",
    "warisboring.com",
    # 智库/研究机构
    "rand.org", "www.rand.org",
    "csis.org", "www.csis.org",
    "cfr.org", "www.cfr.org",
    "brookings.edu", "www.brookings.edu",
    "carnegieendowment.org", "www.carnegieendowment.org",
    "atlanticcouncil.org", "www.atlanticcouncil.org",
    "iiss.org", "www.iiss.org",
    "sipri.org", "www.sipri.org",
    "armscontrol.org", "www.armscontrol.org",
    "heritage.org", "www.heritage.org",
    "aei.org", "www.aei.org",
    "cato.org", "www.cato.org",
    "stimson.org", "www.stimson.org",
    "crisisgroup.org", "www.crisisgroup.org",
    "chathamhouse.org", "www.chathamhouse.org",
    "rusi.org", "www.rusi.org",
    # 政府/官方来源
    "state.gov", "www.state.gov",
    "whitehouse.gov", "www.whitehouse.gov",
    "congress.gov", "www.congress.gov",
    "nato.int", "www.nato.int",
    "un.org", "www.un.org",
    "iaea.org", "www.iaea.org",
    "europa.eu", "www.europa.eu",
    # 学术/研究
    "tandfonline.com", "www.tandfonline.com",
    "jstor.org", "www.jstor.org",
    "oxfordjournals.org",
    "cambridge.org", "www.cambridge.org",
    "nature.com", "www.nature.com",
    "sciencedirect.com", "www.sciencedirect.com",
    # 核武/核能专业
    "nukestrat.com", "www.nukestrat.com",
    "fas.org", "www.fas.org",
    "nti.org", "www.nti.org",
    "armscontrolwonk.com",
    "thebulletin.org", "www.thebulletin.org",
    # 中东专业
    "middleeasteye.net", "www.middleeasteye.net",
    "mei.edu", "www.mei.edu",
    "al-monitor.com", "www.al-monitor.com",
    "timesofisrael.com", "www.timesofisrael.com",
    "haaretz.com", "www.haaretz.com",
    "jpost.com", "www.jpost.com",
}

# 中文网站域名黑名单 (跳过这些域名)
BLOCKED_DOMAIN_PATTERNS: tuple[str, ...] = (
    ".cn",
    ".com.cn",
    "zhihu.com",
    "baidu.com",
    "weibo.com",
    "sina.com",
    "163.com",
    "qq.com",
    "sohu.com",
    "ifeng.com",
    "huanqiu.com",
    "chinadaily.com",
    "xinhuanet.com",
    "people.com.cn",
    "cctv.com",
    "bilibili.com",
    "douban.com",
    "toutiao.com",
    "lemon8-app.com",
    "jisho.org",
    "scribd.com",
)


def _is_preferred_domain(url: str) -> bool:
    """检查 URL 是否来自优选域名。

    Args:
        url: 要检查的 URL

    Returns:
        True 如果域名在白名单或不在黑名单中
    """
    try:
        domain = urlparse(url).netloc.lower()
        if not domain:
            return False

        # 检查是否在黑名单中
        for pattern in BLOCKED_DOMAIN_PATTERNS:
            if domain.endswith(pattern) or pattern in domain:
                logger.debug("跳过黑名单域名: %s", domain)
                return False

        # 如果在白名单中，优先处理
        if domain in PREFERRED_DOMAINS:
            return True

        # 检查是否是白名单域名的子域名
        for preferred in PREFERRED_DOMAINS:
            if domain.endswith("." + preferred):
                return True

        # 默认允许其他非黑名单域名
        return True
    except Exception:
        return False


def _sort_results_by_domain_preference(
    results: list[object],
) -> list[object]:
    """按域名优先级排序搜索结果。

    优先处理白名单域名，将黑名单域名排到最后（或直接过滤）。

    Args:
        results: 搜索结果列表

    Returns:
        排序后的结果列表
    """
    preferred = []
    other = []

    for result in results:
        url = getattr(result, "url", None)
        if url and _is_preferred_domain(url):
            domain = urlparse(url).netloc.lower()
            if domain in PREFERRED_DOMAINS or any(
                domain.endswith("." + p) for p in PREFERRED_DOMAINS
            ):
                preferred.append(result)
            else:
                other.append(result)

    # 白名单域名优先，其他域名其次
    return preferred + other


class CriticProtocol(Protocol):
    """Critic Agent 协议。"""

    async def review_evidence(
        self,
        evidence: list[Evidence],
        section_question: str,
        min_sources: int,
    ) -> CriticReviewResult:
        """审查证据并检测缺口。"""
        ...


@dataclass
class CriticReviewResult:
    """Critic 审查结果。"""

    is_sufficient: bool
    gaps: list[str]
    suggestions: list[str]
    gap_items: tuple[GapItem, ...] = ()
    coverage_score: float = 0.0  # 0.0 - 1.0
    confidence_score: float = 0.0  # 0.0 - 1.0


@dataclass(frozen=True)
class GapItem:
    """缺口条目（用于补洞循环）。"""

    description: str
    priority: int  # 1=最高优先级
    suggested_query: str


@dataclass
class ResearchIteration:
    """研究迭代记录。"""

    iteration_index: int
    query: str
    evidence_uids: list[str]
    gaps_detected: list[str]
    is_terminal: bool  # 是否为终止迭代


@dataclass
class SectionResearchResult:
    """章节研究结果。"""

    section_id: str
    iterations: list[ResearchIteration]
    evidence: list[Evidence]
    chunks: list[Chunk]
    artifacts: list[Artifact]
    gaps: list[str]
    coverage_score: float
    confidence_score: float
    depth_level_used: DepthLevel


@dataclass
class ResearchContext:
    """研究上下文。"""

    store: PostgresStore
    tool_runner: ToolRunner
    llm_runner: LlmRunner
    depth_controller: DepthController | None = None
    critic: CriticProtocol | None = None


@dataclass
class SectionSpec:
    """章节规格。"""

    section_id: str
    title: str
    question: str
    depth_policy: DepthPolicy


@dataclass
class DeepResearchConfig:
    """深度研究配置。"""

    # 是否启用动态深度调整
    enable_dynamic_depth: bool = True
    # 是否启用 Critic 审查
    enable_critic_review: bool = True
    # 覆盖度阈值（达到此值可提前终止）
    coverage_threshold: float = 0.8
    # 置信度阈值（达到此值可提前终止）
    confidence_threshold: float = 0.7
    # 缺口补充最大尝试次数
    max_gap_fill_attempts: int = 2
    # 只处理高优先级缺口（priority <= N）
    gap_priority_threshold: int = 2


class DeepResearchLoop:
    """深度研究循环。

    实现递归深挖逻辑：
    1. search: 根据查询搜索相关来源
    2. read: 抓取并解析网页内容
    3. extract_evidence: 提取证据
    4. critic_review: Critic 审查证据质量和覆盖度
    5. gap_detection: 检测证据缺口
    6. 循环: 根据缺口生成新查询，继续研究
    """

    def __init__(
        self,
        context: ResearchContext,
        config: DeepResearchConfig | None = None,
    ) -> None:
        """初始化深度研究循环。

        Args:
            context: 研究上下文
            config: 研究配置
        """
        self._context = context
        self._config = config or DeepResearchConfig()

    async def run_section_research(
        self,
        task_id: str,
        objective: str,
        section: SectionSpec,
    ) -> SectionResearchResult:
        """执行章节研究。

        Args:
            task_id: 任务 ID
            objective: 任务目标
            section: 章节规格

        Returns:
            章节研究结果
        """
        # 初始化研究状态和参数
        state, depth_state, min_sources, max_iterations = self._initialize_research(
            section
        )

        iterations: list[ResearchIteration] = []
        current_gaps: list[str] = []
        coverage_score = 0.0
        confidence_score = 0.0
        depth_level_used = DepthLevel.MODERATE

        for iteration in range(1, max_iterations + 1):
            # 执行单次迭代
            filtered_artifacts, filtered_chunks, filtered_evidence = (
                await self._run_single_iteration(
                    task_id=task_id,
                    objective=objective,
                    section=section,
                    iteration=iteration,
                    current_gaps=current_gaps,
                    state=state,
                )
            )

            # Critic 审查和补洞
            (
                gaps_detected,
                is_terminal,
                coverage_score,
                confidence_score,
                current_gaps,
            ) = await self._run_critic_review(
                task_id=task_id,
                section=section,
                min_sources=min_sources,
                state=state,
            )

            # 记录迭代
            iteration_record = ResearchIteration(
                iteration_index=iteration,
                query=self._build_query(objective, section, iteration, current_gaps),
                evidence_uids=[e.evidence_uid for e in filtered_evidence],
                gaps_detected=gaps_detected,
                is_terminal=is_terminal,
            )
            iterations.append(iteration_record)

            # 存储迭代记录
            await self._store_iteration_record(
                section=section,
                iteration=iteration,
                query=iteration_record.query,
                evidence_uids=iteration_record.evidence_uids,
            )

            logger.info(
                "迭代完成: section=%s, iteration=%d, evidence_count=%d, "
                "coverage=%.2f, confidence=%.2f, terminal=%s",
                section.section_id,
                iteration,
                state.evidence_count,
                coverage_score,
                confidence_score,
                is_terminal,
            )

            if is_terminal:
                break

            # 动态深度调整
            should_continue, depth_state, min_sources, depth_level_used = (
                self._adjust_depth_dynamically(
                    section=section,
                    depth_state=depth_state,
                    coverage_score=coverage_score,
                    confidence_score=confidence_score,
                )
            )
            if not should_continue:
                break

        # 构建最终结果
        return self._build_section_result(
            section=section,
            iterations=iterations,
            state=state,
            current_gaps=current_gaps,
            coverage_score=coverage_score,
            confidence_score=confidence_score,
            depth_level_used=depth_level_used,
            min_sources=min_sources,
        )

    def _initialize_research(
        self,
        section: SectionSpec,
    ) -> tuple[ResearchState, DepthState | None, int, int]:
        """初始化研究状态和参数。

        Args:
            section: 章节规格

        Returns:
            (state, depth_state, min_sources, max_iterations)
        """
        depth_policy = section.depth_policy
        min_sources = depth_policy.min_sources
        max_iterations = depth_policy.max_iterations
        depth_state: DepthState | None = None

        if (
            self._config.enable_dynamic_depth
            and self._context.depth_controller is not None
        ):
            initial_complexity = min(1.0, len(section.question) / 200)
            depth_state = self._context.depth_controller.initialize_state(
                complexity_score=initial_complexity,
            )
            min_sources, max_iterations = self._adjust_params_by_depth(
                depth_state.current_level,
                min_sources,
                max_iterations,
            )
            logger.info(
                "动态深度调整: section=%s, level=%s, min_sources=%d, max_iterations=%d",
                section.section_id,
                depth_state.current_level.value,
                min_sources,
                max_iterations,
            )

        state = ResearchState()
        return state, depth_state, min_sources, max_iterations

    async def _run_single_iteration(
        self,
        *,
        task_id: str,
        objective: str,
        section: SectionSpec,
        iteration: int,
        current_gaps: list[str],
        state: ResearchState,
    ) -> tuple[list[Artifact], list[Chunk], list[Evidence]]:
        """执行单次研究迭代。

        Args:
            task_id: 任务 ID
            objective: 任务目标
            section: 章节规格
            iteration: 迭代次数
            current_gaps: 当前缺口
            state: 研究状态

        Returns:
            (filtered_artifacts, filtered_chunks, filtered_evidence)
        """
        depth_policy = section.depth_policy

        query = self._build_query(
            objective=objective,
            section=section,
            iteration=iteration,
            gaps=current_gaps,
        )

        logger.info(
            "研究迭代: section=%s, iteration=%d, query=%s",
            section.section_id,
            iteration,
            query[:50],
        )

        # 执行搜索-抓取-解析链路
        new_artifacts, new_chunks, new_evidence = await self._run_research_chain(
            task_id=task_id,
            query=query,
            depth_policy=depth_policy,
        )

        # 去重过滤
        filtered_artifacts, filtered_chunks, filtered_evidence = self._dedupe(
            artifacts=new_artifacts,
            chunks=new_chunks,
            evidence_items=new_evidence,
            state=state,
            dedupe_by_domain=depth_policy.dedupe_by_domain,
        )

        # 存储结果
        if filtered_artifacts or filtered_chunks or filtered_evidence:
            await self._context.store.store_evidence_chain(
                artifacts=filtered_artifacts,
                chunks=filtered_chunks,
                evidence_items=filtered_evidence,
                claims=[],
            )

        # 更新状态
        state.merge_batch(
            artifacts=filtered_artifacts,
            chunks=filtered_chunks,
            evidence_items=filtered_evidence,
            dedupe_by_domain=depth_policy.dedupe_by_domain,
        )

        return filtered_artifacts, filtered_chunks, filtered_evidence

    async def _run_critic_review(
        self,
        *,
        task_id: str,
        section: SectionSpec,
        min_sources: int,
        state: ResearchState,
    ) -> tuple[list[str], bool, float, float, list[str]]:
        """执行 Critic 审查和补洞。

        Args:
            task_id: 任务 ID
            section: 章节规格
            min_sources: 最小来源数量
            state: 研究状态

        Returns:
            (gaps_detected, is_terminal, coverage_score, confidence_score, current_gaps)
        """
        gaps_detected: list[str] = []
        is_terminal = False
        coverage_score = 0.0
        confidence_score = 0.0
        current_gaps: list[str] = []

        if self._config.enable_critic_review and self._context.critic is not None:
            critic_result = await self._context.critic.review_evidence(
                evidence=state.evidence_list,
                section_question=section.question,
                min_sources=min_sources,
            )
            coverage_score = critic_result.coverage_score
            confidence_score = critic_result.confidence_score
            gaps_detected = list(critic_result.gaps)
            current_gaps = list(critic_result.suggestions)

            # 自动补洞循环
            resolved_gap_notes = await self._auto_supplement_on_gaps(
                task_id=task_id,
                section=section,
                state=state,
                critic_result=critic_result,
            )
            if resolved_gap_notes:
                gaps_detected.extend(resolved_gap_notes)

            # 补洞后重新评估
            critic_result = await self._context.critic.review_evidence(
                evidence=state.evidence_list,
                section_question=section.question,
                min_sources=min_sources,
            )
            coverage_score = critic_result.coverage_score
            confidence_score = critic_result.confidence_score
            gaps_detected = list(dict.fromkeys(gaps_detected + critic_result.gaps))
            current_gaps = list(critic_result.suggestions)

            # 检查是否可以提前终止
            if critic_result.is_sufficient:
                is_terminal = True
            elif (
                coverage_score >= self._config.coverage_threshold
                and confidence_score >= self._config.confidence_threshold
            ):
                is_terminal = True
        else:
            # 简单的来源数量检查
            if state.evidence_count >= min_sources:
                is_terminal = True
            coverage_score = min(1.0, state.evidence_count / min_sources)
            confidence_score = coverage_score

        return gaps_detected, is_terminal, coverage_score, confidence_score, current_gaps

    async def _store_iteration_record(
        self,
        *,
        section: SectionSpec,
        iteration: int,
        query: str,
        evidence_uids: list[str],
    ) -> None:
        """存储迭代记录。

        Args:
            section: 章节规格
            iteration: 迭代次数
            query: 查询
            evidence_uids: 证据 UID 列表
        """
        storm_iteration = StormIteration(
            section_id=section.section_id,
            iteration_index=iteration,
            query=query,
            evidence_uids=evidence_uids,
        )
        await self._context.store.store_storm_iterations([storm_iteration])
        await self._context.store.store_storm_section_evidence(
            section_uid=section.section_id,
            evidence_uids=evidence_uids,
        )

    def _adjust_depth_dynamically(
        self,
        *,
        section: SectionSpec,
        depth_state: DepthState | None,
        coverage_score: float,
        confidence_score: float,
    ) -> tuple[bool, DepthState | None, int, DepthLevel]:
        """动态调整深度参数。

        Args:
            section: 章节规格
            depth_state: 深度状态
            coverage_score: 覆盖度分数
            confidence_score: 置信度分数

        Returns:
            (should_continue, updated_depth_state, min_sources, depth_level_used)
        """
        depth_policy = section.depth_policy
        min_sources = depth_policy.min_sources
        depth_level_used = DepthLevel.MODERATE

        if not (
            self._config.enable_dynamic_depth
            and self._context.depth_controller is not None
            and depth_state is not None
        ):
            return True, depth_state, min_sources, depth_level_used

        # 更新指标
        depth_state = self._context.depth_controller.update_metrics(
            depth_state,
            coverage=coverage_score,
            confidence=confidence_score,
        )
        depth_state = self._context.depth_controller.increment_iteration(depth_state)

        # 评估调整
        adjustment = self._context.depth_controller.evaluate_adjustment(depth_state)
        if adjustment.should_adjust and adjustment.new_level is not None:
            depth_state = self._context.depth_controller.apply_adjustment(
                depth_state, adjustment
            )
            depth_level_used = depth_state.current_level
            new_min, _ = self._adjust_params_by_depth(
                depth_state.current_level,
                depth_policy.min_sources,
                depth_policy.max_iterations,
            )
            min_sources = new_min
            logger.info(
                "深度调整: section=%s, new_level=%s, reason=%s",
                section.section_id,
                depth_state.current_level.value,
                adjustment.reason,
            )

        if not adjustment.continue_research:
            logger.info(
                "深度控制器建议终止: section=%s, reason=%s",
                section.section_id,
                adjustment.reason,
            )
            return False, depth_state, min_sources, depth_level_used

        return True, depth_state, min_sources, depth_level_used

    def _build_section_result(
        self,
        *,
        section: SectionSpec,
        iterations: list[ResearchIteration],
        state: ResearchState,
        current_gaps: list[str],
        coverage_score: float,
        confidence_score: float,
        depth_level_used: DepthLevel,
        min_sources: int,
    ) -> SectionResearchResult:
        """构建章节研究结果。

        Args:
            section: 章节规格
            iterations: 迭代列表
            state: 研究状态
            current_gaps: 当前缺口
            coverage_score: 覆盖度分数
            confidence_score: 置信度分数
            depth_level_used: 使用的深度级别
            min_sources: 最小来源数量

        Returns:
            章节研究结果
        """
        final_gaps: list[str] = []
        if state.evidence_count < min_sources:
            final_gaps.append(
                f"来源数量不足（需要 {min_sources}，实际 {state.evidence_count}）"
            )
        if coverage_score < self._config.coverage_threshold:
            final_gaps.append(f"覆盖度不足（{coverage_score:.0%}）")
        final_gaps.extend(current_gaps)

        return SectionResearchResult(
            section_id=section.section_id,
            iterations=iterations,
            evidence=state.evidence_list,
            chunks=state.chunk_list,
            artifacts=state.artifact_list,
            gaps=final_gaps,
            coverage_score=coverage_score,
            confidence_score=confidence_score,
            depth_level_used=depth_level_used,
        )

    async def _auto_supplement_on_gaps(
        self,
        *,
        task_id: str,
        section: SectionSpec,
        state: ResearchState,
        critic_result: CriticReviewResult,
    ) -> list[str]:
        """Critic 缺口触发补洞循环（priority <= threshold）。

        Args:
            task_id: 任务 ID
            section: 章节规格
            state: 研究状态
            critic_result: Critic 审查结果

        Returns:
            已解决缺口的备注列表
        """
        if self._config.max_gap_fill_attempts <= 0:
            return []

        # 选择高优先级缺口
        high_priority = self._select_high_priority_gaps(critic_result)
        if not high_priority:
            return []

        unresolved_before = {item.description for item in high_priority}
        resolved_notes: list[str] = []
        depth_policy = section.depth_policy

        for _attempt in range(1, self._config.max_gap_fill_attempts + 1):
            # 逐个缺口执行补洞搜索
            new_found = await self._fill_gaps_batch(
                task_id=task_id,
                gaps=high_priority,
                depth_policy=depth_policy,
                state=state,
            )

            if not new_found:
                break

            # 重新评估缺口是否已解决
            high_priority, remaining, resolved = await self._recheck_gaps(
                section=section,
                unresolved_before=unresolved_before,
                state=state,
            )

            if resolved:
                resolved_notes.extend([f"[resolved] {item}" for item in resolved])
                unresolved_before = remaining

            if not high_priority:
                break

        return resolved_notes

    def _select_high_priority_gaps(
        self,
        critic_result: CriticReviewResult,
    ) -> list[GapItem]:
        """筛选高优先级缺口。

        Args:
            critic_result: Critic 审查结果

        Returns:
            高优先级缺口列表
        """
        gap_items = list(critic_result.gap_items)

        # 兼容：没有结构化缺口时，退化为前 N 个建议
        if not gap_items and critic_result.suggestions:
            gap_items = [
                GapItem(description=item, priority=1, suggested_query=item)
                for item in critic_result.suggestions[
                    : self._config.gap_priority_threshold
                ]
                if item.strip()
            ]

        return [
            item
            for item in gap_items
            if item.priority <= self._config.gap_priority_threshold
            and item.suggested_query.strip()
        ]

    async def _fill_gaps_batch(
        self,
        *,
        task_id: str,
        gaps: list[GapItem],
        depth_policy: DepthPolicy,
        state: ResearchState,
    ) -> bool:
        """批量填补缺口。

        Args:
            task_id: 任务 ID
            gaps: 缺口列表
            depth_policy: 深度策略
            state: 研究状态

        Returns:
            是否有新发现
        """
        new_found = False

        for gap in gaps:
            found = await self._fill_single_gap(
                task_id=task_id,
                gap=gap,
                depth_policy=depth_policy,
                state=state,
            )
            if found:
                new_found = True

        return new_found

    async def _fill_single_gap(
        self,
        *,
        task_id: str,
        gap: GapItem,
        depth_policy: DepthPolicy,
        state: ResearchState,
    ) -> bool:
        """填补单个缺口。

        Args:
            task_id: 任务 ID
            gap: 缺口条目
            depth_policy: 深度策略
            state: 研究状态

        Returns:
            是否有新发现
        """
        query = gap.suggested_query.strip()
        if not query:
            return False

        new_artifacts, new_chunks, new_evidence = await self._run_research_chain(
            task_id=task_id,
            query=query,
            depth_policy=depth_policy,
        )

        filtered_artifacts, filtered_chunks, filtered_evidence = self._dedupe(
            artifacts=new_artifacts,
            chunks=new_chunks,
            evidence_items=new_evidence,
            state=state,
            dedupe_by_domain=depth_policy.dedupe_by_domain,
        )

        if not (filtered_artifacts or filtered_chunks or filtered_evidence):
            return False

        # 存储结果
        await self._context.store.store_evidence_chain(
            artifacts=filtered_artifacts,
            chunks=filtered_chunks,
            evidence_items=filtered_evidence,
            claims=[],
        )

        # 更新状态
        state.merge_batch(
            artifacts=filtered_artifacts,
            chunks=filtered_chunks,
            evidence_items=filtered_evidence,
            dedupe_by_domain=depth_policy.dedupe_by_domain,
        )

        return True

    async def _recheck_gaps(
        self,
        *,
        section: SectionSpec,
        unresolved_before: set[str],
        state: ResearchState,
    ) -> tuple[list[GapItem], set[str], list[str]]:
        """重新检查缺口是否已解决。

        Args:
            section: 章节规格
            unresolved_before: 之前未解决的缺口
            state: 研究状态

        Returns:
            (high_priority_gaps, remaining, resolved)
        """
        critic = self._context.critic
        if critic is None:
            return [], set(), []

        recheck = await critic.review_evidence(
            evidence=state.evidence_list,
            section_question=section.question,
            min_sources=section.depth_policy.min_sources,
        )

        remaining = {
            item.description
            for item in recheck.gap_items
            if item.priority <= self._config.gap_priority_threshold
        }
        if not remaining:
            remaining = set(recheck.gaps)

        resolved = sorted(unresolved_before - remaining)

        high_priority = [
            item
            for item in recheck.gap_items
            if item.priority <= self._config.gap_priority_threshold
            and item.suggested_query.strip()
        ]

        return high_priority, remaining, resolved

    def _build_query(
        self,
        objective: str,
        section: SectionSpec,
        iteration: int,
        gaps: list[str],
    ) -> str:
        """构建搜索查询。

        Args:
            objective: 任务目标
            section: 章节规格
            iteration: 迭代次数
            gaps: 当前缺口

        Returns:
            搜索查询 (英文)
        """
        if iteration == 1:
            # 首次查询：使用任务目标和章节问题
            return f"{objective} {section.question}".strip()

        if gaps:
            # 后续查询：基于缺口补充
            gap_terms = " ".join(gaps[:2])  # 最多使用两个缺口
            return f"{objective} {section.title} {gap_terms}".strip()

        # 默认补充查询 (英文)
        return f"{objective} {section.title} additional sources".strip()

    def _adjust_params_by_depth(
        self,
        level: DepthLevel,
        base_min_sources: int,
        base_max_iterations: int,
    ) -> tuple[int, int]:
        """根据深度级别调整参数。

        Args:
            level: 深度级别
            base_min_sources: 基础来源数量
            base_max_iterations: 基础迭代次数

        Returns:
            (调整后的 min_sources, 调整后的 max_iterations)
        """
        if level == DepthLevel.SHALLOW:
            return max(1, base_min_sources // 2), max(1, base_max_iterations // 2)
        if level == DepthLevel.MODERATE:
            return base_min_sources, base_max_iterations
        if level == DepthLevel.DEEP:
            return int(base_min_sources * 1.5), int(base_max_iterations * 1.5)
        if level == DepthLevel.EXHAUSTIVE:
            return base_min_sources * 2, base_max_iterations * 2
        return base_min_sources, base_max_iterations

    async def _run_research_chain(
        self,
        task_id: str,
        query: str,
        depth_policy: DepthPolicy,
    ) -> tuple[list[Artifact], list[Chunk], list[Evidence]]:
        """执行搜索-抓取-解析链路。

        Args:
            task_id: 任务 ID
            query: 搜索查询
            depth_policy: 深度策略

        Returns:
            (artifacts, chunks, evidence)
        """
        # 1. 搜索
        search_payload: dict[str, object] = {
            "query": query,
            "max_results": depth_policy.max_results,
            "language": depth_policy.language,
            "time_range": depth_policy.time_range,
        }
        search_response = await self._context.tool_runner.run_mcp(
            tool_name="meta_search",
            tool_input=search_payload,
            stage=StageType.OBSERVE,
            task_id=task_id,
        )
        search_output = MetaSearchOutput.model_validate(search_response)

        artifacts: list[Artifact] = []
        chunks: list[Chunk] = []
        evidence_items: list[Evidence] = []

        # 2. 过滤并排序搜索结果（优先处理高质量欧美来源）
        filtered_results = [
            r for r in search_output.results if _is_preferred_domain(r.url)
        ]
        sorted_results = _sort_results_by_domain_preference(filtered_results)
        logger.info(
            "搜索结果过滤: 原始=%d, 过滤后=%d",
            len(search_output.results),
            len(sorted_results),
        )

        # 3. 对每个搜索结果执行抓取-归档-解析
        for result in sorted_results[: depth_policy.max_results]:
            try:
                # 抓取
                crawl_payload: dict[str, object] = {
                    "url": result.url,
                    "max_depth": depth_policy.max_depth,
                    "max_pages": depth_policy.max_pages,
                    "obey_robots_txt": depth_policy.obey_robots_txt,
                    "timeout_ms": depth_policy.timeout_ms,
                }
                crawl_response = await self._context.tool_runner.run_mcp(
                    tool_name="web_crawl",
                    tool_input=crawl_payload,
                    stage=StageType.OBSERVE,
                    task_id=task_id,
                )
                crawl_output = WebCrawlOutput.model_validate(crawl_response)
                crawl_output.artifact.origin_tool = "web_crawl"
                artifacts.append(crawl_output.artifact)
                await self._context.store.store_artifacts([crawl_output.artifact])

                # 直接使用 web_crawl 的 artifact 进行解析（跳过 archive_url）
                parse_payload: dict[str, object] = {
                    "artifact_uid": crawl_output.artifact.artifact_uid,
                    "chunk_size": depth_policy.chunk_size,
                    "chunk_overlap": depth_policy.chunk_overlap,
                }
                parse_response = await self._context.tool_runner.run_mcp(
                    tool_name="doc_parse",
                    tool_input=parse_payload,
                    stage=StageType.OBSERVE,
                    task_id=task_id,
                )
                parse_output = DocParseOutput.model_validate(parse_response)
                chunks.extend(parse_output.chunks)

                # 生成证据
                for chunk in parse_output.chunks:
                    evidence_items.append(
                        Evidence(
                            chunk_uid=chunk.chunk_uid,
                            source=result.source,
                            uri=result.url,
                            collected_at=crawl_output.artifact.fetched_at,
                            base_credibility=result.score,
                            tags=[f"source:{result.source}"],
                            summary=result.title,
                        )
                    )
            except Exception as exc:
                logger.warning(
                    "处理搜索结果失败: url=%s, error=%s",
                    result.url,
                    exc,
                )
                continue

        return artifacts, chunks, evidence_items

    def _dedupe(
        self,
        artifacts: list[Artifact],
        chunks: list[Chunk],
        evidence_items: list[Evidence],
        state: ResearchState,
        dedupe_by_domain: bool,
    ) -> tuple[list[Artifact], list[Chunk], list[Evidence]]:
        """去重过滤。

        Args:
            artifacts: 原始 artifacts
            chunks: 原始 chunks
            evidence_items: 原始 evidence
            state: 研究状态（包含已见集合）
            dedupe_by_domain: 是否按域名去重

        Returns:
            去重后的 (artifacts, chunks, evidence)
        """
        artifact_map = {a.artifact_uid: a for a in artifacts}
        chunk_map = {c.chunk_uid: c for c in chunks}

        filtered_evidence: list[Evidence] = []
        allowed_artifacts: dict[str, Artifact] = {}
        allowed_chunks: dict[str, Chunk] = {}

        for evidence in evidence_items:
            # URL 去重
            if state.is_url_seen(evidence.uri):
                continue

            # 域名去重
            if dedupe_by_domain and state.is_domain_seen(evidence.uri):
                continue

            # 获取关联的 chunk 和 artifact
            chunk = chunk_map.get(evidence.chunk_uid)
            if chunk is None:
                continue
            artifact = artifact_map.get(chunk.artifact_uid)
            if artifact is None:
                continue

            # 内容哈希去重
            if state.is_hash_seen(artifact.content_sha256):
                continue

            # 通过去重
            allowed_artifacts[artifact.artifact_uid] = artifact
            allowed_chunks[chunk.chunk_uid] = chunk
            filtered_evidence.append(evidence)

        return (
            list(allowed_artifacts.values()),
            list(allowed_chunks.values()),
            filtered_evidence,
        )


class SimpleCritic:
    """简单的 Critic 实现（基于规则）。"""

    async def review_evidence(
        self,
        evidence: list[Evidence],
        section_question: str,
        min_sources: int,
    ) -> CriticReviewResult:
        """审查证据。"""
        evidence_count = len(evidence)
        is_sufficient = evidence_count >= min_sources

        # 计算覆盖度（简单实现）
        coverage_score = min(1.0, evidence_count / max(1, min_sources))

        # 计算置信度（基于来源多样性）
        unique_domains = len(
            set(urlparse(e.uri or "").netloc for e in evidence if e.uri)
        )
        confidence_score = min(1.0, unique_domains / max(1, min_sources * 0.5))

        gaps: list[str] = []
        suggestions: list[str] = []
        gap_items: list[GapItem] = []

        if not is_sufficient:
            gaps.append(f"来源数量不足（需要 {min_sources}，实际 {evidence_count}）")
            suggestions.append("继续搜索更多来源")
            gap_items.append(
                GapItem(
                    description=gaps[-1],
                    priority=1,
                    suggested_query="expand search scope additional sources",
                )
            )

        if unique_domains < min_sources * 0.5:
            gaps.append("来源多样性不足")
            suggestions.append("搜索不同来源的信息")
            gap_items.append(
                GapItem(
                    description=gaps[-1],
                    priority=2,
                    suggested_query="search different sources diverse information",
                )
            )

        return CriticReviewResult(
            is_sufficient=is_sufficient,
            gaps=gaps,
            suggestions=suggestions,
            gap_items=tuple(gap_items),
            coverage_score=coverage_score,
            confidence_score=confidence_score,
        )
