"""用户 Profile 测试。"""

from __future__ import annotations

from baize_core.personalization.profile import (
    ExpertiseLevel,
    InterestLevel,
    PersonalizedRanker,
    ProfileAnalyzer,
    ProfileStore,
    TopicInterest,
    UserProfile,
)


class TestUserProfile:
    """UserProfile 测试。"""

    def test_create_profile(self) -> None:
        """测试创建画像。"""
        profile = UserProfile(user_id="user_1")
        assert profile.user_id == "user_1"
        assert profile.expertise_level == ExpertiseLevel.INTERMEDIATE

    def test_get_topic_weight(self) -> None:
        """测试获取主题权重。"""
        profile = UserProfile(user_id="user_1")
        profile.topic_interests = [
            TopicInterest(
                topic="军事",
                level=InterestLevel.HIGH,
                weight=1.0,
            )
        ]
        assert profile.get_topic_weight("军事") == 1.0
        assert profile.get_topic_weight("经济") == 0.0

    def test_update_topic_interest(self) -> None:
        """测试更新主题兴趣。"""
        profile = UserProfile(user_id="user_1")
        profile.update_topic_interest("军事", InterestLevel.HIGH)
        assert len(profile.topic_interests) == 1
        assert profile.topic_interests[0].weight == 1.0

        # 更新已有主题
        profile.update_topic_interest("军事", InterestLevel.MEDIUM)
        assert len(profile.topic_interests) == 1
        assert profile.topic_interests[0].weight == 0.6


class TestProfileStore:
    """ProfileStore 测试。"""

    def test_create_and_get(self) -> None:
        """测试创建和获取。"""
        store = ProfileStore()
        profile = store.create_profile("user_1")
        assert profile.user_id == "user_1"

        retrieved = store.get_profile("user_1")
        assert retrieved is not None
        assert retrieved.user_id == "user_1"

    def test_get_nonexistent(self) -> None:
        """测试获取不存在的画像。"""
        store = ProfileStore()
        assert store.get_profile("nonexistent") is None

    def test_delete(self) -> None:
        """测试删除。"""
        store = ProfileStore()
        store.create_profile("user_1")
        assert store.delete_profile("user_1") is True
        assert store.get_profile("user_1") is None
        assert store.delete_profile("user_1") is False


class TestPersonalizedRanker:
    """PersonalizedRanker 测试。"""

    def test_rerank_empty(self) -> None:
        """测试空列表排序。"""
        profile = UserProfile(user_id="user_1")
        ranker = PersonalizedRanker(profile)
        result = ranker.rerank([])
        assert result == []

    def test_rerank_with_topic_boost(self) -> None:
        """测试主题加成排序。"""
        profile = UserProfile(user_id="user_1")
        profile.update_topic_interest("军事", InterestLevel.HIGH)

        items = [
            {"id": "1", "score": 1.0, "topic": "经济"},
            {"id": "2", "score": 0.9, "topic": "军事"},
        ]
        ranker = PersonalizedRanker(profile)
        result = ranker.rerank(items)

        # 军事主题应该排在前面（有加成）
        assert result[0]["id"] == "2"
        assert result[0]["personalized_score"] > result[1]["personalized_score"]

    def test_rerank_with_blocked_source(self) -> None:
        """测试屏蔽源降权。"""
        profile = UserProfile(user_id="user_1")
        profile.preferences.blocked_sources = ["bad_source"]

        items = [
            {"id": "1", "score": 1.0, "source": "good_source"},
            {"id": "2", "score": 1.0, "source": "bad_source"},
        ]
        ranker = PersonalizedRanker(profile)
        result = ranker.rerank(items)

        # 屏蔽源应该排在后面
        assert result[0]["id"] == "1"


class TestProfileAnalyzer:
    """ProfileAnalyzer 测试。"""

    def test_get_top_topics(self) -> None:
        """测试获取热门主题。"""
        profile = UserProfile(user_id="user_1")
        profile.update_topic_interest("军事", InterestLevel.HIGH)
        profile.update_topic_interest("政治", InterestLevel.MEDIUM)
        profile.update_topic_interest("经济", InterestLevel.LOW)

        analyzer = ProfileAnalyzer(profile)
        topics = analyzer.get_top_topics(2)
        assert len(topics) == 2
        assert "军事" in topics

    def test_get_query_patterns_empty(self) -> None:
        """测试空查询模式。"""
        profile = UserProfile(user_id="user_1")
        analyzer = ProfileAnalyzer(profile)
        patterns = analyzer.get_query_patterns()
        assert patterns["total_queries"] == 0

    def test_get_recommendation_context(self) -> None:
        """测试获取推荐上下文。"""
        profile = UserProfile(user_id="user_1")
        profile.expertise_level = ExpertiseLevel.EXPERT
        profile.expertise_domains = ["情报分析"]
        profile.update_topic_interest("军事", InterestLevel.HIGH)

        analyzer = ProfileAnalyzer(profile)
        context = analyzer.get_recommendation_context()
        assert context["user_id"] == "user_1"
        assert context["expertise_level"] == "expert"
        assert "军事" in context["top_topics"]
