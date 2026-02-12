<!-- Author: msq -->

# CC 任务：P3 多源交叉关联引擎 + 分析记忆系统

## 背景

AEGI 当前的信息处理是线性的（搜集→提取→融合→分析），缺乏跨事件交叉关联和历史经验积累。需要两个新能力：
1. 多源交叉关联：发现不同事件之间的隐含关联模式
2. 分析记忆：积累历史分析经验，下次遇到类似模式时能引用

## 依赖

- P1 本体升级完成后效果更好（RelationFact 提供结构化关系），但本任务可以先用现有数据结构开始
- P2 InvestigationAgent 完成后，交叉关联发现可以触发自动调研

## 任务 1：CrossCorrelationEngine — 多源交叉关联

新建 `src/aegi_core/services/cross_correlation.py`：

核心思路：不是融合同一事件的多个来源（assertion_fuser 已做），而是发现不同事件之间的隐含关联。

```python
"""多源交叉关联引擎。

输入：一批新事件/claims
输出：发现的关联模式（哪些看似无关的事件组合在一起有意义）

三层关联策略：
1. 实体共现：不同事件涉及相同实体 → 可能有关联
2. 时空邻近：时间窗口内、地理邻近的事件 → 可能有关联
3. 语义模式：LLM 判断事件组合是否构成有意义的模式
"""

class CorrelationPattern(BaseModel):
    """发现的关联模式。"""
    pattern_uid: str
    pattern_type: str              # "entity_cooccurrence" | "spatiotemporal" | "semantic"
    event_uids: list[str]          # 涉及的事件 UID
    claim_uids: list[str]          # 涉及的 claim UID
    entities: list[str]            # 共同涉及的实体
    description: str               # LLM 生成的模式描述
    significance_score: float      # 0.0 ~ 1.0，模式的重要性
    confidence: float              # 0.0 ~ 1.0
    suggested_hypothesis: str | None  # LLM 建议的假设（可选）

class CrossCorrelationEngine:
    def __init__(self, db_session, llm, qdrant, neo4j):
        ...

    async def analyze_batch(self, case_uid: str, new_event_uids: list[str]) -> list[CorrelationPattern]:
        """对一批新事件做交叉关联分析。"""
        # 1. 加载新事件的实体、时间、地点
        # 2. 在历史事件中搜索实体共现
        # 3. 在历史事件中搜索时空邻近
        # 4. 用 Qdrant 做语义相似度搜索
        # 5. 对候选关联用 LLM 判断是否有意义
        # 6. 返回有意义的模式
        ...

    async def _entity_cooccurrence(self, new_events, historical_events) -> list[CorrelationPattern]:
        """实体共现关联：不同事件涉及相同实体。"""
        # 从 Neo4j 查询实体的所有关联事件
        # 找到与新事件共享实体的历史事件
        # 按共享实体数量排序
        ...

    async def _spatiotemporal_proximity(self, new_events, time_window_hours=72) -> list[CorrelationPattern]:
        """时空邻近关联：时间窗口内、同一地区的事件。"""
        # 查询同一 geo_country + 时间窗口内的事件
        # 用 GDELT 的 goldstein_scale 变化检测异常
        ...

    async def _semantic_pattern(self, new_events, top_k=20) -> list[CorrelationPattern]:
        """语义模式关联：用 embedding 找语义相似但表面不同的事件。"""
        # 新事件 embedding → Qdrant 搜索相似历史事件
        # 过滤掉同源事件（同一 URL/同一 source_domain）
        # 用 LLM 判断组合是否构成有意义的模式
        ...

    async def _llm_evaluate_pattern(self, events: list[dict]) -> tuple[bool, str, float]:
        """用 LLM 判断一组事件是否构成有意义的模式。
        返回 (is_significant, description, score)
        """
        ...
```

EventBus 集成：
- 监听 `claim.extracted` 和 `gdelt.event_detected`
- 批量收集（每 N 个事件或每 M 分钟触发一次分析）
- 发现重要模式时 emit `pattern.discovered` 事件
- `pattern.discovered` 可以触发 PushEngine 推送给专家

### 任务 2：AnalysisMemory — 分析记忆系统

新建 `src/aegi_core/services/analysis_memory.py`：

核心思路：把每次分析的假设、证据、结论、后续验证结果都存下来，形成可检索的经验库。

```python
"""分析记忆系统。

不是简单的 RAG，是结构化的分析经验库：
- 记录：分析场景 + 假设 + 证据 + 结论 + 后续验证
- 检索：给定新场景，找到历史上类似的分析案例
- 学习：统计哪些模式的预测准确率高/低
"""

class AnalysisMemoryEntry(BaseModel):
    """单条分析记忆。"""
    uid: str
    case_uid: str
    created_at: datetime

    # 场景描述（用于检索）
    scenario_summary: str          # LLM 生成的场景摘要
    scenario_embedding: list[float] | None  # 场景 embedding（存 Qdrant）

    # 分析内容
    hypotheses: list[dict]         # 假设列表 + 最终后验概率
    key_evidence: list[dict]       # 关键证据（诊断性最高的）
    conclusion: str                # 分析结论
    confidence: float              # 结论置信度

    # 后续验证（事后填写）
    outcome: str | None            # 实际结果
    prediction_accuracy: float | None  # 预测准确度
    lessons_learned: str | None    # 经验教训

    # 模式标签
    pattern_tags: list[str]        # 如 ["military_buildup", "diplomatic_withdrawal", "economic_pressure"]

class AnalysisMemory:
    def __init__(self, db_session, qdrant, llm):
        ...

    async def record(self, case_uid: str) -> AnalysisMemoryEntry:
        """从 case 的当前状态生成一条分析记忆。"""
        # 1. 加载 case 的假设、证据、贝叶斯状态
        # 2. 用 LLM 生成场景摘要和模式标签
        # 3. 生成 embedding 存入 Qdrant（analysis_memory 集合）
        # 4. 持久化到 DB
        ...

    async def recall(self, scenario: str, top_k: int = 5) -> list[AnalysisMemoryEntry]:
        """给定场景描述，检索历史上类似的分析案例。"""
        # 1. scenario → embedding
        # 2. Qdrant 搜索 analysis_memory 集合
        # 3. 返回最相似的历史案例
        ...

    async def update_outcome(self, memory_uid: str, outcome: str, accuracy: float):
        """事后更新：记录实际结果和预测准确度。"""
        ...

    async def get_pattern_stats(self, pattern_tag: str) -> dict:
        """统计某个模式标签的历史预测准确率。"""
        # 返回：出现次数、平均准确率、最近案例
        ...

    async def enhance_analysis(self, case_uid: str, current_hypotheses: list[dict]) -> dict:
        """用历史记忆增强当前分析。"""
        # 1. 用当前 case 的场景做 recall
        # 2. 找到类似历史案例
        # 3. 返回：历史上类似场景的结果分布、建议关注的证据类型、潜在盲区
        ...
```

DB 模型 `src/aegi_core/db/models/analysis_memory.py`：

```python
class AnalysisMemoryRecord(Base):
    __tablename__ = "analysis_memory"

    uid: str
    case_uid: str
    scenario_summary: str
    hypotheses: list[dict]         # JSON
    key_evidence: list[dict]       # JSON
    conclusion: str
    confidence: float
    outcome: str | None
    prediction_accuracy: float | None
    lessons_learned: str | None
    pattern_tags: list[str]        # JSON array
    created_at: datetime
    updated_at: datetime
```

Qdrant 集合：`analysis_memory`（BGE-M3 1024 维）

### 任务 3：集成到现有流程

1. `PipelineOrchestrator` 完成分析后，自动调用 `AnalysisMemory.record()` 保存记忆
2. 在“检索策略/假设生成”阶段调用 `AnalysisMemory.enhance_analysis()` 获取历史参考（例如 `query_planner.aplan_query()` 或假设生成前）
3. `BayesianACH.assess_evidence()` 保持证据驱动，不直接调用 `AnalysisMemory.enhance_analysis()`，避免确认偏差和高频性能开销
4. `CrossCorrelationEngine` 发现模式后，检查 `AnalysisMemory` 是否有类似历史模式
5. 新增 API：
   - `GET /api/memory?case_uid=xxx` — 查看分析记忆
   - `POST /api/memory/{uid}/outcome` — 更新实际结果
   - `GET /api/memory/patterns` — 查看模式统计
   - `GET /api/memory/recall?scenario=xxx` — 检索类似案例

### 任务 4：评估门禁

新建 `src/aegi_core/services/quality_gate.py`：

```python
"""质量门禁 — 用量化指标评估分析质量。"""

class QualityMetrics(BaseModel):
    # 实体链接
    entity_resolution_rate: float      # 成功消歧的实体比例
    # 关系抽取
    relation_extraction_coverage: float # 有关系的实体对比例
    # 冲突
    unresolved_conflicts: int          # 未解决的关系冲突数
    # 证据
    evidence_coverage: float           # 假设被证据覆盖的比例
    avg_diagnosticity: float           # 平均证据诊断性
    # 预测
    historical_accuracy: float | None  # 历史预测准确率（来自 AnalysisMemory）
    # 时效
    avg_evidence_age_hours: float      # 证据平均年龄

class QualityGate:
    async def evaluate(self, case_uid: str) -> QualityMetrics:
        """评估 case 的分析质量。"""
        ...

    async def should_alert(self, metrics: QualityMetrics) -> list[str]:
        """根据指标判断是否需要告警。"""
        alerts = []
        if metrics.evidence_coverage < 0.5:
            alerts.append("证据覆盖率低于 50%，建议补充证据")
        if metrics.unresolved_conflicts > 3:
            alerts.append(f"有 {metrics.unresolved_conflicts} 个未解决的关系冲突")
        if metrics.avg_diagnosticity < 1.5:
            alerts.append("证据诊断性偏低，难以区分假设")
        return alerts
```

## 验证

```bash
source .venv/bin/activate && source env.sh
python -m pytest tests/ -x --tb=short -q \
  --ignore=tests/test_feedback_service.py \
  --ignore=tests/test_stub_routes_integration.py
```

新增测试：
- `tests/test_cross_correlation.py`
- `tests/test_analysis_memory.py`
- `tests/test_quality_gate.py`
