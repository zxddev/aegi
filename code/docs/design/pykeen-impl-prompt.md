# PyKEEN 链接预测实现提示词（给 Claude Code）

## 任务

基于 `docs/design/dowhy-pykeen-guide.md` 架构指导的 Phase 1 部分，实现 PyKEEN 知识图谱链接预测功能。

**在开始编码前，先完整阅读以下文件：**
- `docs/design/dowhy-pykeen-guide.md` — 架构指导（主文档，重点看第四节 PyKEEN 部分）
- `src/aegi_core/infra/neo4j_store.py` — Neo4j 存储层（重点看 `get_subgraph`、`run_cypher`）
- `src/aegi_core/services/graph_analysis.py` — 现有图分析（参考 `_build_nx_graph` 的子图提取模式）
- `src/aegi_core/services/event_bus.py` — EventBus
- `src/aegi_core/settings.py` — Settings 类
- `src/aegi_core/api/routes/kg.py` — 现有 KG 路由（参考风格）

## 实现范围

只做 PyKEEN 链接预测，不做 DoWhy 因果推断（那是 Phase 2）。

核心目标：从 Neo4j 提取三元组 → 训练 RotatE 模型 → 预测缺失链接 → 检测异常三元组 → API 暴露。

## 关键设计决策

### 1. PyKEEN 作为 optional dependency

```toml
# pyproject.toml
[project.optional-dependencies]
analytics = ["pykeen>=1.10"]
```

代码中 lazy import：
```python
def _ensure_pykeen():
    try:
        import pykeen
        return pykeen
    except ImportError:
        raise RuntimeError(
            "PyKEEN not installed. Run: pip install 'aegi-core[analytics]'"
        )
```

没装 PyKEEN 时，API 返回 `501 Not Implemented`，不影响其他功能。

### 2. 模型缓存策略

训练好的模型缓存在内存中（dict[case_uid, model]）。不做文件持久化（Phase 1 简单实现）。如果 case 的 KG 有更新，需要重新训练。

### 3. 最小三元组数检查

三元组数 < `settings.pykeen_min_triples`（默认 50）时，跳过训练，返回提示信息。图太小训练出来没意义。

## 实现顺序

### Step 1：Settings 新增

```python
# settings.py 新增
pykeen_default_model: str = "RotatE"
pykeen_embedding_dim: int = 128
pykeen_num_epochs: int = 100
pykeen_min_triples: int = 50
```

### Step 2：Neo4j 三元组提取

在 `infra/neo4j_store.py` 中新增一个方法：

```python
async def get_all_triples(self, case_uid: str) -> list[tuple[str, str, str]]:
    """提取 case 下所有三元组 (head_uid, relation_type, tail_uid)。

    Cypher:
    MATCH (h {case_uid: $case_uid})-[r]->(t {case_uid: $case_uid})
    RETURN h.uid AS head, type(r) AS relation, t.uid AS tail
    """
```

同时新增一个辅助方法获取实体名称映射：

```python
async def get_entity_names(self, case_uid: str) -> dict[str, str]:
    """返回 {uid: name} 映射，用于结果展示。

    Cypher:
    MATCH (n {case_uid: $case_uid})
    RETURN n.uid AS uid, coalesce(n.name, n.label, n.uid) AS name
    """
```

### Step 3：LinkPredictor 核心服务

新建 `services/link_predictor.py`：

```python
class LinkPredictor:
    """基于 PyKEEN 的知识图谱链接预测引擎。"""

    def __init__(self, neo4j: Neo4jStore) -> None:
        self._neo4j = neo4j
        self._models: dict[str, Any] = {}  # case_uid → trained pipeline

    async def train(
        self,
        case_uid: str,
        *,
        model_name: str | None = None,
        embedding_dim: int | None = None,
        num_epochs: int | None = None,
    ) -> TrainResult:
        """训练链接预测模型。

        流程：
        1. 从 Neo4j 提取三元组：neo4j.get_all_triples(case_uid)
        2. 检查三元组数 >= pykeen_min_triples，否则返回错误
        3. 构建 PyKEEN TriplesFactory：
           from pykeen.triples import TriplesFactory
           import numpy as np
           triples_array = np.array(triples, dtype=str)
           tf = TriplesFactory.from_labeled_triples(triples_array)
        4. 划分训练/测试集（80/20）：
           training, testing = tf.split([0.8, 0.2], random_state=42)
        5. 训练：
           from pykeen.pipeline import pipeline
           result = pipeline(
               training=training,
               testing=testing,
               model=model_name or settings.pykeen_default_model,
               model_kwargs={"embedding_dim": embedding_dim or settings.pykeen_embedding_dim},
               training_kwargs={"num_epochs": num_epochs or settings.pykeen_num_epochs},
               random_seed=42,
           )
        6. 提取评估指标：
           metrics = result.metric_results.to_dict()
           mrr = metrics.get("both.realistic.inverse_harmonic_mean_rank", 0)
           hits_at_1 = metrics.get("both.realistic.hits_at_1", 0)
           hits_at_10 = metrics.get("both.realistic.hits_at_10", 0)
        7. 缓存模型：self._models[case_uid] = result
        8. 返回 TrainResult
        """

    async def predict_missing_links(
        self,
        case_uid: str,
        *,
        top_k: int = 20,
        min_score: float = 0.5,
    ) -> list[PredictedLink]:
        """预测缺失链接。

        流程：
        1. 检查模型是否已训练，未训练则报错提示先调 train
        2. 获取 entity_names 映射
        3. 用 PyKEEN 的 predict_all() 或手动构造候选三元组：
           model = self._models[case_uid].model
           tf = self._models[case_uid].training  # TriplesFactory

           # 方法：对所有实体对 + 所有关系类型打分
           # PyKEEN 提供 predict_target 等便捷方法
           from pykeen.predict import predict_all
           predictions = predict_all(model=model, triples_factory=tf)

        4. 过滤掉已存在的三元组
        5. 按分数降序取 top_k
        6. 分数归一化到 0~1，统一用 sigmoid：score = 1 / (1 + exp(-raw_score))。不要用 min-max（依赖当前批次，结果不稳定）。
        7. 过滤 min_score 以下的
        8. 附上实体名称，返回 list[PredictedLink]

        ⚠️ 不要用 predict_all()！复杂度 O(entities² × relations)，100 实体 × 3 关系 = 30000 候选，
        500 实体就是 75 万个，会 OOM。Phase 1 统一用 predict_target 逐关系类型预测：
        
        ```python
        from pykeen.predict import predict_target
        all_predictions = []
        for relation in tf.relation_to_id:
            for entity in tf.entity_to_id:
                # predict tail given (entity, relation, ?)
                preds = predict_target(
                    model=model, head=entity, relation=relation,
                    triples_factory=tf,
                )
                all_predictions.append(preds)
        ```
        
        如果实体数 > 200，只对 top-N 高连接度实体做预测，并在响应中注明。
        """

    async def predict_for_entity(
        self,
        case_uid: str,
        entity_uid: str,
        *,
        direction: str = "both",
        top_k: int = 10,
    ) -> list[PredictedLink]:
        """预测某个实体的缺失关系。

        用 PyKEEN 的 predict_target（entity 作为 head）
        和 predict_target（entity 作为 tail）。
        合并结果，按分数降序取 top_k。
        """

    async def detect_anomalous_triples(
        self,
        case_uid: str,
        *,
        threshold: float = 0.1,
    ) -> list[AnomalousTriple]:
        """检测异常三元组。

        流程：
        1. 获取所有已存在的三元组
        2. 用模型对每个三元组打分
        3. 分数低于 threshold 的 = 异常（不符合图结构模式）
        4. 按分数升序返回（最异常的排最前）
        """
```

### Step 4：API 路由

新建 `api/routes/links.py`：

```python
router = APIRouter(prefix="/cases/{case_uid}/links", tags=["link-prediction"])

# POST /cases/{case_uid}/links/train
#   body: {model_name?, embedding_dim?, num_epochs?}
#   → TrainResult
#   如果 PyKEEN 未安装，返回 501

# GET /cases/{case_uid}/links/predictions
#   query: top_k=20, min_score=0.5
#   → {"predictions": list[PredictedLink]}
#   如果未训练，返回 400 提示先训练

# GET /cases/{case_uid}/links/predictions/{entity_uid}
#   query: direction=both, top_k=10
#   → {"predictions": list[PredictedLink]}

# GET /cases/{case_uid}/links/anomalies
#   query: threshold=0.1
#   → {"anomalies": list[AnomalousTriple]}
```

修改 `api/main.py`：注册 links router。

### Step 5：事件集成（轻量）

在 `train()` 方法末尾，如果预测到高置信度缺失链接（score > 0.8），emit 事件：

```python
from aegi_core.services.event_bus import get_event_bus, AegiEvent

# 训练完成后自动跑一次预测
top_predictions = await self.predict_missing_links(case_uid, top_k=5, min_score=0.8)
if top_predictions:
    bus = get_event_bus()
    await bus.emit(AegiEvent(
        event_type="link.predicted",
        case_uid=case_uid,
        payload={
            "summary": f"发现 {len(top_predictions)} 条高置信度潜在关联",
            "predictions": [
                {"head": p.head_name, "relation": p.relation,
                 "tail": p.tail_name, "score": p.score}
                for p in top_predictions
            ],
        },
        severity="medium",
        source_event_uid=f"pykeen:{case_uid}:train",
    ))
```

### Step 6：测试

1. `tests/test_link_predictor.py`（mock Neo4j + 条件跳过）：

```python
import pytest
pykeen = pytest.importorskip("pykeen")  # 没装 PyKEEN 自动跳过
```

测试用例：
- `test_train_success` — 构造 100+ 三元组，训练成功，返回 TrainResult 且 MRR > 0
- `test_train_too_few_triples` — 三元组 < 50，返回错误/跳过
- `test_predict_missing_links` — 训练后预测，返回非空列表，每条有 head/relation/tail/score
- `test_predict_for_entity` — 指定实体预测，返回结果
- `test_detect_anomalies` — 训练后检测异常，返回列表
- `test_predict_without_training` — 未训练时预测，抛出合适的错误

2. `tests/test_links_api.py`（mock LinkPredictor）：
- `test_train_endpoint` — POST train 返回 200
- `test_predictions_endpoint` — GET predictions 返回列表
- `test_entity_predictions_endpoint` — GET predictions/{entity_uid}
- `test_anomalies_endpoint` — GET anomalies
- `test_pykeen_not_installed` — mock ImportError，返回 501

3. 测试数据构造：

```python
def _make_test_triples(n: int = 100) -> list[tuple[str, str, str]]:
    """构造测试用三元组。

    生成一个小型知识图谱：
    - 10 个实体：entity_0 ~ entity_9
    - 3 种关系：allies_with, opposes, trades_with
    - 随机生成 n 条三元组
    """
    import random
    random.seed(42)
    entities = [f"entity_{i}" for i in range(10)]
    relations = ["allies_with", "opposes", "trades_with"]
    triples = set()
    while len(triples) < n:
        h = random.choice(entities)
        r = random.choice(relations)
        t = random.choice(entities)
        if h != t:
            triples.add((h, r, t))
    return list(triples)
```

## 关键约束

- **PyKEEN 是 optional dependency**：lazy import，没装时 API 返回 501，不影响其他功能
- **不修改现有代码的行为**：只在 `neo4j_store.py` 新增 2 个方法，不改现有方法
- **模型缓存在内存**：Phase 1 不做文件持久化，重启后需要重新训练
- **大图保护**：实体数 > 500 时，`predict_missing_links` 应该限制候选数量或给出警告
- **测试用 `pytest.importorskip("pykeen")`**：没装 PyKEEN 的环境自动跳过，不 fail
- **现有测试不能 break**：实现完成后跑全量 pytest，确保 0 failed

## 验收标准

1. 在安装了 PyKEEN 的环境中：`pytest tests/test_link_predictor.py tests/test_links_api.py` 全绿
2. 在未安装 PyKEEN 的环境中：上述测试自动跳过，不 fail
3. `pytest` 全量测试 0 failed
4. API 端点可通过 curl 手动验证（需要 Neo4j 有数据）
5. `POST /cases/{case_uid}/links/train` 能成功训练并返回 MRR 指标
