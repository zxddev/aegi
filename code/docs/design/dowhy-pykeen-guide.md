# DoWhy 因果推断 + PyKEEN 链接预测 — 架构指导

> 日期：2026-02-11
> 作者：白泽
> 状态：架构指导，待详细设计

---

## 一、目标

让 AEGI 的知识图谱从"存储关系"升级为"推理关系"。

当前 AEGI 的 Neo4j 知识图谱只做了两件事：存实体关系 + 查路径。这是 GraphRAG 的基础能力，但远远不够。情报分析需要：

1. **因果推断（DoWhy）**：A 制裁 B → B 货币贬值，这是相关还是因果？有没有混淆因素？
2. **链接预测（PyKEEN）**：A 和 C 之间没有直接关系，但根据图结构，它们很可能存在隐含关联

这两个能力叠加后，AEGI 可以：
- 从已知事实推断因果链，给假设分析提供定量支撑
- 发现知识图谱中的"暗线"——尚未被证据证实但高概率存在的关系
- 主动提示分析师："根据图谱推断，X 和 Y 之间可能存在 Z 关系，建议验证"

---

## 二、与现有系统的关系

```
现有：
  graphrag_pipeline.py → LLM 抽取实体/关系 → Neo4j 存储
  graph_analysis.py    → networkx 社区发现/中心性/路径分析
  causal_reasoner.py   → assertion 时序一致性 + LLM 反事实推理

新增：
  causal_inference.py  → DoWhy 因果推断（从 Neo4j 子图构建因果模型）
  link_predictor.py    → PyKEEN 链接预测（从 Neo4j 子图训练 embedding）
```

关键：不替换现有的 `causal_reasoner.py`，而是在它旁边增加更强的因果推断能力。`causal_reasoner.py` 做的是 assertion 级别的时序一致性检查，新模块做的是实体级别的因果发现。

---

## 三、DoWhy 因果推断

### 3.1 DoWhy 能做什么

DoWhy 是微软开源的因果推断库，核心流程：
1. **建模（Model）**：定义因果图（DAG），指定处理变量、结果变量、混淆因素
2. **识别（Identify）**：自动找到可估计因果效应的统计方法
3. **估计（Estimate）**：用数据估计因果效应大小
4. **反驳（Refute）**：用多种方法检验因果结论的稳健性

### 3.2 AEGI 中的应用场景

| 场景 | 处理变量 | 结果变量 | 示例 |
|------|---------|---------|------|
| 制裁效果 | 制裁事件 | 经济指标变化 | 美国制裁伊朗 → 伊朗石油出口下降？ |
| 军事部署影响 | 军事部署 | 地区紧张度 | 航母进入海域 → 周边国家军事活动增加？ |
| 外交行动效果 | 外交声明 | 后续行为变化 | 联合声明 → 实际合作行动？ |
| 信息战效果 | 虚假信息传播 | 公众舆论变化 | 假新闻扩散 → 民意转向？ |

### 3.3 架构设计

```python
# services/causal_inference.py

class CausalInferenceEngine:
    """基于 DoWhy 的因果推断引擎。

    从 Neo4j 知识图谱提取子图，构建因果模型，
    估计实体间关系的因果效应。
    """

    def __init__(self, neo4j: Neo4jStore) -> None: ...

    async def build_causal_graph(
        self,
        case_uid: str,
        treatment_entity_uid: str,
        outcome_entity_uid: str,
    ) -> CausalGraphResult:
        """从 Neo4j 子图构建因果 DAG。

        流程：
        1. 从 Neo4j 提取 case 子图（graph_analysis._build_nx_graph 复用）
        2. 识别 treatment 和 outcome 之间的路径
        3. 识别潜在混淆因素（与 treatment 和 outcome 都有边的节点）
        4. 构建 DoWhy CausalModel
        """

    async def estimate_effect(
        self,
        case_uid: str,
        treatment_entity_uid: str,
        outcome_entity_uid: str,
        *,
        method: str = "backdoor.linear_regression",
    ) -> CausalEffectResult:
        """估计因果效应。

        流程：
        1. build_causal_graph()
        2. DoWhy identify_effect()
        3. DoWhy estimate_effect()
        4. DoWhy refute_estimate()（至少跑 placebo treatment 和 random common cause）
        5. 返回因果效应估计值 + 置信区间 + 稳健性检验结果
        """

    async def discover_causal_chains(
        self,
        case_uid: str,
        *,
        min_chain_length: int = 2,
        max_chain_length: int = 5,
    ) -> list[CausalChain]:
        """自动发现知识图谱中的因果链。

        不需要指定 treatment/outcome，自动扫描：
        1. 从 Neo4j 提取所有时序关系（有时间戳的边）
        2. 按时间排序，构建候选因果对
        3. 对每对候选用 DoWhy 估计因果效应
        4. 过滤掉效应不显著的
        5. 串联成因果链
        """
```

### 3.4 数据准备：从图结构到表格数据

DoWhy 需要表格数据（DataFrame），但 Neo4j 存的是图。转换策略：

```python
async def _graph_to_dataframe(
    self,
    neo4j: Neo4jStore,
    case_uid: str,
    entity_uids: list[str],
) -> pd.DataFrame:
    """将图结构转为 DoWhy 可用的表格数据。

    每行 = 一个时间点的观测
    列 = 实体的状态/属性值

    从 Neo4j 提取：
    - 实体的时序属性（如 tone、goldstein_scale）
    - 事件的发生时间和类型
    - 关系的建立/断裂时间

    转为二值或连续变量：
    - 事件发生 = 1，未发生 = 0
    - 关系存在 = 1，不存在 = 0
    - 数值属性直接用
    """
```

这是最关键也最难的部分。Phase 1 先做简单版：只处理有 `goldstein_scale` 或 `tone` 等数值属性的实体/事件，用事件发生的二值变量做因果推断。

### 3.5 返回值

```python
@dataclass
class CausalEffectResult:
    treatment: str              # 处理变量实体 uid
    outcome: str                # 结果变量实体 uid
    effect_estimate: float      # 因果效应估计值
    confidence_interval: tuple[float, float]  # 95% CI
    p_value: float | None
    method: str                 # 估计方法
    confounders: list[str]      # 识别的混淆因素
    refutation_results: list[dict]  # 稳健性检验
    is_significant: bool        # 效应是否显著（p < 0.05 且反驳通过）

@dataclass
class CausalChain:
    entities: list[str]         # 因果链上的实体 uid 序列
    effects: list[float]        # 相邻实体间的因果效应
    total_effect: float         # 链的总效应（乘积）
    confidence: float           # 链的整体置信度
```

---

## 四、PyKEEN 链接预测

### 4.1 PyKEEN 能做什么

PyKEEN 是知识图谱 embedding 库，核心能力：
1. 将实体和关系映射到低维向量空间
2. 训练模型学习图的结构模式
3. 预测缺失的三元组 (head, relation, tail)
4. 支持 30+ 模型（TransE, RotatE, ComplEx, DistMult 等）

### 4.2 AEGI 中的应用场景

| 场景 | 预测内容 | 示例 |
|------|---------|------|
| 隐含关联发现 | 实体间缺失的关系 | A 组织和 B 组织可能有资金往来 |
| 关系类型推断 | 已知实体对的关系类型 | X 国和 Y 国之间是合作还是对抗？ |
| 实体补全 | 三元组中缺失的实体 | 谁在幕后资助 Z 组织？ |
| 异常检测 | 不符合图模式的三元组 | 这条关系是否可疑（与图结构不一致）？ |

### 4.3 架构设计

```python
# services/link_predictor.py

class LinkPredictor:
    """基于 PyKEEN 的知识图谱链接预测引擎。

    从 Neo4j 提取三元组，训练 embedding 模型，
    预测缺失的实体关系。
    """

    def __init__(self, neo4j: Neo4jStore) -> None: ...

    async def train(
        self,
        case_uid: str,
        *,
        model_name: str = "RotatE",
        embedding_dim: int = 128,
        num_epochs: int = 100,
        batch_size: int = 256,
    ) -> TrainResult:
        """训练链接预测模型。

        流程：
        1. 从 Neo4j 提取 case 下所有三元组 (head, relation, tail)
        2. 构建 PyKEEN TriplesFactory
        3. 训练模型（RotatE 默认，平衡精度和速度）
        4. 评估（MRR, Hits@K）
        5. 缓存模型（内存或文件）
        """

    async def predict_missing_links(
        self,
        case_uid: str,
        *,
        top_k: int = 20,
        min_score: float = 0.5,
    ) -> list[PredictedLink]:
        """预测缺失的链接。

        流程：
        1. 加载已训练模型
        2. 对所有可能的 (head, relation, tail) 组合打分
        3. 过滤掉已存在的三元组
        4. 按分数降序返回 top_k
        """

    async def predict_for_entity(
        self,
        case_uid: str,
        entity_uid: str,
        *,
        direction: str = "both",  # head | tail | both
        top_k: int = 10,
    ) -> list[PredictedLink]:
        """预测某个实体的缺失关系。

        "这个实体还可能和谁有什么关系？"
        """

    async def detect_anomalous_triples(
        self,
        case_uid: str,
        *,
        threshold: float = 0.1,
    ) -> list[AnomalousTriple]:
        """检测异常三元组。

        已存在但分数极低的三元组 = 不符合图结构模式 = 可疑。
        可能是错误数据，也可能是值得深入调查的异常关系。
        """
```

### 4.4 Neo4j → PyKEEN 三元组提取

```python
async def _extract_triples(
    self,
    neo4j: Neo4jStore,
    case_uid: str,
) -> list[tuple[str, str, str]]:
    """从 Neo4j 提取三元组。

    Cypher:
    MATCH (h)-[r]->(t)
    WHERE h.case_uid = $case_uid OR t.case_uid = $case_uid
    RETURN h.uid AS head, type(r) AS relation, t.uid AS tail

    返回 [(head_uid, relation_type, tail_uid), ...]
    """
```

### 4.5 返回值

```python
@dataclass
class TrainResult:
    model_name: str
    num_triples: int
    num_entities: int
    num_relations: int
    mrr: float              # Mean Reciprocal Rank
    hits_at_1: float
    hits_at_10: float
    training_time_seconds: float

@dataclass
class PredictedLink:
    head_uid: str
    head_name: str
    relation: str
    tail_uid: str
    tail_name: str
    score: float            # 预测分数（0~1）
    confidence: str         # high | medium | low

@dataclass
class AnomalousTriple:
    head_uid: str
    relation: str
    tail_uid: str
    score: float            # 越低越异常
    existing: bool          # 是否已存在于图中
    reason: str             # "不符合图结构模式"
```

---

## 五、事件驱动集成

### 5.1 触发时机

不做定时训练。在以下时机触发：

| 触发事件 | 动作 |
|---------|------|
| `pipeline.completed` | 如果 case 的 KG 节点数 > 阈值（如 20），自动训练 PyKEEN + 跑 DoWhy |
| 手动 API 调用 | 分析师主动请求因果分析或链接预测 |
| `kg.updated`（新增） | KG 有新节点/边写入时 emit，触发增量预测 |

### 5.2 新增事件类型

| 事件类型 | 触发时机 | payload |
|---------|---------|---------|
| `causal.effect_discovered` | DoWhy 发现显著因果效应 | `{treatment, outcome, effect, confidence}` |
| `link.predicted` | PyKEEN 预测到高置信度缺失链接 | `{head, relation, tail, score}` |
| `link.anomaly_detected` | PyKEEN 发现异常三元组 | `{head, relation, tail, score}` |

这些事件通过 PushEngine 推送给订阅了该 case 的专家。

---

## 六、API 端点

### 6.1 因果推断

```
POST /cases/{case_uid}/causal/estimate
  body: {treatment_entity_uid, outcome_entity_uid, method?}
  → CausalEffectResult

GET  /cases/{case_uid}/causal/chains
  query: min_length?, max_length?
  → list[CausalChain]
```

### 6.2 链接预测

```
POST /cases/{case_uid}/links/train
  body: {model_name?, embedding_dim?, num_epochs?}
  → TrainResult

GET  /cases/{case_uid}/links/predictions
  query: top_k?, min_score?
  → list[PredictedLink]

GET  /cases/{case_uid}/links/predictions/{entity_uid}
  query: direction?, top_k?
  → list[PredictedLink]

GET  /cases/{case_uid}/links/anomalies
  query: threshold?
  → list[AnomalousTriple]
```

---

## 七、依赖管理

新增两个 Python 依赖：

```
dowhy>=0.11
pykeen>=1.10
```

这两个库比较重（PyKEEN 依赖 PyTorch），建议：
- `pyproject.toml` 中作为 optional dependency：`[project.optional-dependencies] analytics = ["dowhy>=0.11", "pykeen>=1.10"]`
- 代码中 lazy import：`try: import dowhy except ImportError: dowhy = None`
- 没装这两个库时，API 返回 501 Not Implemented，不影响其他功能

---

## 八、Settings 新增

```python
# settings.py
pykeen_default_model: str = "RotatE"
pykeen_embedding_dim: int = 128
pykeen_num_epochs: int = 100
pykeen_min_triples: int = 50          # 三元组数 < 50 时跳过训练
causal_min_observations: int = 10     # 观测数 < 10 时跳过因果推断
causal_significance_level: float = 0.05
```

---

## 九、文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `services/causal_inference.py` | 新建 | DoWhy 因果推断引擎 |
| `services/link_predictor.py` | 新建 | PyKEEN 链接预测引擎 |
| `api/routes/causal.py` | 新建 | 因果推断 API（2 端点） |
| `api/routes/links.py` | 新建 | 链接预测 API（4 端点） |
| `api/main.py` | 修改 | 注册路由 |
| `settings.py` | 修改 | 新增 6 个配置项 |
| `tests/test_causal_inference.py` | 新建 | 因果推断测试 |
| `tests/test_link_predictor.py` | 新建 | 链接预测测试 |
| `tests/test_causal_api.py` | 新建 | API 测试 |
| `tests/test_links_api.py` | 新建 | API 测试 |

---

## 十、实现优先级

**Phase 1（先做 PyKEEN，更容易出效果）：**
- `link_predictor.py`：三元组提取 → 训练 → 预测缺失链接 → 异常检测
- 原因：PyKEEN 只需要三元组，Neo4j 直接能提供，不需要额外的数据转换

**Phase 2（后做 DoWhy，需要更多数据准备）：**
- `causal_inference.py`：图→表格转换 → 因果建模 → 效应估计 → 稳健性检验
- 原因：DoWhy 需要表格数据，图→表格的转换逻辑比较复杂，需要仔细设计

**Phase 3（远期）：**
- 因果链自动发现（`discover_causal_chains`）
- PyKEEN 增量训练（新三元组加入后不重新训练，只更新 embedding）
- DoWhy + PyKEEN 联合：PyKEEN 预测的链接作为 DoWhy 的候选因果关系

---

_架构指导完成，待主人确认后出实现提示词。_
