"""结构化输出测试。"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from baize_core.llm.structured import (
    GenerationMode,
    JsonModeAdapter,
    JsonModeConfig,
    ModelCapability,
    OutlinesAdapter,
    StructuredGenerationError,
    StructuredGenerator,
    build_json_mode_params,
    build_outlines_prompt,
    build_schema_prompt,
    detect_model_capability,
    extract_json_from_text,
    get_recommended_mode,
    is_outlines_available,
    supports_json_mode,
    validate_and_parse,
)
from baize_core.schemas.extraction import (
    CritiqueResult,
    EntityExtractionResult,
    EventExtractionResult,
    ExtractedEntityType,
    ExtractedEventType,
    ExtractionResult,
    JudgeResult,
)


class SampleOutput(BaseModel):
    """测试用输出模型。"""

    name: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)


class NestedOutput(BaseModel):
    """嵌套结构测试模型。"""

    title: str
    items: list[SampleOutput]


class TestExtractJsonFromText:
    """JSON 提取测试。"""

    def test_纯JSON文本(self) -> None:
        """测试直接解析纯 JSON 文本。"""
        text = '{"name": "test", "score": 0.8}'
        result = extract_json_from_text(text)
        assert result == '{"name": "test", "score": 0.8}'

    def test_带空白的JSON(self) -> None:
        """测试带前后空白的 JSON。"""
        text = '  \n{"name": "test", "score": 0.5}\n  '
        result = extract_json_from_text(text)
        assert result is not None
        assert '"name": "test"' in result

    def test_markdown代码块(self) -> None:
        """测试从 markdown 代码块提取 JSON。"""
        text = """
以下是输出：
```json
{"name": "example", "score": 0.9, "tags": ["a", "b"]}
```
"""
        result = extract_json_from_text(text)
        assert result is not None
        assert '"name": "example"' in result

    def test_无语言标记的代码块(self) -> None:
        """测试无语言标记的 markdown 代码块。"""
        text = """
```
{"name": "test", "score": 0.7}
```
"""
        result = extract_json_from_text(text)
        assert result is not None
        assert '"name": "test"' in result

    def test_嵌入在文本中的JSON(self) -> None:
        """测试从普通文本中提取嵌入的 JSON。"""
        text = '根据分析，结果如下：{"name": "result", "score": 0.6}。以上是输出。'
        result = extract_json_from_text(text)
        assert result is not None
        assert '"name": "result"' in result

    def test_JSON数组(self) -> None:
        """测试提取 JSON 数组。"""
        text = '[{"name": "a", "score": 0.1}, {"name": "b", "score": 0.2}]'
        result = extract_json_from_text(text)
        assert result is not None
        assert '"name": "a"' in result

    def test_无效JSON返回None(self) -> None:
        """测试无法提取有效 JSON 时返回 None。"""
        text = "这是一段普通文本，没有 JSON 内容"
        result = extract_json_from_text(text)
        assert result is None

    def test_不完整JSON返回None(self) -> None:
        """测试不完整 JSON 返回 None。"""
        text = '{"name": "test", "score":'
        result = extract_json_from_text(text)
        assert result is None


class TestValidateAndParse:
    """校验与解析测试。"""

    def test_有效JSON解析成功(self) -> None:
        """测试有效 JSON 解析为 Pydantic 模型。"""
        text = '{"name": "test", "score": 0.8, "tags": ["x", "y"]}'
        result, errors = validate_and_parse(text, SampleOutput)
        assert result is not None
        assert result.name == "test"
        assert result.score == 0.8
        assert result.tags == ["x", "y"]
        assert len(errors) == 0

    def test_缺少必需字段(self) -> None:
        """测试缺少必需字段时返回错误。"""
        text = '{"score": 0.5}'
        result, errors = validate_and_parse(text, SampleOutput)
        assert result is None
        assert len(errors) > 0
        assert any("name" in err for err in errors)

    def test_字段值超出范围(self) -> None:
        """测试字段值超出范围时返回错误。"""
        text = '{"name": "test", "score": 1.5}'
        result, errors = validate_and_parse(text, SampleOutput)
        assert result is None
        assert len(errors) > 0
        assert any("score" in err for err in errors)

    def test_嵌套结构解析(self) -> None:
        """测试嵌套结构解析。"""
        text = """
{
    "title": "Report",
    "items": [
        {"name": "item1", "score": 0.5, "tags": []},
        {"name": "item2", "score": 0.7, "tags": ["a"]}
    ]
}
"""
        result, errors = validate_and_parse(text, NestedOutput)
        assert result is not None
        assert result.title == "Report"
        assert len(result.items) == 2
        assert result.items[0].name == "item1"

    def test_从代码块提取并解析(self) -> None:
        """测试从 markdown 代码块提取并解析。"""
        text = """
输出如下：
```json
{"name": "example", "score": 0.9}
```
"""
        result, errors = validate_and_parse(text, SampleOutput)
        assert result is not None
        assert result.name == "example"

    def test_无法提取JSON返回错误(self) -> None:
        """测试无法提取 JSON 时返回错误。"""
        text = "这不是 JSON 内容"
        result, errors = validate_and_parse(text, SampleOutput)
        assert result is None
        assert any("无法从输出中提取有效 JSON" in err for err in errors)


class TestStructuredGenerator:
    """StructuredGenerator 测试。"""

    def test_默认模式为后置校验(self) -> None:
        """测试默认生成模式为后置校验。"""
        generator = StructuredGenerator()
        assert generator.default_mode == GenerationMode.POST_VALIDATE

    def test_自定义最大重试次数(self) -> None:
        """测试自定义最大重试次数。"""
        generator = StructuredGenerator(max_retries=5)
        assert generator.max_retries == 5

    def test_解析有效输出(self) -> None:
        """测试解析有效的 LLM 输出。"""
        generator = StructuredGenerator()
        text = '{"name": "test", "score": 0.6}'
        result = generator.parse_with_validation(text, SampleOutput)
        assert result.data.name == "test"
        assert result.mode_used == GenerationMode.POST_VALIDATE
        assert result.retries == 0

    def test_解析无效输出抛出异常(self) -> None:
        """测试解析无效输出时抛出异常。"""
        generator = StructuredGenerator()
        text = '{"name": "", "score": 0.5}'  # name 不能为空
        with pytest.raises(StructuredGenerationError) as exc_info:
            generator.parse_with_validation(text, SampleOutput)
        assert len(exc_info.value.validation_errors) > 0

    def test_构建结构化提示词(self) -> None:
        """测试构建带 schema 的提示词。"""
        generator = StructuredGenerator()
        user_prompt = "请分析以下内容"
        result = generator.build_structured_prompt(user_prompt, SampleOutput)
        assert "请分析以下内容" in result
        assert "JSON Schema" in result
        assert "name" in result
        assert "score" in result


class TestBuildSchemaPrompt:
    """schema 提示词构建测试。"""

    def test_生成JSON_Schema字符串(self) -> None:
        """测试生成可读的 JSON Schema 字符串。"""
        result = build_schema_prompt(SampleOutput)
        assert "name" in result
        assert "score" in result
        assert "tags" in result
        assert "properties" in result

    def test_嵌套模型生成完整Schema(self) -> None:
        """测试嵌套模型生成完整的 schema。"""
        result = build_schema_prompt(NestedOutput)
        assert "title" in result
        assert "items" in result


class TestGetRecommendedMode:
    """模式推荐测试。"""

    def test_JSON_MODE能力推荐JSON_MODE(self) -> None:
        """测试 JSON_MODE 能力推荐 JSON_MODE 模式。"""
        mode = get_recommended_mode(ModelCapability.JSON_MODE)
        assert mode == GenerationMode.JSON_MODE

    def test_FUNCTION_CALL能力推荐JSON_MODE(self) -> None:
        """测试 FUNCTION_CALL 能力推荐 JSON_MODE 模式。"""
        mode = get_recommended_mode(ModelCapability.FUNCTION_CALL)
        assert mode == GenerationMode.JSON_MODE

    def test_OUTLINES能力推荐OUTLINES(self) -> None:
        """测试 OUTLINES 能力推荐 OUTLINES 模式。"""
        mode = get_recommended_mode(ModelCapability.OUTLINES)
        assert mode == GenerationMode.OUTLINES

    def test_TEXT_ONLY能力推荐POST_VALIDATE(self) -> None:
        """测试 TEXT_ONLY 能力推荐 POST_VALIDATE 模式。"""
        mode = get_recommended_mode(ModelCapability.TEXT_ONLY)
        assert mode == GenerationMode.POST_VALIDATE


class TestStructuredGenerationError:
    """StructuredGenerationError 测试。"""

    def test_错误包含原始文本(self) -> None:
        """测试错误对象包含原始文本。"""
        error = StructuredGenerationError(
            message="测试错误",
            raw_text="原始输出",
            validation_errors=["错误1", "错误2"],
            retries=2,
        )
        assert error.raw_text == "原始输出"
        assert len(error.validation_errors) == 2
        assert error.retries == 2

    def test_错误消息正确(self) -> None:
        """测试错误消息正确传递。"""
        error = StructuredGenerationError(message="校验失败")
        assert str(error) == "校验失败"
        assert error.validation_errors == []


class TestOutlinesAvailability:
    """Outlines 可用性测试。"""

    def test_检查outlines是否可用(self) -> None:
        """测试检查 outlines 库是否已安装。"""
        # 仅测试函数可调用，不依赖实际安装状态
        result = is_outlines_available()
        assert isinstance(result, bool)


class TestOutlinesAdapter:
    """OutlinesAdapter 测试。"""

    def test_适配器初始化属性(self) -> None:
        """测试适配器初始化时保存的属性。"""
        if not is_outlines_available():
            pytest.skip("outlines 未安装")

        adapter = OutlinesAdapter(
            model_name="test-model",
            model_backend="transformers",
        )
        assert adapter.model_name == "test-model"
        assert adapter.model_backend == "transformers"

    def test_不支持的后端抛出错误(self) -> None:
        """测试不支持的模型后端抛出错误。"""
        if not is_outlines_available():
            pytest.skip("outlines 未安装")

        adapter = OutlinesAdapter(
            model_name="test-model",
            model_backend="unsupported",
        )
        with pytest.raises(ValueError, match="不支持的模型后端"):
            adapter._get_or_create_model()


class TestBuildOutlinesPrompt:
    """Outlines 提示词构建测试。"""

    def test_构建完整提示词(self) -> None:
        """测试构建包含系统提示、用户输入和 schema 的完整提示词。"""
        result = build_outlines_prompt(
            system="你是一个分析师",
            user="分析以下内容",
            schema=SampleOutput,
        )
        assert "你是一个分析师" in result
        assert "分析以下内容" in result
        assert "JSON Schema" in result
        assert "name" in result
        assert "score" in result

    def test_提示词包含schema定义(self) -> None:
        """测试提示词包含完整的 schema 定义。"""
        result = build_outlines_prompt(
            system="系统",
            user="用户",
            schema=NestedOutput,
        )
        assert "title" in result
        assert "items" in result
        assert "properties" in result


class TestJsonModeConfig:
    """JsonModeConfig 测试。"""

    def test_默认配置(self) -> None:
        """测试默认配置值。"""
        config = JsonModeConfig()
        assert config.response_format == "json_object"
        assert config.schema_name == "output"
        assert config.strict is False

    def test_自定义配置(self) -> None:
        """测试自定义配置值。"""
        config = JsonModeConfig(
            response_format="json_schema",
            schema_name="custom",
            strict=True,
        )
        assert config.response_format == "json_schema"
        assert config.schema_name == "custom"
        assert config.strict is True


class TestBuildJsonModeParams:
    """JSON mode 参数构建测试。"""

    def test_默认json_object模式(self) -> None:
        """测试默认 json_object 模式参数。"""
        params = build_json_mode_params(SampleOutput)
        assert "response_format" in params
        assert params["response_format"]["type"] == "json_object"

    def test_json_schema模式(self) -> None:
        """测试 json_schema 模式参数。"""
        config = JsonModeConfig(
            response_format="json_schema",
            schema_name="test_output",
            strict=True,
        )
        params = build_json_mode_params(SampleOutput, config)
        assert "response_format" in params
        rf = params["response_format"]
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["name"] == "test_output"
        assert rf["json_schema"]["strict"] is True
        assert "schema" in rf["json_schema"]


class TestJsonModeAdapter:
    """JsonModeAdapter 测试。"""

    def test_适配器初始化(self) -> None:
        """测试适配器初始化。"""
        adapter = JsonModeAdapter()
        assert adapter.config.response_format == "json_object"

    def test_自定义配置初始化(self) -> None:
        """测试自定义配置初始化。"""
        config = JsonModeConfig(response_format="json_schema")
        adapter = JsonModeAdapter(config)
        assert adapter.config.response_format == "json_schema"

    def test_构建请求参数(self) -> None:
        """测试构建请求参数。"""
        adapter = JsonModeAdapter()
        params = adapter.build_params(SampleOutput)
        assert "response_format" in params

    def test_解析有效响应(self) -> None:
        """测试解析有效的 JSON 响应。"""
        adapter = JsonModeAdapter()
        response = '{"name": "test", "score": 0.5}'
        result = adapter.parse_response(response, SampleOutput)
        assert result.data.name == "test"
        assert result.mode_used == GenerationMode.JSON_MODE

    def test_解析无效响应抛出异常(self) -> None:
        """测试解析无效响应时抛出异常。"""
        adapter = JsonModeAdapter()
        response = '{"name": "", "score": 0.5}'  # name 不能为空
        with pytest.raises(StructuredGenerationError):
            adapter.parse_response(response, SampleOutput)


class TestSupportsJsonMode:
    """supports_json_mode 测试。"""

    def test_gpt4支持(self) -> None:
        """测试 GPT-4 模型支持 JSON mode。"""
        assert supports_json_mode("gpt-4-turbo") is True
        assert supports_json_mode("gpt-4o") is True

    def test_gpt35支持(self) -> None:
        """测试 GPT-3.5 模型支持 JSON mode。"""
        assert supports_json_mode("gpt-3.5-turbo") is True

    def test_claude3支持(self) -> None:
        """测试 Claude 3 模型支持 JSON mode。"""
        assert supports_json_mode("claude-3-opus") is True
        assert supports_json_mode("claude-3-sonnet") is True

    def test_deepseek支持(self) -> None:
        """测试 DeepSeek 模型支持 JSON mode。"""
        assert supports_json_mode("deepseek-v3") is True
        assert supports_json_mode("deepseek-r1") is True

    def test_未知模型不支持(self) -> None:
        """测试未知模型不支持 JSON mode。"""
        assert supports_json_mode("unknown-model") is False


class TestDetectModelCapability:
    """detect_model_capability 测试。"""

    def test_云API模型检测为JSON_MODE(self) -> None:
        """测试云 API 模型检测为 JSON_MODE。"""
        assert detect_model_capability("gpt-4") == ModelCapability.JSON_MODE
        assert detect_model_capability("claude-3-opus") == ModelCapability.JSON_MODE
        assert detect_model_capability("deepseek-v3") == ModelCapability.JSON_MODE

    def test_ollama模型检测为OUTLINES(self) -> None:
        """测试 Ollama 模型检测为 OUTLINES。"""
        assert detect_model_capability("ollama/qwen2.5") == ModelCapability.OUTLINES
        assert detect_model_capability("ollama/llama3") == ModelCapability.OUTLINES

    def test_vllm模型检测为OUTLINES(self) -> None:
        """测试 vLLM 模型检测为 OUTLINES。"""
        assert detect_model_capability("vllm/mistral") == ModelCapability.OUTLINES

    def test_未知模型检测为TEXT_ONLY(self) -> None:
        """测试未知模型检测为 TEXT_ONLY。"""
        assert detect_model_capability("unknown") == ModelCapability.TEXT_ONLY


# ============================================================================
# 端到端测试：抽取 Schema 验证
# ============================================================================


class TestExtractionSchemaE2E:
    """抽取 Schema 端到端测试。"""

    def test_实体抽取结果解析(self) -> None:
        """测试解析实体抽取结果。"""
        json_text = """
{
    "entities": [
        {
            "name": "美国海军第七舰队",
            "entity_type": "Unit",
            "description": "驻日美军主力舰队",
            "aliases": ["第七舰队", "7th Fleet"],
            "confidence": 0.9
        },
        {
            "name": "横须贺基地",
            "entity_type": "Facility",
            "location": {
                "name": "横须贺",
                "country": "日本"
            },
            "confidence": 0.85
        }
    ],
    "source_summary": "美军在太平洋地区的军事部署"
}
"""
        result, errors = validate_and_parse(json_text, EntityExtractionResult)
        assert result is not None
        assert len(result.entities) == 2
        assert result.entities[0].name == "美国海军第七舰队"
        assert result.entities[0].entity_type == ExtractedEntityType.UNIT
        assert result.entities[1].location is not None
        assert result.entities[1].location.country == "日本"

    def test_事件抽取结果解析(self) -> None:
        """测试解析事件抽取结果。"""
        json_text = """
{
    "events": [
        {
            "summary": "中美海军在南海进行了对峙",
            "event_type": "Incident",
            "time_range": {
                "start": "2026-01-15T00:00:00Z",
                "is_approximate": true,
                "raw_text": "2026年1月中旬"
            },
            "location": {
                "name": "南海",
                "region": "西太平洋"
            },
            "participants": [
                {"name": "中国海军", "role": "participant"},
                {"name": "美国海军", "role": "participant"}
            ],
            "confidence": 0.75,
            "tags": ["南海", "军事对峙"]
        }
    ]
}
"""
        result, errors = validate_and_parse(json_text, EventExtractionResult)
        assert result is not None
        assert len(result.events) == 1
        event = result.events[0]
        assert event.event_type == ExtractedEventType.INCIDENT
        assert len(event.participants) == 2
        assert event.location is not None
        assert event.location.name == "南海"

    def test_综合抽取结果解析(self) -> None:
        """测试解析综合抽取结果。"""
        json_text = """
{
    "entities": [
        {"name": "俄罗斯", "entity_type": "Actor", "confidence": 0.95}
    ],
    "events": [
        {"summary": "俄军在边境增兵", "event_type": "Deployment", "confidence": 0.8}
    ],
    "source_summary": "乌克兰局势分析",
    "extraction_notes": "需要进一步核实兵力规模"
}
"""
        result, errors = validate_and_parse(json_text, ExtractionResult)
        assert result is not None
        assert len(result.entities) == 1
        assert len(result.events) == 1
        assert result.extraction_notes is not None

    def test_Critic结果解析(self) -> None:
        """测试解析 Critic 评估结果。"""
        json_text = """
{
    "overall_quality": 0.65,
    "gaps": [
        {
            "description": "缺少第三方来源验证",
            "importance": "high",
            "suggested_queries": ["搜索国际媒体报道", "查找智库分析"]
        }
    ],
    "concerns": ["主要来源偏向单一国家媒体"],
    "strengths": ["时效性好", "有官方声明支持"],
    "needs_more_evidence": true,
    "summary": "证据质量中等，需要补充第三方来源"
}
"""
        result, errors = validate_and_parse(json_text, CritiqueResult)
        assert result is not None
        assert result.overall_quality == 0.65
        assert len(result.gaps) == 1
        assert result.gaps[0].importance == "high"
        assert result.needs_more_evidence is True

    def test_Judge结果解析(self) -> None:
        """测试解析 Judge 仲裁结果。"""
        json_text = """
{
    "has_conflicts": true,
    "conflicts": [
        {
            "claim_a": "俄军已撤离边境",
            "claim_b": "卫星图像显示俄军仍在集结",
            "conflict_type": "contradiction",
            "resolution": "需要更新的卫星图像确认",
            "confidence": 0.8
        }
    ],
    "consistent_claims": ["双方存在军事紧张"],
    "overall_consistency": 0.6,
    "summary": "存在关于军事部署的矛盾信息"
}
"""
        result, errors = validate_and_parse(json_text, JudgeResult)
        assert result is not None
        assert result.has_conflicts is True
        assert len(result.conflicts) == 1
        assert result.conflicts[0].conflict_type == "contradiction"
        assert result.overall_consistency == 0.6


class TestStructuredOutputE2EFlow:
    """结构化输出端到端流程测试。"""

    def test_完整抽取流程_从LLM输出到schema(self) -> None:
        """测试完整的抽取流程：模拟 LLM 输出 -> 提取 JSON -> 校验 -> 解析。"""
        # 模拟 LLM 输出（包含前后文本）
        llm_output = """
根据分析，我识别出以下实体和事件：

```json
{
    "entities": [
        {
            "name": "北约",
            "entity_type": "Organization",
            "description": "北大西洋公约组织",
            "aliases": ["NATO"],
            "confidence": 0.95
        }
    ],
    "events": [
        {
            "summary": "北约举行联合军演",
            "event_type": "Exercise",
            "confidence": 0.85
        }
    ],
    "source_summary": "欧洲安全形势分析"
}
```

以上是我的分析结果。
"""
        # 使用 StructuredGenerator 处理
        generator = StructuredGenerator()
        result = generator.parse_with_validation(llm_output, ExtractionResult)

        assert result.data is not None
        assert len(result.data.entities) == 1
        assert result.data.entities[0].name == "北约"
        assert len(result.data.events) == 1
        assert result.data.events[0].event_type == ExtractedEventType.EXERCISE

    def test_校验失败时的错误信息(self) -> None:
        """测试校验失败时返回详细的错误信息。"""
        # 缺少必需字段的 JSON
        invalid_json = """
{
    "entities": [
        {
            "entity_type": "Unit"
        }
    ]
}
"""
        result, errors = validate_and_parse(invalid_json, EntityExtractionResult)
        assert result is None
        assert len(errors) > 0
        # 应该提示 name 字段缺失
        assert any("name" in err.lower() for err in errors)

    def test_嵌套结构校验(self) -> None:
        """测试嵌套结构的完整校验。"""
        json_text = """
{
    "events": [
        {
            "summary": "军事演习",
            "event_type": "Exercise",
            "time_range": {
                "start": "2026-01-01T00:00:00Z",
                "end": "2026-01-10T00:00:00Z",
                "is_approximate": false
            },
            "participants": [
                {"name": "中国", "role": "host", "entity_type": "Actor"},
                {"name": "俄罗斯", "role": "participant", "entity_type": "Actor"}
            ]
        }
    ]
}
"""
        result, errors = validate_and_parse(json_text, EventExtractionResult)
        assert result is not None
        event = result.events[0]
        assert event.time_range is not None
        assert event.time_range.start is not None
        assert event.time_range.end is not None
        assert len(event.participants) == 2
        assert event.participants[0].entity_type == ExtractedEntityType.ACTOR


# ============================================================
# 端到端测试：LlmRunner.generate_structured() 完整流程
# ============================================================


class TestLlmRunnerGenerateStructuredE2E:
    """LlmRunner.generate_structured() 端到端测试。

    测试从 LLM 调用到 schema 校验的完整流程。
    """

    @pytest.fixture
    def mock_policy_engine(self) -> object:
        """创建模拟策略引擎。"""
        from baize_core.config.settings import PolicyConfig
        from baize_core.policy.engine import PolicyEngine

        config = PolicyConfig(
            allowed_models=("*",),
            allowed_tools=("*",),
            default_allow=True,
            enforced_timeout_ms=30000,
            enforced_max_pages=20,
            enforced_max_iterations=3,
            enforced_min_sources=3,
            enforced_max_concurrency=5,
            require_archive_first=True,
            require_citations=True,
            hitl_risk_levels=tuple(),
            tool_risk_levels={},
        )
        return PolicyEngine(config)

    @pytest.fixture
    def mock_audit_recorder(self) -> object:
        """创建模拟审计记录器。"""

        class MockRecorder:
            """模拟审计记录器。"""

            def __init__(self) -> None:
                self.traces: list[object] = []
                self.decisions: list[object] = []

            async def record_model_trace(self, trace: object) -> None:
                """记录模型调用追踪。"""
                self.traces.append(trace)

            async def record_policy_decision(
                self, request: object, decision: object
            ) -> None:
                """记录策略决策。"""
                self.decisions.append((request, decision))

        return MockRecorder()

    @pytest.fixture
    def mock_review_store(self) -> object:
        """创建模拟评审存储。"""

        class MockReviewStore:
            """模拟评审存储。"""

            async def create_review_request(self, request: object) -> object:
                """创建评审请求（不应被调用）。"""
                raise NotImplementedError("不应在此测试中创建评审请求")

        return MockReviewStore()

    @pytest.fixture
    def llm_config(self) -> object:
        """创建 LLM 配置。"""
        from baize_core.llm.runner import LlmConfig

        return LlmConfig(
            provider="test",
            model="test-model",
            api_key="test-key",
            api_base="http://test.local",
        )

    @pytest.fixture
    def mock_model_router(self) -> object:
        """创建模拟模型路由器。"""
        from baize_core.llm.router import ModelRouter, ModelRouterConfig

        config = ModelRouterConfig(default_model="test-model")
        return ModelRouter(config)

    @pytest.mark.asyncio
    async def test_首次解析成功(
        self,
        mock_policy_engine: object,
        mock_audit_recorder: object,
        mock_review_store: object,
        llm_config: object,
        mock_model_router: object,
    ) -> None:
        """测试首次 LLM 输出即符合 schema 的场景。"""
        from unittest.mock import AsyncMock, patch

        from baize_core.llm.runner import LlmRunner
        from baize_core.schemas.policy import StageType

        runner = LlmRunner(
            policy_engine=mock_policy_engine,  # type: ignore[arg-type]
            recorder=mock_audit_recorder,  # type: ignore[arg-type]
            config=llm_config,  # type: ignore[arg-type]
            model_router=mock_model_router,  # type: ignore[arg-type]
            review_store=mock_review_store,  # type: ignore[arg-type]
        )

        # 模拟 LLM 返回有效的 JSON
        valid_response = '{"name": "test", "score": 0.8, "tags": ["tag1"]}'

        with patch.object(runner, "_call_litellm_messages", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = valid_response

            result = await runner.generate_structured(
                system="测试系统提示",
                user="生成测试输出",
                schema=SampleOutput,
                stage=StageType.OBSERVE,
                task_id="test-task-1",
            )

        # 验证结果
        assert result.data is not None
        assert result.data.name == "test"
        assert result.data.score == 0.8
        assert result.data.tags == ["tag1"]
        assert result.retries == 0
        assert len(result.validation_errors) == 0

        # 验证只调用了一次 LLM
        assert mock_llm.call_count == 1

    @pytest.mark.asyncio
    async def test_重试后成功(
        self,
        mock_policy_engine: object,
        mock_audit_recorder: object,
        mock_review_store: object,
        llm_config: object,
        mock_model_router: object,
    ) -> None:
        """测试首次失败、重试后成功的场景。"""
        from unittest.mock import patch

        from baize_core.llm.runner import LlmRunner
        from baize_core.schemas.policy import StageType

        runner = LlmRunner(
            policy_engine=mock_policy_engine,  # type: ignore[arg-type]
            recorder=mock_audit_recorder,  # type: ignore[arg-type]
            config=llm_config,  # type: ignore[arg-type]
            model_router=mock_model_router,  # type: ignore[arg-type]
            review_store=mock_review_store,  # type: ignore[arg-type]
        )

        # 第一次返回无效 JSON，第二次返回有效 JSON
        call_count = 0

        async def mock_response(*args: object, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 首次返回无效数据（score 超出范围）
                return '{"name": "test", "score": 1.5, "tags": []}'
            # 第二次返回有效数据
            return '{"name": "test", "score": 0.5, "tags": ["fixed"]}'

        with patch.object(runner, "_call_litellm_messages", side_effect=mock_response):
            result = await runner.generate_structured(
                system="测试系统提示",
                user="生成测试输出",
                schema=SampleOutput,
                stage=StageType.OBSERVE,
                task_id="test-task-2",
            )

        # 验证结果
        assert result.data is not None
        assert result.data.name == "test"
        assert result.data.score == 0.5
        assert result.data.tags == ["fixed"]
        assert result.retries == 1
        assert len(result.validation_errors) > 0

        # 验证调用了两次 LLM
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_重试耗尽后失败(
        self,
        mock_policy_engine: object,
        mock_audit_recorder: object,
        mock_review_store: object,
        llm_config: object,
        mock_model_router: object,
    ) -> None:
        """测试多次重试后仍然失败的场景。"""
        from unittest.mock import AsyncMock, patch

        from baize_core.llm.runner import LlmRunner
        from baize_core.schemas.policy import StageType

        runner = LlmRunner(
            policy_engine=mock_policy_engine,  # type: ignore[arg-type]
            recorder=mock_audit_recorder,  # type: ignore[arg-type]
            config=llm_config,  # type: ignore[arg-type]
            model_router=mock_model_router,  # type: ignore[arg-type]
            review_store=mock_review_store,  # type: ignore[arg-type]
        )

        # 始终返回无效 JSON
        invalid_response = '{"name": "", "score": 2.0}'

        with patch.object(runner, "_call_litellm_messages", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = invalid_response

            with pytest.raises(StructuredGenerationError) as exc_info:
                await runner.generate_structured(
                    system="测试系统提示",
                    user="生成测试输出",
                    schema=SampleOutput,
                    stage=StageType.OBSERVE,
                    task_id="test-task-3",
                    max_retries=3,
                )

        # 验证错误信息
        error = exc_info.value
        assert error.retries == 3
        assert len(error.validation_errors) > 0
        # 使用 str(error) 获取错误消息
        error_msg = str(error)
        assert "校验失败" in error_msg or "重试" in error_msg

        # 验证调用了 3 次 LLM
        assert mock_llm.call_count == 3

    @pytest.mark.asyncio
    async def test_带代码块的响应解析(
        self,
        mock_policy_engine: object,
        mock_audit_recorder: object,
        mock_review_store: object,
        llm_config: object,
        mock_model_router: object,
    ) -> None:
        """测试 LLM 返回带 markdown 代码块的响应。"""
        from unittest.mock import AsyncMock, patch

        from baize_core.llm.runner import LlmRunner
        from baize_core.schemas.policy import StageType

        runner = LlmRunner(
            policy_engine=mock_policy_engine,  # type: ignore[arg-type]
            recorder=mock_audit_recorder,  # type: ignore[arg-type]
            config=llm_config,  # type: ignore[arg-type]
            model_router=mock_model_router,  # type: ignore[arg-type]
            review_store=mock_review_store,  # type: ignore[arg-type]
        )

        # LLM 返回带代码块的响应
        response_with_codeblock = """
这是生成的结果：

```json
{"name": "codeblock-test", "score": 0.9, "tags": ["md", "block"]}
```

以上是输出内容。
"""

        with patch.object(runner, "_call_litellm_messages", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = response_with_codeblock

            result = await runner.generate_structured(
                system="测试系统提示",
                user="生成测试输出",
                schema=SampleOutput,
                stage=StageType.OBSERVE,
                task_id="test-task-4",
            )

        # 验证结果
        assert result.data is not None
        assert result.data.name == "codeblock-test"
        assert result.data.score == 0.9
        assert result.data.tags == ["md", "block"]

    @pytest.mark.asyncio
    async def test_嵌套结构解析(
        self,
        mock_policy_engine: object,
        mock_audit_recorder: object,
        mock_review_store: object,
        llm_config: object,
        mock_model_router: object,
    ) -> None:
        """测试嵌套结构的解析。"""
        from unittest.mock import AsyncMock, patch

        from baize_core.llm.runner import LlmRunner
        from baize_core.schemas.policy import StageType

        runner = LlmRunner(
            policy_engine=mock_policy_engine,  # type: ignore[arg-type]
            recorder=mock_audit_recorder,  # type: ignore[arg-type]
            config=llm_config,  # type: ignore[arg-type]
            model_router=mock_model_router,  # type: ignore[arg-type]
            review_store=mock_review_store,  # type: ignore[arg-type]
        )

        # 嵌套结构响应
        nested_response = """
{
    "title": "测试报告",
    "items": [
        {"name": "item1", "score": 0.8, "tags": ["a"]},
        {"name": "item2", "score": 0.6, "tags": ["b", "c"]}
    ]
}
"""

        with patch.object(runner, "_call_litellm_messages", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = nested_response

            result = await runner.generate_structured(
                system="测试系统提示",
                user="生成嵌套输出",
                schema=NestedOutput,
                stage=StageType.OBSERVE,
                task_id="test-task-5",
            )

        # 验证结果
        assert result.data is not None
        assert result.data.title == "测试报告"
        assert len(result.data.items) == 2
        assert result.data.items[0].name == "item1"
        assert result.data.items[1].score == 0.6

    @pytest.mark.asyncio
    async def test_实体抽取结果解析(
        self,
        mock_policy_engine: object,
        mock_audit_recorder: object,
        mock_review_store: object,
        llm_config: object,
        mock_model_router: object,
    ) -> None:
        """测试实际的 EntityExtractionResult schema 解析。"""
        from unittest.mock import AsyncMock, patch

        from baize_core.llm.runner import LlmRunner
        from baize_core.schemas.extraction import EntityExtractionResult
        from baize_core.schemas.policy import StageType

        runner = LlmRunner(
            policy_engine=mock_policy_engine,  # type: ignore[arg-type]
            recorder=mock_audit_recorder,  # type: ignore[arg-type]
            config=llm_config,  # type: ignore[arg-type]
            model_router=mock_model_router,  # type: ignore[arg-type]
            review_store=mock_review_store,  # type: ignore[arg-type]
        )

        # 模拟 LLM 返回实体抽取结果
        entity_response = """
```json
{
    "entities": [
        {
            "name": "第七舰队",
            "entity_type": "Unit",
            "aliases": ["7th Fleet"],
            "description": "美国海军第七舰队"
        },
        {
            "name": "日本海上自卫队",
            "entity_type": "Unit",
            "aliases": ["JMSDF"],
            "parent_org": "日本自卫队"
        }
    ]
}
```
"""

        with patch.object(runner, "_call_litellm_messages", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = entity_response

            result = await runner.generate_structured(
                system="你是军事情报分析专家",
                user="从以下文本中提取军事实体",
                schema=EntityExtractionResult,
                stage=StageType.OBSERVE,
                task_id="test-entity-extraction",
            )

        # 验证结果
        assert result.data is not None
        assert len(result.data.entities) == 2
        assert result.data.entities[0].name == "第七舰队"
        assert result.data.entities[1].name == "日本海上自卫队"

    @pytest.mark.asyncio
    async def test_Critique结果解析(
        self,
        mock_policy_engine: object,
        mock_audit_recorder: object,
        mock_review_store: object,
        llm_config: object,
        mock_model_router: object,
    ) -> None:
        """测试 CritiqueResult schema 解析。"""
        from unittest.mock import AsyncMock, patch

        from baize_core.llm.runner import LlmRunner
        from baize_core.schemas.extraction import CritiqueResult
        from baize_core.schemas.policy import StageType

        runner = LlmRunner(
            policy_engine=mock_policy_engine,  # type: ignore[arg-type]
            recorder=mock_audit_recorder,  # type: ignore[arg-type]
            config=llm_config,  # type: ignore[arg-type]
            model_router=mock_model_router,  # type: ignore[arg-type]
            review_store=mock_review_store,  # type: ignore[arg-type]
        )

        # 模拟 Critic Agent 的 LLM 输出
        # 使用与 CritiqueResult schema 匹配的字段名：gaps, summary, concerns, strengths
        critique_response = """
{
    "overall_quality": 0.75,
    "gaps": [
        {
            "description": "缺少事件发生的具体时间",
            "importance": "high",
            "suggested_queries": ["该事件发生的具体日期是什么？"]
        }
    ],
    "concerns": ["时间信息不够精确"],
    "strengths": ["证据来源可靠"],
    "needs_more_evidence": true,
    "summary": "证据链较为完整，但时间信息不够精确"
}
"""

        with patch.object(runner, "_call_litellm_messages", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = critique_response

            result = await runner.generate_structured(
                system="你是情报质量评估专家",
                user="评估以下证据链的质量",
                schema=CritiqueResult,
                stage=StageType.ORIENT,
                task_id="test-critique",
            )

        # 验证结果
        assert result.data is not None
        assert result.data.overall_quality == 0.75
        assert len(result.data.gaps) == 1
        assert result.data.gaps[0].importance == "high"
        assert result.data.summary is not None
