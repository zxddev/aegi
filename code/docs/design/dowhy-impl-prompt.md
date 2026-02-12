# DoWhy 因果推断实现提示词（给 Claude Code）

## 任务

基于 `docs/design/dowhy-pykeen-guide.md` 架构指导的 DoWhy 部分（第三节），实现因果推断功能。

**在开始编码前，先完整阅读以下文件：**
- `docs/design/dowhy-pykeen-guide.md` — 架构指导（主文档，重点看第三节 DoWhy 部分）
- `src/aegi_core/infra/neo4j_store.py` — Neo4j 存储层（重点看 `get_subgraph`、`get_all_triples`、`run_cypher`）
- `src/aegi_core/services/graph_analysis.py` — 现有图分析（参考 `_build_nx_graph` 的子图提取模式）
- `src/aegi_core/services/causal_reasoner.py` — 现有因果推理器（assertion 级别，不要修改它）
- `src/aegi_core/services/event_bus.py` — EventBus
- `src/aegi_core/services/link_predictor.py` — PyKEEN 实现（参考 optional dependency 的处理模式）
- `src/aegi_core/settings.py` — Settings 类
- `src/aegi_core/api/routes/kg.py` — 现有 KG 路由（参考风格）

## 实现范围

Phase 1：实体级别的因果推断。从 Neo4j 子图提取数据 → 构建因果 DAG → DoWhy 估计因果效应 → 稳健性检验。

不做：因果链自动发现（`discover_causal_chains`），那是 Phase 2。

## 关键设计决策

### 1. DoWhy 作为 optional dependency

与 PyKEEN 相同模式：

```toml
# pyproject.toml [project.optional-dependencies]
# 在已有的 analytics 组中追加
analytics = ["pykeen>=1.10", "dowhy>=0.11"]
```

代码中 lazy import：
```python
def _ensure_dowhy():
    try:
        import dowhy
        return dowhy
    except ImportError:
        raise RuntimeError(
            "DoWhy not installed. Run: pip install 'aegi-core[analytics]'"
        )
```

没装 DoWhy 时，API 返回 `501 Not Implemented`。

### 2. 图→表格数据转换（核心难点）

DoWhy 需要 pandas DataFrame，但 Neo4j 存的是图。Phase 1 采用简化策略：

**基于事件共现的二值矩阵：**
- 从 Neo4j 提取 case 子图中所有实体和关系
- 时间轴：按 `created_at` 或关系上的时间属性划分时间窗口（默认按天）
- 每个时间窗口生成一行观测
- 列 = 实体是否在该窗口内出现（二值 0/1）
- 如果实体有数值属性（如 GDELT 的 `tone`、`goldstein_scale`），直接用数值

```python
async def _graph_to_dataframe(
    self,
    case_uid: str,
    entity_uids: list[str],
    *,
    window: str = "1d",  # 时间窗口：1d, 12h, 1w
) -> pd.DataFrame:
    """将图结构转为 DoWhy 可用的表格数据。

    Cypher 提取：
    MATCH (n {case_uid: $case_uid})
    WHERE n.uid IN $entity_uids
    OPTIONAL MATCH (n)-[r]->(m {case_uid: $case_uid})
    RETURN n.uid, n.created_at, type(r), m.uid, r.created_at,
           n.tone, n.goldstein_scale
    ORDER BY coalesce(r.created_at, n.created_at)

    转换逻辑：
    1. 按时间窗口分桶
    2. 每个桶内，实体出现 = 1，未出现 = 0
    3. 数值属性取窗口内均值
    4. 返回 DataFrame，index = 时间窗口，columns = 实体 uid
    """
```

**最小观测数检查：** 如果 DataFrame 行数 < `settings.causal_min_observations`（默认 10），跳过因果推断，返回提示信息。数据太少做因果推断没意义。

### 3. 因果 DAG 构建

不让用户手动画 DAG。自动从图结构推断：

```python
async def build_causal_graph(
    self,
    case_uid: str,
    treatment_entity_uid: str,
    outcome_entity_uid: str,
) -> CausalGraphResult:
    """
    1. 从 Neo4j 提取 case 子图（复用 graph_analysis._build_nx_graph 模式）
    2. 在 networkx 图上找 treatment → outcome 的所有路径（max_length=4）
    3. 路径上的中间节点 = 中介变量（mediators）
    4. 与 treatment 和 outcome 都有边、但不在路径上的节点 = 混淆因素（confounders）
    5. 构建 DoWhy 的 GML 格式因果图字符串
    """
```

### 4. 不替换现有 causal_reasoner.py

`causal_reasoner.py` 做的是 assertion 级别的时序一致性检查 + LLM 反事实推理。新模块 `causal_inference.py` 做的是实体级别的统计因果推断。两者互补，不冲突。

## 实现顺序

### Step 1：Settings 新增

```python
# settings.py 新增
causal_min_observations: int = 10       # 观测数 < 10 时跳过
causal_significance_level: float = 0.05 # p-value 阈值
causal_time_window: str = "1d"          # 默认时间窗口
```

### Step 2：核心服务

新建 `services/causal_inference.py`：

```python
@dataclass
class CausalGraphResult:
    treatment: str                    # treatment 实体 uid
    outcome: str                      # outcome 实体 uid
    confounders: list[str]            # 混淆因素实体 uid
    mediators: list[str]              # 中介变量实体 uid
    gml_graph: str                    # DoWhy 用的 GML 格式因果图
    num_paths: int                    # treatment → outcome 路径数
    entity_names: dict[str, str]      # uid → name 映射

@dataclass
class RefutationResult:
    method: str                       # placebo_treatment / random_common_cause / data_subset
    estimated_effect: float
    new_effect: float
    p_value: float | None
    passed: bool                      # 是否通过稳健性检验

@dataclass
class CausalEffectResult:
    treatment: str
    treatment_name: str
    outcome: str
    outcome_name: str
    effect_estimate: float
    confidence_interval: tuple[float, float]
    p_value: float | None
    method: str                       # backdoor.linear_regression 等
    confounders: list[str]
    confounder_names: list[str]
    refutation_results: list[RefutationResult]
    is_significant: bool              # p < 0.05 且至少 1 个 refutation 通过
    num_observations: int
    warning: str | None = None        # 数据量不足等警告

class CausalInferenceEngine:
    def __init__(self, neo4j: Neo4jStore) -> None:
        self._neo4j = neo4j

    async def build_causal_graph(
        self,
        case_uid: str,
        treatment_entity_uid: str,
        outcome_entity_uid: str,
    ) -> CausalGraphResult: ...

    async def estimate_effect(
        self,
        case_uid: str,
        treatment_entity_uid: str,
        outcome_entity_uid: str,
        *,
        method: str = "backdoor.linear_regression",
        time_window: str | None = None,
    ) -> CausalEffectResult:
        """估计因果效应。

        流程：
        1. build_causal_graph() 获取因果 DAG
        2. _graph_to_dataframe() 获取表格数据
        3. 检查观测数 >= causal_min_observations
        4. dowhy.CausalModel(data, treatment, outcome, graph=gml)
        5. model.identify_effect(proceed_when_unidentifiable=True)
        6. model.estimate_effect(method_name=method)
        7. 稳健性检验（3 种方法）：
           - model.refute_estimate(method_name="placebo_treatment_refuter")
           - model.refute_estimate(method_name="random_common_cause")
           - model.refute_estimate(method_name="data_subset_refuter", subset_fraction=0.8)
        8. 综合判断 is_significant
        9. 如果显著，emit "causal.effect_discovered" 事件
        """

    async def _graph_to_dataframe(
        self,
        case_uid: str,
        entity_uids: list[str],
        *,
        window: str = "1d",
    ) -> pd.DataFrame: ...
```

### Step 3：API 路由

新建 `api/routes/causal.py`：

```python
router = APIRouter(prefix="/cases/{case_uid}/causal", tags=["causal-inference"])

# POST /cases/{case_uid}/causal/estimate
#   body: {treatment_entity_uid, outcome_entity_uid, method?, time_window?}
#   → CausalEffectResult
#   如果 DoWhy 未安装，返回 501
#   如果观测数不足，返回 200 + warning 字段

# POST /cases/{case_uid}/causal/graph
#   body: {treatment_entity_uid, outcome_entity_uid}
#   → CausalGraphResult（只构建因果图，不估计效应，用于前端可视化）
```

修改 `api/main.py`：注册 causal router。

### Step 4：事件集成

在 `estimate_effect()` 末尾，如果因果效应显著（`is_significant=True`），emit 事件：

```python
if result.is_significant:
    bus = get_event_bus()
    await bus.emit(AegiEvent(
        event_type="causal.effect_discovered",
        case_uid=case_uid,
        payload={
            "summary": f"发现因果关系：{result.treatment_name} → {result.outcome_name}，效应={result.effect_estimate:.3f}",
            "treatment": result.treatment_name,
            "outcome": result.outcome_name,
            "effect": result.effect_estimate,
            "confidence_interval": list(result.confidence_interval),
            "p_value": result.p_value,
            "refutations_passed": sum(1 for r in result.refutation_results if r.passed),
        },
        severity="medium",
        source_event_uid=f"causal:{case_uid}:{treatment_entity_uid}:{outcome_entity_uid}",
    ))
```

### Step 5：测试

1. `tests/test_causal_inference.py`（mock Neo4j + 条件跳过）：

```python
import pytest
dowhy = pytest.importorskip("dowhy")
```

测试用例：
- `test_graph_to_dataframe` — 构造 mock Neo4j 子图数据，验证转换后 DataFrame 的形状和列名
- `test_build_causal_graph` — 构造有路径的图，验证 confounders 和 mediators 识别正确
- `test_estimate_effect_significant` — 构造有因果关系的合成数据（treatment 和 outcome 强相关），验证 effect > 0 且 is_significant=True
- `test_estimate_effect_no_effect` — 构造无关的合成数据，验证 is_significant=False
- `test_estimate_effect_too_few_observations` — 观测数 < 10，返回 warning
- `test_refutation_results` — 验证 3 种稳健性检验都有结果

2. `tests/test_causal_api.py`（mock CausalInferenceEngine）：
- `test_estimate_endpoint` — POST estimate 返回 200
- `test_graph_endpoint` — POST graph 返回因果图
- `test_dowhy_not_installed` — mock ImportError，返回 501
- `test_insufficient_data` — 返回 200 + warning

3. 合成数据构造（关键）：

```python
def _make_causal_data(n: int = 50) -> pd.DataFrame:
    """构造有因果关系的合成数据。

    treatment (X) → outcome (Y)，有混淆因素 (Z)
    Z → X, Z → Y
    X → Y (真实因果效应 = 2.0)
    """
    import numpy as np
    np.random.seed(42)
    Z = np.random.normal(0, 1, n)
    X = 0.5 * Z + np.random.normal(0, 0.5, n)
    Y = 2.0 * X + 0.3 * Z + np.random.normal(0, 0.5, n)
    return pd.DataFrame({"X": X, "Y": Y, "Z": Z})
```

这样 DoWhy 应该能估计出 X→Y 的因果效应约为 2.0。

## 关键约束

- **DoWhy 是 optional dependency**：lazy import，没装时 API 返回 501
- **不修改 causal_reasoner.py**：新模块是增量叠加，不替换现有功能
- **不修改 neo4j_store.py**：用已有的 `get_subgraph()` 和 `run_cypher()` 方法
- **数据量保护**：观测数 < 10 时不跑 DoWhy，返回 warning
- **稳健性检验必须做**：至少跑 placebo_treatment 和 random_common_cause 两种 refutation
- **测试用 `pytest.importorskip("dowhy")`**：没装 DoWhy 的环境自动跳过
- **现有测试不能 break**：实现完成后跑全量 pytest，确保 0 failed

## 验收标准

1. 在安装了 DoWhy 的环境中：`pytest tests/test_causal_inference.py tests/test_causal_api.py` 全绿
2. 在未安装 DoWhy 的环境中：上述测试自动跳过，不 fail
3. `pytest` 全量测试 0 failed
4. 合成数据测试中，估计的因果效应在 1.5~2.5 范围内（真实值 2.0）
5. API 端点可通过 curl 手动验证（需要 Neo4j 有数据）
