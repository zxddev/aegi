"""用户 Profile 个性化模块。

提供以下功能：
- 用户偏好存储与管理
- 个性化检索排序
- 历史行为分析
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class InterestLevel(Enum):
    """兴趣等级。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class ExpertiseLevel(Enum):
    """专业水平。"""

    EXPERT = "expert"
    INTERMEDIATE = "intermediate"
    BEGINNER = "beginner"


@dataclass
class TopicInterest:
    """主题兴趣。"""

    topic: str
    level: InterestLevel
    weight: float  # 0.0 - 1.0
    last_accessed: datetime | None = None
    access_count: int = 0


@dataclass
class RegionInterest:
    """地区兴趣。"""

    region: str
    level: InterestLevel
    weight: float
    last_accessed: datetime | None = None


@dataclass
class UserPreferences:
    """用户偏好设置。"""

    # 输出格式偏好
    preferred_language: str = "zh-CN"
    preferred_detail_level: str = "detailed"  # brief, detailed, comprehensive
    preferred_format: str = "structured"  # structured, narrative

    # 信息源偏好
    trusted_sources: list[str] = field(default_factory=list)
    blocked_sources: list[str] = field(default_factory=list)

    # 通知偏好
    notification_enabled: bool = True
    notification_topics: list[str] = field(default_factory=list)


@dataclass
class UserHistory:
    """用户历史记录。"""

    queries: list[dict[str, Any]] = field(default_factory=list)
    viewed_reports: list[str] = field(default_factory=list)
    saved_items: list[str] = field(default_factory=list)
    feedback: list[dict[str, Any]] = field(default_factory=list)

    def add_query(self, query: str, results_count: int) -> None:
        """记录查询。"""
        self.queries.append(
            {
                "query": query,
                "results_count": results_count,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        # 限制历史长度
        if len(self.queries) > 1000:
            self.queries = self.queries[-1000:]

    def add_feedback(self, item_id: str, rating: int, comment: str = "") -> None:
        """记录反馈。"""
        self.feedback.append(
            {
                "item_id": item_id,
                "rating": rating,
                "comment": comment,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )


@dataclass
class UserProfile:
    """用户画像。"""

    user_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # 专业背景
    expertise_level: ExpertiseLevel = ExpertiseLevel.INTERMEDIATE
    expertise_domains: list[str] = field(default_factory=list)

    # 兴趣画像
    topic_interests: list[TopicInterest] = field(default_factory=list)
    region_interests: list[RegionInterest] = field(default_factory=list)

    # 偏好设置
    preferences: UserPreferences = field(default_factory=UserPreferences)

    # 历史记录
    history: UserHistory = field(default_factory=UserHistory)

    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_topic_weight(self, topic: str) -> float:
        """获取主题权重。"""
        for interest in self.topic_interests:
            if interest.topic.lower() == topic.lower():
                return interest.weight
        return 0.0

    def get_region_weight(self, region: str) -> float:
        """获取地区权重。"""
        for interest in self.region_interests:
            if interest.region.lower() == region.lower():
                return interest.weight
        return 0.0

    def update_topic_interest(self, topic: str, level: InterestLevel) -> None:
        """更新主题兴趣。"""
        for interest in self.topic_interests:
            if interest.topic.lower() == topic.lower():
                interest.level = level
                interest.weight = self._level_to_weight(level)
                interest.last_accessed = datetime.now(UTC)
                interest.access_count += 1
                self.updated_at = datetime.now(UTC)
                return
        # 新增
        weight = self._level_to_weight(level)
        self.topic_interests.append(
            TopicInterest(
                topic=topic,
                level=level,
                weight=weight,
                last_accessed=datetime.now(UTC),
                access_count=1,
            )
        )
        self.updated_at = datetime.now(UTC)

    def _level_to_weight(self, level: InterestLevel) -> float:
        """兴趣等级转权重。"""
        mapping = {
            InterestLevel.HIGH: 1.0,
            InterestLevel.MEDIUM: 0.6,
            InterestLevel.LOW: 0.3,
            InterestLevel.NONE: 0.0,
        }
        return mapping.get(level, 0.5)


class ProfileStore:
    """用户画像存储（内存实现）。"""

    def __init__(self) -> None:
        """初始化存储。"""
        self._profiles: dict[str, UserProfile] = {}

    def get_profile(self, user_id: str) -> UserProfile | None:
        """获取用户画像。"""
        return self._profiles.get(user_id)

    def create_profile(self, user_id: str) -> UserProfile:
        """创建用户画像。"""
        profile = UserProfile(user_id=user_id)
        self._profiles[user_id] = profile
        return profile

    def save_profile(self, profile: UserProfile) -> None:
        """保存用户画像。"""
        profile.updated_at = datetime.now(UTC)
        self._profiles[profile.user_id] = profile

    def delete_profile(self, user_id: str) -> bool:
        """删除用户画像。"""
        if user_id in self._profiles:
            del self._profiles[user_id]
            return True
        return False


class PersonalizedRanker:
    """个性化排序器。"""

    def __init__(self, profile: UserProfile) -> None:
        """初始化排序器。

        Args:
            profile: 用户画像
        """
        self._profile = profile

    def rerank(
        self,
        items: list[dict[str, Any]],
        score_key: str = "score",
        topic_key: str = "topic",
        region_key: str = "region",
    ) -> list[dict[str, Any]]:
        """基于用户画像重排序结果。

        Args:
            items: 待排序项目列表
            score_key: 原始分数字段名
            topic_key: 主题字段名
            region_key: 地区字段名

        Returns:
            重排序后的列表
        """
        for item in items:
            original_score = item.get(score_key, 0.0)
            boost = 0.0

            # 主题偏好加成
            topic = item.get(topic_key, "")
            if topic:
                topic_weight = self._profile.get_topic_weight(topic)
                boost += topic_weight * 0.3

            # 地区偏好加成
            region = item.get(region_key, "")
            if region:
                region_weight = self._profile.get_region_weight(region)
                boost += region_weight * 0.2

            # 信息源偏好
            source = item.get("source", "")
            if source in self._profile.preferences.trusted_sources:
                boost += 0.2
            elif source in self._profile.preferences.blocked_sources:
                boost -= 0.5

            # 计算最终分数
            item["personalized_score"] = original_score * (1 + boost)

        # 按个性化分数排序
        items.sort(key=lambda x: x.get("personalized_score", 0), reverse=True)
        return items


class ProfileAnalyzer:
    """用户画像分析器。"""

    def __init__(self, profile: UserProfile) -> None:
        """初始化分析器。

        Args:
            profile: 用户画像
        """
        self._profile = profile

    def get_top_topics(self, limit: int = 5) -> list[str]:
        """获取最感兴趣的主题。"""
        sorted_topics = sorted(
            self._profile.topic_interests,
            key=lambda x: (x.weight, x.access_count),
            reverse=True,
        )
        return [t.topic for t in sorted_topics[:limit]]

    def get_query_patterns(self) -> dict[str, Any]:
        """分析查询模式。"""
        queries = self._profile.history.queries
        if not queries:
            return {"total_queries": 0}

        return {
            "total_queries": len(queries),
            "avg_results": sum(q.get("results_count", 0) for q in queries)
            / len(queries),
            "recent_queries": [q["query"] for q in queries[-10:]],
        }

    def get_recommendation_context(self) -> dict[str, Any]:
        """生成推荐上下文。"""
        return {
            "user_id": self._profile.user_id,
            "expertise_level": self._profile.expertise_level.value,
            "expertise_domains": self._profile.expertise_domains,
            "top_topics": self.get_top_topics(),
            "preferred_format": self._profile.preferences.preferred_format,
            "preferred_language": self._profile.preferences.preferred_language,
        }
