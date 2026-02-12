# AEGI 首轮全面审查 — 白泽评审总结

> 审查日期：2026-02-11
> 审查员：白泽（全栈架构师 + AI算法工程师）

---

## 一、整体判断

AEGI 的代码量和模块覆盖面已经相当可观，情报分析的核心 pipeline（OSINT → 声明提取 → 实体消歧 → KG → ACH → 因果推理 → 叙事检测）骨架已成型。但当前系统本质上仍是一个**被动式分析引擎**，距离"主动式情报助手"还有关键差距。

**一句话总结：骨架扎实，但血管没通。**

---

## 二、四大审查结论

### 1. 主动推送机制 — 🔴 核心缺失

这是最严重的问题。AEGI 的核心卖点是"主动式"，但主动推送链路的四个环节中，只有最后一个（消息投递）实现了：

| 环节 | 状态 |
|------|------|
| 事件产生（pipeline完成、OSINT采集完成等） | ❌ 无自动触发 |
| 关联匹配（事件 ↔ 专家关注领域） | ❌ 无订阅关系表 |
| 推送决策（过滤、去重、节流、优先级） | ❌ 完全缺失 |
| 消息投递（chat_inject / ws broadcast） | ✅ 已实现 |

`dispatch.py` 中的 `dispatch_and_notify()` 是唯一的主动推送函数，但**全项目没有任何代码调用它**。这是死代码。

### 2. Pipeline 编排 — 🟡 骨架可用，有运行时 bug

架构方向正确（pluggable stage + playbook + SSE streaming），但有几个会导致运行时崩溃的问题：

- **P0**: `adversarial_evaluate` stage 传参类型错误，playbook 模式下必崩
- **P1**: OSINT 采集结果未回流 `ctx.source_claims`，`osint_deep` playbook 跑不通
- **P2**: `report_generate` 永远被 skip
- **P7**: Playbook YAML 未在启动时加载，自定义 playbook 不生效
- 存在两套重复的 pipeline 执行路径（新旧并存），维护风险高

### 3. MCP Gateway — 🟡 可用但有安全隐患

职责清晰（策略执行 + 错误格式化 + 审计），但：

- **P0**: Gateway 无任何鉴权，裸露在网络上
- **P1**: 策略执行不一致（只有 `archive_url` 走策略引擎）
- **P1**: OpenClaw 端的 9 个工具端点完全无审计记录
- **P1**: 双层审计（Gateway JSONL + Core PG）无法关联
- 名为 "MCP Gateway" 但未实现 MCP 协议

### 4. 数据模型与知识图谱 — 🟡 设计合理，一致性有风险

三存储分工合理（PG 权威源 + Neo4j 图推理 + Qdrant 向量检索），但：

- **高风险**: PG ↔ Neo4j / Qdrant 无事务绑定，写入失败无补偿机制
- **中风险**: 实体消歧结果未自动回写 Neo4j，图谱持续存在重复节点
- **中风险**: 跨语言对齐结果无持久化，每次重新计算
- Alembic migration 与模型一致，无遗漏

---

## 三、优先级排序

### 🔴 立即修复（阻塞核心功能）

| # | 问题 | 来源 | 影响 |
|---|------|------|------|
| 1 | `adversarial_evaluate` stage 签名不匹配 | Pipeline | playbook 模式必崩 |
| 2 | OSINT claims 未回流 ctx.source_claims | Pipeline | osint_deep 跑不通 |
| 3 | Playbook YAML 未在启动时加载 | Pipeline | 自定义 playbook 不生效 |
| 4 | Gateway 无鉴权 | MCP Gateway | 安全漏洞 |

### 🟠 短期必须（实现"主动式"核心）

| # | 问题 | 说明 |
|---|------|------|
| 5 | 事件总线 | 内部 pub/sub，让 pipeline/OSINT/cron 产生的事件能被统一捕获 |
| 6 | 订阅关系表 | user ↔ case/topic 的关注关系，决定事件推给谁 |
| 7 | 推送决策引擎 | 过滤、去重、节流、优先级，避免消息轰炸 |
| 8 | 自动触发接入 | 将 dispatch_and_notify() 接入事件总线消费端 |
| 9 | WS 心跳保活 | 避免长连接静默断开 |

### 🟡 中期优化

| # | 问题 | 说明 |
|---|------|------|
| 10 | PG ↔ Neo4j/Qdrant 一致性 | outbox 模式或后台 reconciliation job |
| 11 | 实体消歧结果自动回写 Neo4j | apply_merge_groups() |
| 12 | 跨语言对齐结果持久化 | entity_links 表 |
| 13 | 合并两套 pipeline 执行路径 | 消除重复代码 |
| 14 | OpenClaw 端点补齐审计 | 9 个工具端点无 ToolTrace |
| 15 | 共享契约包 | MCP Gateway 与 Core 之间的接口契约 |
| 16 | Pipeline tracker 持久化 + 重试 | 生产环境可靠性 |

---

## 四、架构建议：实现"主动式"的最短路径

要让 AEGI 从"被动分析引擎"变成"主动情报助手"，核心是补齐**事件驱动层**：

```
┌─────────────────────────────────────────────────────────┐
│                    Event Bus (新增)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Pipeline  │  │  OSINT   │  │  Cron    │  ← 事件生产者│
│  │ Complete  │  │ Complete │  │ Trigger  │              │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘              │
│        └──────────────┼──────────────┘                   │
│                       ▼                                  │
│              ┌────────────────┐                          │
│              │ Subscription   │ ← user ↔ case/topic     │
│              │ Matcher        │                          │
│              └───────┬────────┘                          │
│                      ▼                                   │
│              ┌────────────────┐                          │
│              │ Push Decision  │ ← 过滤/去重/节流/优先级  │
│              │ Engine         │                          │
│              └───────┬────────┘                          │
│                      ▼                                   │
│              ┌────────────────┐                          │
│              │ dispatch.py    │ ← 已有，接入即可         │
│              │ notify_user()  │                          │
│              └────────────────┘                          │
└─────────────────────────────────────────────────────────┘
```

技术选型建议：
- Event Bus 初期可用内存 asyncio.Queue + 简单 pub/sub，不需要引入 Kafka/RabbitMQ
- 订阅关系表加到 PostgreSQL，一张 `subscriptions` 表即可
- 推送决策引擎先做最简版：去重（同事件不重复推）+ 节流（每用户每小时上限）

---

## 五、下一步行动建议

1. 让 Claude Code 先修 4 个 P0 bug（#1-#4），确保现有功能能跑
2. 主人和我一起设计事件驱动层的详细方案（#5-#8）
3. 设计完成后拆分任务给 Claude Code 实现

---

_白泽审毕。_
