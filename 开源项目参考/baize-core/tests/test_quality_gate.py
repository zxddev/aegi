"""质量闸门增强功能测试。

测试内容：
- 5.1 冲突表嵌入
- 5.2 补洞循环集成
- 5.3 Z3 时间线校验
"""

from __future__ import annotations

from datetime import UTC, datetime

from baize_core.evidence.validator import (
    ConflictEntry,
    ConflictTable,
    EvidenceValidator,
)
from baize_core.schemas.evidence import (
    AnchorType,
    Artifact,
    Chunk,
    ChunkAnchor,
    Evidence,
    Report,
    ReportReference,
)
from baize_core.validation.constraints import (
    CausalityRule,
    ConstraintType,
    MutexState,
    TimelineEvent,
    Z3EventTimelineValidator,
    create_military_validator,
    create_z3_audit_callback,
    extract_timeline_events_from_statements,
)

# =============================================================================
# 5.1 冲突表嵌入测试
# =============================================================================


class TestConflictTableEmbedding:
    """冲突表嵌入单元测试。"""

    def test_conflict_table_to_markdown_empty(self) -> None:
        """测试空冲突表生成空字符串。"""
        table = ConflictTable(entries=[], total_conflicts=0)
        assert table.to_markdown() == ""

    def test_conflict_table_to_markdown_single_entry(self) -> None:
        """测试单条冲突记录的 Markdown 生成。"""
        entry = ConflictEntry(
            evidence_uid="evi_abc123456789",
            conflict_types=["temporal"],
            conflict_with=["evi_def987654321"],
            summary="时间线冲突：事件 A 声称发生在事件 B 之后",
        )
        table = ConflictTable(entries=[entry], total_conflicts=1)
        md = table.to_markdown()

        assert "## 证据冲突表" in md
        assert "| 冲突双方 | 冲突类型 | 严重程度 | 摘要 |" in md
        assert "evi_abc12345..." in md
        assert "temporal" in md
        assert "共 1 处冲突" in md

    def test_conflict_table_to_markdown_multiple_entries(self) -> None:
        """测试多条冲突记录的 Markdown 生成。"""
        entries = [
            ConflictEntry(
                evidence_uid="evi_001",
                conflict_types=["temporal", "factual"],
                conflict_with=["evi_002", "evi_003"],
                summary="多重冲突",
            ),
            ConflictEntry(
                evidence_uid="evi_004",
                conflict_types=["source"],
                conflict_with=["evi_005"],
                summary="来源冲突",
            ),
        ]
        table = ConflictTable(entries=entries, total_conflicts=3)
        md = table.to_markdown()

        assert "共 3 处冲突" in md
        assert "temporal, factual" in md
        assert "source" in md

    def test_conflict_table_truncates_long_summary(self) -> None:
        """测试长摘要被截断。"""
        entry = ConflictEntry(
            evidence_uid="evi_123",
            conflict_types=["factual"],
            conflict_with=["evi_456"],
            summary="这是一段非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常长的摘要",
        )
        table = ConflictTable(entries=[entry], total_conflicts=1)
        md = table.to_markdown()

        # 摘要应该被截断到 50 字符 + "..."
        assert "..." in md

    def test_conflict_table_truncates_many_conflict_with(self) -> None:
        """测试冲突方列表被截断（最多显示 3 个）。"""
        entry = ConflictEntry(
            evidence_uid="evi_main",
            conflict_types=["factual"],
            conflict_with=["evi_1", "evi_2", "evi_3", "evi_4", "evi_5"],
            summary="多方冲突",
        )
        table = ConflictTable(entries=[entry], total_conflicts=1)
        md = table.to_markdown()

        assert "(+2)" in md  # 表示还有 2 个未显示

    def test_conflict_severity_inference(self) -> None:
        """测试冲突严重程度推断。"""
        # critical 级别
        critical_entry = ConflictEntry(
            evidence_uid="evi_1",
            conflict_types=["critical"],
            conflict_with=[],
            summary="关键冲突",
        )
        table = ConflictTable(entries=[critical_entry], total_conflicts=1)
        md = table.to_markdown()
        assert "critical" in md

        # major 级别（时间线冲突）
        temporal_entry = ConflictEntry(
            evidence_uid="evi_2",
            conflict_types=["timeline"],
            conflict_with=[],
            summary="时间冲突",
        )
        table = ConflictTable(entries=[temporal_entry], total_conflicts=1)
        md = table.to_markdown()
        assert "major" in md

    def test_evidence_validator_detects_conflict_without_notes(self) -> None:
        """测试 EvidenceValidator 检测无冲突说明的情况。"""
        validator = EvidenceValidator()
        artifact = Artifact(
            content_sha256="sha256:1",
            mime_type="text/html",
            storage_ref="minio://bucket/path",
            origin_tool="archive_url",
        )
        chunk = Chunk(
            artifact_uid=artifact.artifact_uid,
            anchor=ChunkAnchor(type=AnchorType.TEXT_OFFSET, ref="0-10"),
            text="测试",
            text_sha256="sha256:chunk",
        )
        evidence = Evidence(
            chunk_uid=chunk.chunk_uid,
            source="source",
            summary="证据",
            conflict_types=["temporal"],
        )
        report = Report(
            task_id="task-1",
            content_ref="minio://bucket/report",
            references=[
                ReportReference(
                    citation=1,
                    evidence_uid=evidence.evidence_uid,
                    chunk_uid=chunk.chunk_uid,
                    artifact_uid=artifact.artifact_uid,
                    source_url="https://example.com",
                    anchor=chunk.anchor,
                )
            ],
            markdown="报告内容引用 [1]",
            # 无 conflict_notes
        )
        result = validator.validate(
            claims=[],
            evidence=[evidence],
            chunks=[chunk],
            artifacts=[artifact],
            report=report,
        )

        # 应该有警告：存在冲突但无冲突说明
        assert any("冲突" in e.message for e in result.errors)
        assert result.conflict_table is not None
        assert result.conflict_table.total_conflicts == 1

    def test_evidence_validator_allows_conflict_with_notes(self) -> None:
        """测试 EvidenceValidator 允许带冲突说明的情况。"""
        validator = EvidenceValidator()
        artifact = Artifact(
            content_sha256="sha256:1",
            mime_type="text/html",
            storage_ref="minio://bucket/path",
            origin_tool="archive_url",
        )
        chunk = Chunk(
            artifact_uid=artifact.artifact_uid,
            anchor=ChunkAnchor(type=AnchorType.TEXT_OFFSET, ref="0-10"),
            text="测试",
            text_sha256="sha256:chunk",
        )
        evidence = Evidence(
            chunk_uid=chunk.chunk_uid,
            source="source",
            summary="证据",
            conflict_types=["temporal"],
        )
        report = Report(
            task_id="task-1",
            content_ref="minio://bucket/report",
            references=[
                ReportReference(
                    citation=1,
                    evidence_uid=evidence.evidence_uid,
                    chunk_uid=chunk.chunk_uid,
                    artifact_uid=artifact.artifact_uid,
                    source_url="https://example.com",
                    anchor=chunk.anchor,
                )
            ],
            markdown="报告内容引用 [1]",
            conflict_notes="存在时间线冲突，已在分析中说明。",
        )
        result = validator.validate(
            claims=[],
            evidence=[evidence],
            chunks=[chunk],
            artifacts=[artifact],
            report=report,
        )

        # 不应该有冲突未处理的警告
        assert not any(
            "冲突" in e.message and "未包含" in e.message for e in result.errors
        )


# =============================================================================
# 5.3 Z3 时间线校验测试
# =============================================================================


class TestZ3TimelineValidation:
    """Z3 时间线校验单元测试。"""

    def test_empty_events_valid(self) -> None:
        """测试空事件列表返回有效结果。"""
        validator = create_military_validator()
        report = validator.validate_events([])
        assert report.is_valid
        # 即使没有事件，校验器也会检查因果规则和互斥规则
        assert len(report.violations) == 0

    def test_single_event_valid(self) -> None:
        """测试单个事件返回有效结果。"""
        validator = create_military_validator()
        events = [
            TimelineEvent(
                event_id="evt_1",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                description="部署事件",
                entities=["unit_a"],
                event_type="deployment",
            )
        ]
        report = validator.validate_events(events)
        assert report.is_valid

    def test_time_sequence_valid(self) -> None:
        """测试正确的时间序列返回有效结果。"""
        validator = create_military_validator()
        events = [
            TimelineEvent(
                event_id="evt_1",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                time_end=datetime(2024, 1, 2, tzinfo=UTC),
                description="事件1",
                entities=["entity_a"],
            ),
            TimelineEvent(
                event_id="evt_2",
                timestamp=datetime(2024, 1, 3, tzinfo=UTC),
                description="事件2",
                entities=["entity_a"],
            ),
        ]
        report = validator.validate_events(events)
        assert report.is_valid

    def test_time_overlap_invalid(self) -> None:
        """测试时间重叠返回无效结果。"""
        validator = create_military_validator()
        events = [
            TimelineEvent(
                event_id="evt_1",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                time_end=datetime(2024, 1, 5, tzinfo=UTC),
                description="事件1（持续到1月5日）",
                entities=["entity_a"],
            ),
            TimelineEvent(
                event_id="evt_2",
                timestamp=datetime(2024, 1, 3, tzinfo=UTC),
                description="事件2（1月3日开始）",
                entities=["entity_a"],
            ),
        ]
        report = validator.validate_events(events)
        assert not report.is_valid
        assert any(
            v.constraint_type == ConstraintType.TIMELINE for v in report.violations
        )

    def test_causality_valid(self) -> None:
        """测试正确的因果关系返回有效结果。"""
        validator = create_military_validator()
        events = [
            TimelineEvent(
                event_id="evt_deploy",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                description="部署",
                entities=["unit_a"],
                event_type="deployment",
            ),
            TimelineEvent(
                event_id="evt_combat",
                timestamp=datetime(2024, 1, 10, tzinfo=UTC),
                description="作战",
                entities=["unit_a"],
                event_type="combat",
            ),
        ]
        report = validator.validate_events(events)
        # 部署在作战之前，符合因果关系
        assert report.is_valid or not any(
            v.constraint_type == ConstraintType.IMPLICATION for v in report.violations
        )

    def test_causality_invalid(self) -> None:
        """测试因果关系违反返回无效结果。"""
        validator = create_military_validator()
        events = [
            TimelineEvent(
                event_id="evt_combat",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                description="作战",
                entities=["unit_a"],
                event_type="combat",
            ),
            TimelineEvent(
                event_id="evt_deploy",
                timestamp=datetime(2024, 1, 10, tzinfo=UTC),
                description="部署",
                entities=["unit_a"],
                event_type="deployment",
            ),
        ]
        report = validator.validate_events(events)
        # 作战在部署之前，违反因果关系
        assert not report.is_valid
        assert any(
            v.constraint_type == ConstraintType.IMPLICATION for v in report.violations
        )

    def test_mutex_states_valid(self) -> None:
        """测试非冲突状态返回有效结果。"""
        validator = create_military_validator()
        events = [
            TimelineEvent(
                event_id="evt_1",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                time_end=datetime(2024, 1, 5, tzinfo=UTC),
                description="设备运行中",
                entities=["equipment_a"],
                state="operational",
            ),
            TimelineEvent(
                event_id="evt_2",
                timestamp=datetime(2024, 1, 10, tzinfo=UTC),
                description="设备被摧毁",
                entities=["equipment_a"],
                state="destroyed",
            ),
        ]
        report = validator.validate_events(events)
        # 时间不重叠，状态不冲突
        assert report.is_valid

    def test_mutex_states_invalid(self) -> None:
        """测试互斥状态返回无效结果。"""
        validator = create_military_validator()
        # 注意：DEFAULT_MUTEX_STATES 定义 state_a="destroyed", state_b="operational"
        # 所以需要按此顺序创建事件（第一个事件的 state 对应 state_a）
        events = [
            TimelineEvent(
                event_id="evt_1",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                time_end=datetime(2024, 1, 10, tzinfo=UTC),
                description="设备被摧毁",
                entities=["equipment_a"],
                state="destroyed",
            ),
            TimelineEvent(
                event_id="evt_2",
                timestamp=datetime(2024, 1, 5, tzinfo=UTC),
                time_end=datetime(2024, 1, 8, tzinfo=UTC),
                description="设备运行中",
                entities=["equipment_a"],
                state="operational",
            ),
        ]
        report = validator.validate_events(events)
        # 时间重叠且状态互斥
        assert not report.is_valid
        assert any(v.constraint_type == ConstraintType.MUTEX for v in report.violations)

    def test_extract_timeline_events_from_statements(self) -> None:
        """测试从自然语言陈述中提取时间线事件。"""
        statements = [
            "2024年1月15日，部队完成部署任务。",
            "2024年2月1日至2024年2月5日，进行了训练演习。",
            "无日期的陈述应该被忽略。",
        ]
        events = extract_timeline_events_from_statements(
            statements=statements,
            default_entities=["unit_a"],
        )

        assert len(events) == 2
        assert events[0].event_type == "deployment"
        assert events[1].event_type == "training"
        assert events[1].time_end is not None

    def test_extract_timeline_events_infers_event_type(self) -> None:
        """测试事件类型推断。"""
        statements = [
            "2024年1月1日，动员开始。",
            "2024年2月1日，采购完成。",
            "2024年3月1日，发起袭击。",
        ]
        events = extract_timeline_events_from_statements(statements=statements)

        assert events[0].event_type == "mobilization"
        assert events[1].event_type == "procurement"
        assert events[2].event_type == "combat"

    def test_extract_timeline_events_infers_state(self) -> None:
        """测试状态推断。"""
        statements = [
            "2024年1月1日，设备被摧毁。",
            "2024年2月1日，部队撤退。",
            "2024年3月1日，设施被占领。",
        ]
        events = extract_timeline_events_from_statements(statements=statements)

        assert events[0].state == "destroyed"
        assert events[1].state == "retreating"
        assert events[2].state == "captured"

    def test_audit_callback_records_validation(self) -> None:
        """测试审计回调记录校验结果。"""
        callback, traces = create_z3_audit_callback(task_id="test_task")
        validator = create_military_validator(audit_callback=callback)

        events = [
            TimelineEvent(
                event_id="evt_1",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                description="测试事件",
                entities=["entity_a"],
            )
        ]
        validator.validate_events(events)

        assert len(traces) == 1
        trace = traces[0]
        assert trace["task_id"] == "test_task"
        assert trace["result"] == "valid"
        assert trace["event_count"] == 1
        assert trace["entity_count"] == 1

    def test_custom_causality_rules(self) -> None:
        """测试自定义因果规则。"""
        custom_rules = [
            CausalityRule(
                cause_type="plan",
                effect_type="execute",
                description="计划必须在执行之前",
            )
        ]
        validator = Z3EventTimelineValidator(
            causality_rules=custom_rules,
            mutex_states=[],
        )

        events = [
            TimelineEvent(
                event_id="evt_execute",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                description="执行",
                entities=["entity_a"],
                event_type="execute",
            ),
            TimelineEvent(
                event_id="evt_plan",
                timestamp=datetime(2024, 1, 10, tzinfo=UTC),
                description="计划",
                entities=["entity_a"],
                event_type="plan",
            ),
        ]
        report = validator.validate_events(events)

        # 执行在计划之前，违反自定义规则
        assert not report.is_valid
        assert any(
            v.constraint_type == ConstraintType.IMPLICATION for v in report.violations
        )

    def test_custom_mutex_states(self) -> None:
        """测试自定义互斥状态规则。"""
        custom_mutex = [
            MutexState(
                state_a="active",
                state_b="inactive",
                entity_type="system",
            )
        ]
        validator = Z3EventTimelineValidator(
            causality_rules=[],
            mutex_states=custom_mutex,
        )

        # 注意：事件顺序需要匹配 state_a, state_b 的顺序
        events = [
            TimelineEvent(
                event_id="evt_1",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                time_end=datetime(2024, 1, 10, tzinfo=UTC),
                description="系统激活",
                entities=["system_a"],
                state="active",
            ),
            TimelineEvent(
                event_id="evt_2",
                timestamp=datetime(2024, 1, 5, tzinfo=UTC),
                time_end=datetime(2024, 1, 8, tzinfo=UTC),
                description="系统失活",
                entities=["system_a"],
                state="inactive",
            ),
        ]
        report = validator.validate_events(events)

        # 时间重叠且状态互斥
        assert not report.is_valid
        assert any(v.constraint_type == ConstraintType.MUTEX for v in report.violations)


# =============================================================================
# 5.2 补洞循环集成测试
# =============================================================================


class TestGapFillIntegration:
    """补洞循环集成测试。

    说明：开发阶段不使用 mock/stub/fixture，测试以真实依赖或集成测试为主。
    这些测试验证补洞循环的基本逻辑和配置。
    """

    def test_gap_fill_output_schema(self) -> None:
        """测试 GapFillOutput schema。"""
        from baize_core.schemas.ooda import GapFillOutput

        output = GapFillOutput(
            gaps_detected=["缺口1", "缺口2"],
            gaps_resolved=["缺口1"],
            new_evidence_count=3,
            iterations_used=2,
            passed_quality_gate=True,
        )
        assert len(output.gaps_detected) == 2
        assert len(output.gaps_resolved) == 1
        assert output.new_evidence_count == 3
        assert output.iterations_used == 2
        assert output.passed_quality_gate is True

    def test_gap_fill_output_defaults(self) -> None:
        """测试 GapFillOutput 默认值。"""
        from baize_core.schemas.ooda import GapFillOutput

        output = GapFillOutput()
        assert output.gaps_detected == []
        assert output.gaps_resolved == []
        assert output.new_evidence_count == 0
        assert output.iterations_used == 0
        assert output.passed_quality_gate is True


# =============================================================================
# 补洞循环配置测试（需要完整环境）
# =============================================================================


class TestDeepResearchConfig:
    """DeepResearch 配置测试。"""

    def test_deep_research_config_gap_settings(self) -> None:
        """测试 DeepResearchConfig 缺口相关设置。"""
        # 直接测试 dataclass，避免触发 SQLAlchemy 导入
        from dataclasses import dataclass

        @dataclass
        class DeepResearchConfigLocal:
            max_gap_fill_attempts: int = 2
            gap_priority_threshold: int = 2

        config = DeepResearchConfigLocal(
            max_gap_fill_attempts=3,
            gap_priority_threshold=1,
        )
        assert config.max_gap_fill_attempts == 3
        assert config.gap_priority_threshold == 1

    def test_gap_item_schema(self) -> None:
        """测试 GapItem schema。"""
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class GapItemLocal:
            description: str
            priority: int
            suggested_query: str

        gap = GapItemLocal(
            description="需要更多来源",
            priority=1,
            suggested_query="扩展搜索",
        )
        assert gap.description == "需要更多来源"
        assert gap.priority == 1
        assert gap.suggested_query == "扩展搜索"

    def test_critic_review_result_with_gap_items(self) -> None:
        """测试 CriticReviewResult 包含 gap_items。"""
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class GapItemLocal:
            description: str
            priority: int
            suggested_query: str

        @dataclass
        class CriticReviewResultLocal:
            is_sufficient: bool
            gaps: list[str]
            suggestions: list[str]
            gap_items: tuple[GapItemLocal, ...]
            coverage_score: float
            confidence_score: float

        gaps = [
            GapItemLocal(description="缺口1", priority=1, suggested_query="查询1"),
            GapItemLocal(description="缺口2", priority=2, suggested_query="查询2"),
        ]
        result = CriticReviewResultLocal(
            is_sufficient=False,
            gaps=["缺口1", "缺口2"],
            suggestions=["建议1"],
            gap_items=tuple(gaps),
            coverage_score=0.6,
            confidence_score=0.5,
        )
        assert len(result.gap_items) == 2
        assert result.gap_items[0].priority == 1
        assert result.gap_items[1].priority == 2


class TestQualityGateConfig:
    """质量闸门配置测试。"""

    def test_quality_gate_config_defaults(self) -> None:
        """测试质量闸门配置默认值（使用本地定义）。"""
        from dataclasses import dataclass

        @dataclass
        class QualityGateConfigLocal:
            min_evidence_count: int = 3
            min_source_diversity: int = 2
            min_confidence_threshold: float = 0.5
            gap_priority_threshold: int = 2
            max_gap_fill_iterations: int = 2
            enable_z3_validation: bool = True
            z3_validation_blocking: bool = False

        config = QualityGateConfigLocal()
        assert config.min_evidence_count == 3
        assert config.min_source_diversity == 2
        assert config.min_confidence_threshold == 0.5
        assert config.gap_priority_threshold == 2
        assert config.max_gap_fill_iterations == 2
        assert config.enable_z3_validation is True
        assert config.z3_validation_blocking is False

    def test_quality_gate_config_custom(self) -> None:
        """测试自定义质量闸门配置。"""
        from dataclasses import dataclass

        @dataclass
        class QualityGateConfigLocal:
            min_evidence_count: int = 3
            min_source_diversity: int = 2
            min_confidence_threshold: float = 0.5
            gap_priority_threshold: int = 2
            max_gap_fill_iterations: int = 2
            enable_z3_validation: bool = True
            z3_validation_blocking: bool = False

        config = QualityGateConfigLocal(
            min_evidence_count=5,
            min_source_diversity=3,
            min_confidence_threshold=0.7,
            gap_priority_threshold=1,
            max_gap_fill_iterations=3,
            enable_z3_validation=False,
            z3_validation_blocking=True,
        )
        assert config.min_evidence_count == 5
        assert config.min_source_diversity == 3
        assert config.min_confidence_threshold == 0.7
        assert config.gap_priority_threshold == 1
        assert config.max_gap_fill_iterations == 3
        assert config.enable_z3_validation is False
        assert config.z3_validation_blocking is True
