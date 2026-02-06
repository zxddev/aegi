"""STORM 研究契约。"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from baize_core.schemas.evidence import ReportReference


def generate_uid(prefix: str) -> str:
    """生成稳定前缀 UID。"""

    return f"{prefix}_{uuid4().hex}"


class StormTaskType(str, Enum):
    """任务模板类型。"""

    STRATEGIC_SITUATION = "strategic_situation"
    OPERATIONAL_ACTION = "operational_action"


class SectionType(str, Enum):
    """章节类型（用于动态深度控制）。
    不同章节类型有不同的深挖策略。
    """

    # 战略态势章节
    BACKGROUND = "background"  # 背景与关键事件
    KEY_ACTORS = "key_actors"  # 关键参与方
    STRATEGIC_OUTLOOK = "strategic_outlook"  # 战略前景（核心）
    WATCHLIST = "watchlist"  # 观察指标

    # 战役行动章节
    FORCE_POSTURE = "force_posture"  # 力量与部署（核心）
    TIMELINE = "timeline"  # 行动时间线
    ASSESSMENT = "assessment"  # 态势评估

    # 通用章节
    SUMMARY = "summary"  # 摘要
    EVIDENCE_TABLE = "evidence_table"  # 证据表
    DEFAULT = "default"  # 默认


class DepthPolicy(BaseModel):
    """深度研究策略。

    Attributes:
        min_sources: 最少来源数量
        max_iterations: 最大迭代次数
        max_results: 单次搜索最大结果数
        language: 搜索语言
        time_range: 时间范围
        max_depth: 抓取深度
        max_pages: 最大页数
        obey_robots_txt: 是否遵守 robots.txt
        timeout_ms: 超时时间
        chunk_size: 切片大小
        chunk_overlap: 切片重叠
        dedupe_by_domain: 是否按域名去重
        require_primary_sources: 是否要求一手来源
    """

    min_sources: int = Field(default=2, ge=1)
    max_iterations: int = Field(default=2, ge=1)
    max_results: int = Field(default=5, ge=1, le=50)
    # 默认使用英文搜索以获取欧美权威来源
    language: str = Field(default="en", min_length=1)
    time_range: str = Field(default="all", min_length=1)
    max_depth: int = Field(default=1, ge=1, le=5)
    max_pages: int = Field(default=10, ge=1, le=50)
    obey_robots_txt: bool = True
    timeout_ms: int = Field(default=30000, ge=1000, le=120000)
    chunk_size: int = Field(default=800, ge=100, le=4000)
    chunk_overlap: int = Field(default=120, ge=0, le=1000)
    dedupe_by_domain: bool = True
    require_primary_sources: bool = False


# =========================
# 报告模块化配置（新）
# =========================


class ReportModuleSpec(BaseModel):
    """报告模块定义（用于用户选择/覆盖）。"""

    module_id: str = Field(min_length=1)
    parent_id: str | None = None
    title: str = Field(min_length=1)
    description: str | None = None
    icon: str | None = None
    sort_order: int = 0
    is_active: bool = True
    # 用户可覆盖模块的核心问题（为空则使用模块预设）
    question: str | None = None
    # 用户可覆盖深度策略（为空则使用模块预设/章节默认）
    depth_policy: DepthPolicy = Field(default_factory=DepthPolicy)
    # 章节写作提示词配置（profile 名称）
    prompt_profile: str = Field(default="default", min_length=1)
    # 章节类型（影响深挖策略与后处理）
    section_type: SectionType = SectionType.DEFAULT
    coverage_questions: list[str] = Field(default_factory=list)


class ReportConfig(BaseModel):
    """报告配置（用户输入）。"""

    title: str | None = None
    selected_modules: list[ReportModuleSpec] = Field(default_factory=list)
    # 自由输入：由解析器转换为章节结构
    custom_sections: list[dict[str, object]] = Field(default_factory=list)
    user_context: str | None = None
    output_language: str = Field(default="zh", min_length=1)
    output_style: str = Field(default="professional", min_length=1)


# 预设深度策略：核心章节深挖
CORE_SECTION_DEPTH_POLICY = DepthPolicy(
    min_sources=5,
    max_iterations=2,
    max_results=8,
    require_primary_sources=True,
)

# 预设深度策略：背景章节浅挖
BACKGROUND_SECTION_DEPTH_POLICY = DepthPolicy(
    min_sources=2,
    max_iterations=1,
    max_results=5,
)

# 预设深度策略：摘要章节不挖
SUMMARY_SECTION_DEPTH_POLICY = DepthPolicy(
    min_sources=1,
    max_iterations=1,
    max_results=5,
)

# 章节类型到深度策略的映射
SECTION_TYPE_DEPTH_POLICIES: dict[SectionType, DepthPolicy] = {
    SectionType.STRATEGIC_OUTLOOK: CORE_SECTION_DEPTH_POLICY,
    SectionType.FORCE_POSTURE: CORE_SECTION_DEPTH_POLICY,
    SectionType.BACKGROUND: BACKGROUND_SECTION_DEPTH_POLICY,
    SectionType.KEY_ACTORS: BACKGROUND_SECTION_DEPTH_POLICY,
    SectionType.SUMMARY: SUMMARY_SECTION_DEPTH_POLICY,
    SectionType.EVIDENCE_TABLE: SUMMARY_SECTION_DEPTH_POLICY,
}


def get_depth_policy_for_section_type(section_type: SectionType) -> DepthPolicy:
    """根据章节类型获取深度策略。

    Args:
        section_type: 章节类型

    Returns:
        对应的深度策略，未找到则返回默认策略
    """
    return SECTION_TYPE_DEPTH_POLICIES.get(section_type, DepthPolicy())


class CoverageItem(BaseModel):
    """覆盖清单条目。"""

    item_id: str = Field(default_factory=lambda: generate_uid("cov"))
    question: str = Field(min_length=1)
    required: bool = True
    covered: bool = False


class StormSectionSpec(BaseModel):
    """大纲章节定义。

    Attributes:
        section_id: 章节 ID
        title: 章节标题
        question: 章节问题
        section_type: 章节类型（用于动态深度控制）
        coverage_item_ids: 关联的覆盖清单条目
        depth_policy: 深度策略（可覆盖默认值）
        module_id: 来源模块（用于动态模块组装）
        prompt_profile: 写作提示词配置名称
    """

    section_id: str = Field(default_factory=lambda: generate_uid("sec"))
    title: str = Field(min_length=1)
    question: str = Field(min_length=1)
    section_type: SectionType = SectionType.DEFAULT
    module_id: str | None = None
    prompt_profile: str = Field(default="default", min_length=1)
    coverage_item_ids: list[str] = Field(default_factory=list)
    depth_policy: DepthPolicy = Field(default_factory=DepthPolicy)

    def get_effective_depth_policy(self) -> DepthPolicy:
        """获取有效的深度策略。

        如果章节有自定义策略则使用，否则根据 section_type 获取预设策略。

        Returns:
            有效的深度策略
        """
        # 检查是否为默认策略
        default = DepthPolicy()
        if (
            self.depth_policy.min_sources != default.min_sources
            or self.depth_policy.max_iterations != default.max_iterations
        ):
            # 有自定义，使用自定义
            return self.depth_policy
        # 使用类型预设
        return get_depth_policy_for_section_type(self.section_type)


class StormOutline(BaseModel):
    """STORM 大纲。"""

    outline_uid: str = Field(default_factory=lambda: generate_uid("otl"))
    task_id: str = Field(min_length=1)
    task_type: StormTaskType
    objective: str = Field(min_length=1)
    report_config: ReportConfig | None = None
    coverage_checklist: list[CoverageItem] = Field(default_factory=list)
    sections: list[StormSectionSpec] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StormIteration(BaseModel):
    """章节研究迭代记录。"""

    iteration_id: str = Field(default_factory=lambda: generate_uid("it"))
    section_id: str = Field(min_length=1)
    iteration_index: int = Field(ge=1)
    query: str = Field(min_length=1)
    evidence_uids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StormResearchSection(BaseModel):
    """章节研究结果。"""

    section_id: str = Field(min_length=1)
    iterations: list[StormIteration] = Field(default_factory=list)
    evidence_uids: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class StormResearch(BaseModel):
    """研究汇总。"""

    outline_uid: str = Field(min_length=1)
    sections: list[StormResearchSection] = Field(default_factory=list)


class StormReportSection(BaseModel):
    """报告章节。"""

    section_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    markdown: str = Field(min_length=1)
    evidence_uids: list[str] = Field(default_factory=list)


class StormReport(BaseModel):
    """报告内容。"""

    report_uid: str = Field(default_factory=lambda: generate_uid("rpt"))
    outline_uid: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    report_type: StormTaskType
    title: str = Field(min_length=1)
    markdown: str = Field(min_length=1)
    sections: list[StormReportSection] = Field(default_factory=list)
    references: list[ReportReference] = Field(default_factory=list)
    conflict_notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
