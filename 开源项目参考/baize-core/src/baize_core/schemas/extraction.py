"""抽取输出 Schema。

用于 LLM 结构化输出的抽取结果定义。
这些 schema 与存储层 schema 的区别：
- 不包含 UID（由系统生成）
- 不强制要求 evidence_uids（抽取时尚未关联）
- 字段更宽松，便于 LLM 输出
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ExtractedEntityType(str, Enum):
    """抽取实体类型。"""

    ACTOR = "Actor"
    """国家/地区、联盟与国际组织、非国家行为体。"""

    ORGANIZATION = "Organization"
    """政府机构、军队/军种、部委/执法机构、智库、媒体与企业。"""

    UNIT = "Unit"
    """部队单位（层级、隶属、驻地、公开装备线索、公开编制线索）。"""

    FACILITY = "Facility"
    """基地/机场/港口/训练场/雷达站/仓储等设施。"""

    EQUIPMENT = "Equipment"
    """装备/平台/武器系统。"""

    GEOGRAPHY = "Geography"
    """地点/区域/海域空域。"""

    LEGAL_INSTRUMENT = "LegalInstrument"
    """条约、决议、法律与制裁措施。"""

    PERSON = "Person"
    """个人（政治人物、军事将领等）。"""

    OTHER = "Other"
    """其他类型。"""


class ExtractedEventType(str, Enum):
    """抽取事件类型。"""

    STATEMENT = "Statement"
    """声明、讲话、通报。"""

    DIPLOMATIC = "Diplomatic"
    """访问、峰会、谈判、协议。"""

    ECONOMIC = "Economic"
    """制裁、禁运、军费与军贸。"""

    MILITARY_POSTURE = "MilitaryPosture"
    """增兵/撤离、基地建设、战备调整。"""

    INCIDENT = "Incident"
    """摩擦、对峙、危机与升级事件。"""

    EXERCISE = "Exercise"
    """演训与联合演习。"""

    DEPLOYMENT = "Deployment"
    """兵力/平台部署变化。"""

    MOVEMENT = "Movement"
    """舰机活动、跨区机动。"""

    ENGAGEMENT = "Engagement"
    """交战/打击/拦截等事件。"""

    C2_CHANGE = "C2Change"
    """指挥架构或指挥关系变化。"""

    SUPPORT_LOGISTICS = "SupportLogistics"
    """补给、后装、人员轮换等支援事件。"""

    FACILITY_ACTIVITY = "FacilityActivity"
    """设施启用/扩建、进出港/起降活动。"""

    OTHER = "Other"
    """其他类型。"""


class ExtractedGeoLocation(BaseModel):
    """抽取的地理位置。

    LLM 抽取时可能无法提供精确坐标，
    因此支持多种位置表示方式。
    """

    name: str | None = Field(default=None, description="地点名称")
    country: str | None = Field(default=None, description="国家/地区")
    region: str | None = Field(default=None, description="行政区域")
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0, description="纬度")
    longitude: float | None = Field(
        default=None, ge=-180.0, le=180.0, description="经度"
    )


class ExtractedEntity(BaseModel):
    """从文本中抽取的实体。

    用于 LLM 结构化输出，字段相对宽松。
    后续处理会转换为存储层的 Entity 对象。
    """

    name: str = Field(min_length=1, description="实体名称")
    entity_type: ExtractedEntityType = Field(description="实体类型")
    description: str | None = Field(default=None, description="实体描述")
    aliases: list[str] = Field(default_factory=list, description="别名列表")
    location: ExtractedGeoLocation | None = Field(default=None, description="地理位置")
    attributes: dict[str, str] = Field(
        default_factory=dict,
        description="额外属性（键值对）",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="抽取置信度",
    )
    source_text: str | None = Field(default=None, description="来源文本片段")


class ExtractedTimeRange(BaseModel):
    """抽取的时间范围。"""

    start: datetime | None = Field(default=None, description="开始时间")
    end: datetime | None = Field(default=None, description="结束时间")
    is_approximate: bool = Field(default=False, description="是否为近似时间")
    raw_text: str | None = Field(default=None, description="原始时间文本")


class ExtractedEventParticipant(BaseModel):
    """抽取的事件参与方。"""

    name: str = Field(min_length=1, description="参与方名称")
    role: str = Field(default="participant", description="参与角色")
    entity_type: ExtractedEntityType | None = Field(
        default=None,
        description="实体类型（如果已知）",
    )


class ExtractedEvent(BaseModel):
    """从文本中抽取的事件。

    用于 LLM 结构化输出，字段相对宽松。
    后续处理会转换为存储层的 Event 对象。
    """

    summary: str = Field(min_length=1, description="事件摘要")
    event_type: ExtractedEventType = Field(description="事件类型")
    time_range: ExtractedTimeRange | None = Field(default=None, description="时间范围")
    location: ExtractedGeoLocation | None = Field(default=None, description="地理位置")
    participants: list[ExtractedEventParticipant] = Field(
        default_factory=list,
        description="参与方列表",
    )
    tags: list[str] = Field(default_factory=list, description="标签")
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="抽取置信度",
    )
    source_text: str | None = Field(default=None, description="来源文本片段")


class EntityExtractionResult(BaseModel):
    """实体抽取结果。

    批量返回从文本中抽取的所有实体。
    """

    entities: list[ExtractedEntity] = Field(
        default_factory=list,
        description="抽取的实体列表",
    )
    source_summary: str | None = Field(
        default=None,
        description="来源文本摘要",
    )


class EventExtractionResult(BaseModel):
    """事件抽取结果。

    批量返回从文本中抽取的所有事件。
    """

    events: list[ExtractedEvent] = Field(
        default_factory=list,
        description="抽取的事件列表",
    )
    source_summary: str | None = Field(
        default=None,
        description="来源文本摘要",
    )


class ExtractedRelationType(str, Enum):
    """抽取的关系类型。"""

    BELONGS_TO = "BELONGS_TO"
    """隶属关系（Unit→Organization）。"""

    LOCATED_AT = "LOCATED_AT"
    """位置关系（Unit→Facility, Entity→Geography）。"""

    OPERATES = "OPERATES"
    """运用关系（Unit→Equipment）。"""

    ALLIED_WITH = "ALLIED_WITH"
    """同盟关系（Actor→Actor）。"""

    HOSTILE_TO = "HOSTILE_TO"
    """敌对关系（Actor→Actor）。"""

    COOPERATES_WITH = "COOPERATES_WITH"
    """合作关系（Organization→Organization）。"""

    PARTICIPATES_IN = "PARTICIPATES_IN"
    """参与关系（Entity→Event）。"""

    CAUSED_BY = "CAUSED_BY"
    """因果关系（Event→Event）。"""

    FOLLOWS = "FOLLOWS"
    """时序关系（Event→Event）。"""

    RELATED_TO = "RELATED_TO"
    """通用关联。"""


class ExtractedRelation(BaseModel):
    """从文本中抽取的实体间关系。

    用于 LLM 结构化输出，描述两个实体之间的关系。
    """

    source_name: str = Field(min_length=1, description="源实体名称")
    target_name: str = Field(min_length=1, description="目标实体名称")
    relation_type: ExtractedRelationType = Field(description="关系类型")
    description: str | None = Field(default=None, description="关系描述")
    properties: dict[str, str] = Field(
        default_factory=dict,
        description="关系属性（键值对）",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="抽取置信度",
    )
    source_text: str | None = Field(default=None, description="来源文本片段")


class ExtractionResult(BaseModel):
    """综合抽取结果。

    同时返回实体、事件和关系的抽取结果。
    """

    entities: list[ExtractedEntity] = Field(
        default_factory=list,
        description="抽取的实体列表",
    )
    events: list[ExtractedEvent] = Field(
        default_factory=list,
        description="抽取的事件列表",
    )
    relations: list[ExtractedRelation] = Field(
        default_factory=list,
        description="抽取的关系列表",
    )
    source_summary: str | None = Field(
        default=None,
        description="来源文本摘要",
    )
    extraction_notes: str | None = Field(
        default=None,
        description="抽取说明/备注",
    )


class RelationExtractionResult(BaseModel):
    """关系抽取结果。

    批量返回从文本中抽取的所有关系。
    """

    relations: list[ExtractedRelation] = Field(
        default_factory=list,
        description="抽取的关系列表",
    )
    source_summary: str | None = Field(
        default=None,
        description="来源文本摘要",
    )


# Critic 输出 schema
class EvidenceGap(BaseModel):
    """证据缺口。"""

    description: str = Field(min_length=1, description="缺口描述")
    importance: str = Field(
        default="medium",
        description="重要性（high/medium/low）",
    )
    suggested_queries: list[str] = Field(
        default_factory=list,
        description="建议搜索查询",
    )


class CritiqueResult(BaseModel):
    """Critic 质量评估结果。

    用于识别证据缺口和质量问题。
    """

    overall_quality: float = Field(
        ge=0.0,
        le=1.0,
        description="整体质量评分（0-1）",
    )
    gaps: list[EvidenceGap] = Field(
        default_factory=list,
        description="证据缺口列表",
    )
    concerns: list[str] = Field(
        default_factory=list,
        description="质量问题列表",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="优势列表",
    )
    needs_more_evidence: bool = Field(
        default=False,
        description="是否需要更多证据",
    )
    summary: str = Field(min_length=1, description="评估摘要")


# Judge 输出 schema
class ConflictItem(BaseModel):
    """冲突条目。"""

    claim_a: str = Field(min_length=1, description="声明 A")
    claim_b: str = Field(min_length=1, description="声明 B")
    conflict_type: str = Field(
        default="contradiction",
        description="冲突类型（contradiction/inconsistency/temporal）",
    )
    resolution: str | None = Field(default=None, description="解决建议")
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="冲突判定置信度",
    )


class JudgeResult(BaseModel):
    """Judge 冲突仲裁结果。

    用于识别和仲裁声明之间的冲突。
    """

    has_conflicts: bool = Field(description="是否存在冲突")
    conflicts: list[ConflictItem] = Field(
        default_factory=list,
        description="冲突列表",
    )
    consistent_claims: list[str] = Field(
        default_factory=list,
        description="一致性声明列表",
    )
    overall_consistency: float = Field(
        ge=0.0,
        le=1.0,
        description="整体一致性评分（0-1）",
    )
    summary: str = Field(min_length=1, description="仲裁摘要")


# Watchlist 输出 schema
class WatchlistCategory(str, Enum):
    """观察指标类别。

    用于分类需要持续关注的态势指标。
    """

    ENTITY_CHANGE = "entity_change"
    """实体变化：部署调整、能力变化、状态转换等。"""

    EVENT_TRIGGER = "event_trigger"
    """事件触发条件：可能引发态势变化的事件信号。"""

    METRIC_THRESHOLD = "metric_threshold"
    """指标阈值：需要监控的数值指标及其临界值。"""

    TIMELINE_MILESTONE = "timeline_milestone"
    """时间节点：关键日期或时间窗口。"""

    UNCERTAINTY = "uncertainty"
    """不确定性消解：需要进一步确认或澄清的信息。"""


class WatchlistPriority(str, Enum):
    """观察指标优先级。"""

    HIGH = "high"
    """高优先级：需要立即关注。"""

    MEDIUM = "medium"
    """中优先级：常规监控。"""

    LOW = "low"
    """低优先级：背景关注。"""


class WatchlistItem(BaseModel):
    """观察指标条目。

    表示一个需要持续关注的态势指标，
    用于后续的态势追踪和预警。
    """

    indicator: str = Field(min_length=1, description="指标描述")
    category: WatchlistCategory = Field(description="指标类别")
    priority: WatchlistPriority = Field(
        default=WatchlistPriority.MEDIUM,
        description="优先级",
    )
    entities: list[str] = Field(
        default_factory=list,
        description="关联实体名称",
    )
    trigger_conditions: list[str] = Field(
        default_factory=list,
        description="触发条件列表",
    )
    rationale: str | None = Field(
        default=None,
        description="列入观察的理由",
    )
    evidence_refs: list[str] = Field(
        default_factory=list,
        description="支撑证据引用（引用编号）",
    )


class WatchlistExtractionResult(BaseModel):
    """Watchlist 抽取结果。

    批量返回从报告内容中抽取的所有观察指标。
    """

    items: list[WatchlistItem] = Field(
        default_factory=list,
        description="观察指标列表",
    )
    summary: str | None = Field(
        default=None,
        description="观察指标总结",
    )


# 解析前向引用（由于使用了 from __future__ import annotations）
EntityExtractionResult.model_rebuild()
EventExtractionResult.model_rebuild()
ExtractionResult.model_rebuild()
RelationExtractionResult.model_rebuild()
CritiqueResult.model_rebuild()
JudgeResult.model_rebuild()
WatchlistExtractionResult.model_rebuild()
