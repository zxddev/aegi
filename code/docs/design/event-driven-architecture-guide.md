# AEGI 事件驱动层 — 架构指导

> 作者：白泽（架构师）
> 日期：2026-02-11
> 用途：指导 CC 完成详细设计，CC 不得偏离本文档的核心原则

---

## 一、目标

让 AEGI 从"被动分析引擎"变成"主动情报助手"。

核心链路：**事件产生 → 关联匹配 → 推送决策 → 消息投递**

目前只有最后一环（dispatch.py / chat_inject）已实现，前三环需要补齐。

---

## 二、核心原则

### 1. 不引入新中间件
- 不用 Kafka、RabbitMQ、NATS 等外部消息队列
- 用 Python asyncio 内存事件总线，与现有 FastAPI async 架构一致
- 后期如果需要扩展，再考虑替换，但接口要预留

### 2. 三级匹配，渐进增强
- **规则匹配**（必须有）：专家订阅了 case/topic/地区/实体，事件命中就推
- **语义匹配**（必须有）：用现有 Qdrant + BGE-M3 做事件与专家兴趣的向量相似度
- **LLM 精排**（可选增强）：用 Instructor structured output 让 LLM 判断事件对专家的价值

三级是渐进的，不是串行必经。规则匹配命中高置信度的直接推，不确定的才走语义和 LLM。

### 3. 宁可漏推不可轰炸
- 推送决策必须有节流机制
- 每个专家每小时推送上限（可配置）
- 同一事件不重复推送
- 优先级排序：高优先级事件可以突破节流

### 4. 复用现有基础设施
- PostgreSQL：订阅关系表、事件日志表
- Qdrant：语义匹配（已有 aegi_chunks 集合，新增专家兴趣 profile 集合）
- LLMClient + Instructor：LLM 精排
- dispatch.py：消息投递（已有，接入即可）
- OpenClaw Gateway：最终推送通道

### 5. 可观测、可审计
- 每次推送决策都要记录：为什么推、推给谁、匹配了什么规则/相似度
- 专家可以反馈"有用/没用"，用于后续优化匹配策略

---

## 三、事件模型

### 事件类型（初期）

| 事件类型 | 触发点 | 说明 |
|----------|--------|------|
| `pipeline.completed` | PipelineOrchestrator.run_playbook() 完成后 | 分析流水线跑完了 |
| `osint.collected` | OSINTCollectStage 完成后 | 新的 OSINT 数据采集完成 |
| `claim.extracted` | ClaimExtractor 完成后 | 从新数据中提取了声明 |
| `entity.discovered` | EntityDisambiguator 完成后 | 发现了新实体或实体关系变化 |
| `hypothesis.updated` | HypothesisEngine 完成后 | 假设分析结果有更新 |
| `narrative.detected` | NarrativeBuilder 完成后 | 检测到新的叙事模式 |
| `anomaly.detected` | 未来扩展 | 检测到异常信号 |

### 事件结构

```python
class AegiEvent:
    event_type: str           # 如 "pipeline.completed"
    case_uid: str             # 关联的 case
    payload: dict             # 事件详情（灵活 schema）
    entities: list[str]       # 涉及的实体 uid 列表
    regions: list[str]        # 涉及的地区
    topics: list[str]         # 涉及的主题标签
    severity: str             # low / medium / high / critical
    source_event_uid: str     # 去重用，同一事件的唯一标识
    created_at: datetime
```

---

## 四、订阅模型

### 订阅关系

专家可以订阅：
- 特定 case（关注某个案例的所有动态）
- 特定实体（关注某个人物/组织/国家的相关事件）
- 特定地区（关注某个地理区域的事件）
- 特定主题（关注某类主题，如"核扩散"、"网络攻击"）
- 全局（接收所有高优先级事件）

### 订阅表设计方向

```
subscriptions:
  - user_id（专家）
  - sub_type（case / entity / region / topic / global）
  - sub_target（具体的 case_uid / entity_uid / region_code / topic_tag）
  - priority_threshold（只接收该优先级以上的事件）
  - enabled（开关）
```

### 专家兴趣 Profile

除了显式订阅，还需要一个隐式的兴趣向量：
- 基于专家历史查询、浏览、反馈，生成兴趣 embedding
- 存入 Qdrant 的专家 profile 集合
- 用于语义匹配：新事件 embedding vs 专家兴趣 embedding

初期可以简化：用专家订阅的实体/主题描述文本生成 embedding。

---

## 五、推送决策引擎

### 决策流程

```
新事件
  │
  ├─ 1. 规则匹配：遍历 subscriptions 表，找到匹配的专家
  │     命中 → 加入候选列表（附匹配原因）
  │
  ├─ 2. 语义匹配：事件 embedding vs 专家 profile embedding
  │     相似度 > 阈值 → 加入候选列表
  │
  ├─ 3. 合并去重：同一专家可能被多条规则命中，合并
  │
  ├─ 4. 节流检查：该专家最近是否已收到太多推送？
  │     超限 → 降级为摘要（攒一批再推）或丢弃低优先级
  │
  ├─ 5. LLM 精排（可选）：对不确定的候选，让 LLM 判断价值
  │
  └─ 6. 投递：调用 dispatch.py 的 notify_user()
```

### 节流策略

- 每用户每小时最大推送数（默认 10，可配置）
- critical 事件不受节流限制
- 被节流的事件进入"摘要队列"，定期合并推送

---

## 六、模块划分

| 新增模块 | 职责 | 位置 |
|----------|------|------|
| `services/event_bus.py` | 事件总线：注册/发布/订阅 | 纯内存 asyncio |
| `services/push_engine.py` | 匹配 + 决策 + 投递 | 核心逻辑 |
| `db/models/subscription.py` | 订阅关系表 | PostgreSQL |
| `db/models/event_log.py` | 事件日志表 | PostgreSQL |
| `db/models/push_log.py` | 推送日志表（审计） | PostgreSQL |

### 需要修改的现有模块

| 模块 | 改动 | 说明 |
|------|------|------|
| `services/pipeline_orchestrator.py` | 在 run_playbook 完成后 emit 事件 | 接入事件总线 |
| `services/stages/osint_collect.py` | 在采集完成后 emit 事件 | 接入事件总线 |
| `services/claim_extractor.py` | 在提取完成后 emit 事件 | 接入事件总线 |
| `openclaw/dispatch.py` | 被 push_engine 调用 | 无需大改，已有 notify_user |
| `api/main.py` | lifespan 中初始化 event_bus | 启动时注册 |

---

## 七、不要做的事

- 不要引入外部消息队列
- 不要做复杂的 ML 推荐模型（初期用规则 + 语义就够）
- 不要做前端（订阅管理先通过 API）
- 不要做降级逻辑（开发阶段让错误暴露）
- 不要过度设计事件 schema（payload 用 dict，保持灵活）
- 不要把推送决策做成同步阻塞（整个链路必须 async）

---

## 八、CC 的任务

基于以上架构指导，CC 需要输出：

1. **详细设计文档**：数据模型（完整 SQLAlchemy 定义）、接口定义、事件流序列图、配置项
2. **Alembic migration**：新增表的 migration
3. **代码实现**：event_bus.py、push_engine.py、新增 models、现有模块的 emit 接入
4. **测试**：每个模块的单元测试 + 端到端集成测试（事件产生 → 匹配 → 推送）

设计文档写入：`/home/user/workspace/gitcode/aegi/code/docs/design/event-driven-layer.md`

---

_白泽出品，CC 执行。_
