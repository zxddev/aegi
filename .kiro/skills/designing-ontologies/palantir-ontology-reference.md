# Palantir Ontology Reference

Palantir Foundry 的 Ontology 是一个操作型本体层。核心定位：**组织的数字孪生**，同时服务人类用户和 AI Agent。

## OOSD 范式（为什么用本体）

来源：Peter Wilczynski（Palantir Ontology System 产品负责人）博文。

传统企业软件优化组件（component-centric），系统层面性能停滞。OOSD 的解法：**将复杂性推入 Ontology 共享层**。

核心论点：
1. **It's an ontology problem, not an AI problem** — 企业 AI 的瓶颈不是模型，而是缺少统一的决策中心本体
2. **Single language** — Ontology 可用图形（应用 UI）、口语（业务描述）、编程（OSDK 代码）三种形式表达
3. **知识复合** — 新应用复用已有集成，翻译只发生一次，边际成本趋零
4. **Defragment the enterprise** — 替代孤立组件，形成整体决策系统

```
传统：App A ←→ [DB₁][API₁]   每个应用独立集成，N×M 倍增长
OOSD：App A/B/C/AI ──→ [Ontology] ──→ 统一数据/逻辑/行动/安全
```

## 决策三要素模型

每个决策 = Data + Logic + Action。Ontology 必须建模全部三者：

```
Data (名词)   →  Objects, Properties, Links, Object Sets
Logic (推理)  →  Functions, AIP Logic, ML Models
Action (动词) →  Action Types, Webhooks, Writeback
```

操作系统闭合 Action 环路；分析系统止步于 Logic。

## 完整概念模型（七大元素）

```
Ontology
├── Object Types      现实实体/事件的 schema
├── Properties        Object Type 的特征字段
├── Link Types        两个 Object Type 之间的关系
├── Action Types      结构化修改操作（Parameters + Rules + Submission Criteria + Side Effects）
├── Functions         服务端代码（TS/Python），读写 Ontology + 调用外部 API
├── Interfaces        跨 Object Type 的多态抽象（共享属性，类比 OOP 接口）
└── Materialization   源数据 + 用户编辑的合并快照
```

### Interfaces 设计要点

```
Interface: Facility
  shared properties: name, location, capacity
  implements: Airport, Manufacturing Plant, Maintenance Hangar
```

- 工作流面向 Interface 编程，不绑定具体 Object Type
- 设计时识别"多个 Object Type 共享的属性形状"→ 提取为 Interface

### Functions 设计要点

- 复杂业务逻辑放 Functions，不放应用层
- Function-backed Action：声明式规则无法表达时，用代码实现
- Function-backed Column：Workshop 表格中的实时派生列

## Action Types 设计

### 分类

| 按操作 | 按实现 |
|---|---|
| Create / Edit / Link / Delete / Bulk | Form-based / Function-backed / With Side Effects |

### 四要素

```
Action Type
├── Parameters          用户输入（对象选择、文本、下拉框）
├── Rules               参数 → Ontology 编辑的逻辑
├── Submission Criteria  权限 + 业务验证（如 start_timestamp > now()）
└── Side Effects        通知 + Webhooks
```

### Webhook 事务性

- **Writeback Webhook**：外部失败 → Ontology 不变更（准事务）
- **Side Effect Webhook**：Ontology 变更后触发，失败不回滚

### Writeback 原理

不直接编辑源数据，使用独立 writeback 层：源数据 + 用户编辑 → Materialization（合并快照）→ 下游消费。全部版本化、可审计。

## AIP 与 Ontology 的交互（设计 AI 工具面）

设计 Ontology 时需要考虑 AI Agent 如何使用它：

- **Actions 自动作为 AI tools 暴露** — 无需额外配置
- **边界推理** — 传入特定 Objects 作为变量，AI 只在该上下文内推理
- **默认 human-in-the-loop** — AI 暂存决策，人类审核后执行
- **人的工具 = AI 的工具** — 同一套 Actions 同时服务人和 AI

设计启示：Action 的命名、参数、验证逻辑要同时对人和 AI 友好。

## Object Type 设计规则

### 主键（id）

- **string 类型，无例外**
- **由对象自身属性构成**，不依赖外部对象
- **独立 `id` 列**，即使已有唯一列
- **不 hash**，**不从 id 反推属性**

```
✅ id = customer_id
✅ id = customer_id + maintenance_job + maintenance_timestamp
❌ id = uuid_generated_at_pipeline_runtime
❌ id = sha256(...)
```

### 外键

格式：`{foreign_object_type}_id` 或 `{link_api_name}_{foreign_object_type}_id`

### 命名

- 自然语言业务概念，避免缩写（`Aircraft` 不是 `AC`）
- 不用 `[tag]` 前缀 → 用 Groups 组织
- 不用版本后缀（`Message_v2` 是坏实践）
- 全平台一致：`prediction.py` → `Prediction` dataset → `Prediction` Object Type

### 属性

- 最小化：可从父对象推导的不重复存
- 时间戳：`{verbed}_at_timestamp`
- 操作者：`{verbed}_by_user`
- 成熟度：Experimental → Active → Deprecated

### 可编辑性

仅在必要时开启。不可变数据源、Pipeline 生成值不应可编辑。

## Link Type 设计规则

- 孤立对象 = 坏设计；蜘蛛网 = 同样坏
- 同类型自关联用有意义名称：`Manager` / `Direct Report`，不是 `Employee` / `Employee2`
- 复数端 API 名用复数：`employee.subordinates.all()`

## Action 设计规则

- 配置 Submission Criteria（权限 + 验证）
- 默认关闭 Revert Action（可能有副作用）
- 同一 Action 逻辑跨所有应用一致

## 安全设计考量

设计 Object Type 时需要预先规划安全边界：

- **行级安全**：Object Security Policies 或 Restricted Views（基于用户属性过滤对象实例）
- **列级安全**：Property Security Policies（敏感属性需要特定 Marking 才可见）
- **单元格级**：行 + 列组合
- **Markings 标记一次，全平台生效** — 设计时决定哪些属性需要标记
- **AI Agent 受同样安全约束** — 不需要为 AI 单独设计权限

## 设计流程

1. 描述用户/Agent 需要做什么**决策**
2. 提取名词 → Object Types
3. 提取动词 → Action Types
4. 映射关系 → Link Types
5. 识别共享形状 → Interfaces
6. 定义最小属性
7. 规划安全边界（哪些对象/属性需要行/列级控制）
8. 验证：用样本查询和领域专家确认

实用主义：能交付价值就是好设计。

## 与传统本体的关键差异

| 维度 | Palantir Ontology | OWL/RDF |
|---|---|---|
| 目标 | 操作决策（封闭世界） | 知识推理（开放世界） |
| 核心 | Object + Action | Triple (S-P-O) |
| 动态性 | Actions/Functions/Security | 静态 schema + 推理 |
| 多态 | Interfaces | rdfs:subClassOf |
| AI | Actions 自动作为 tools | 无原生集成 |
| 安全 | 内嵌（行/列/单元格级） | 事后叠加 |

## 来源

- [Ontology-Oriented Software Development（Wilczynski 博文）](https://blog.palantir.com/ontology-oriented-software-development-68d7353fdb12)
- [Connecting AI to Decisions（官方博客）](https://blog.palantir.com/connecting-ai-to-decisions-with-the-palantir-ontology-c73f7b0a1a72)
- [Palantir 社区设计原则帖](https://community.palantir.com/t/ontology-and-pipeline-design-principles/5481)
- [Palantir 官方架构文档](https://palantir.com/docs/foundry/object-backend/overview/)
- [Palantir LLM 平台摘要](https://www.palantir.com/docs/foundry/getting-started/foundry-platform-summary-llm)
- [Object/Property Security Policies](https://palantir.com/docs/foundry/object-permissioning/object-security-policies/)
- [Restricted Views](https://palantir.com/docs/foundry/security/restricted-views/)
- [Action Types 文档](https://palantir.com/docs/foundry/action-types/overview/)
- [Webhooks 文档](https://palantir.com/docs/foundry/action-types/webhooks/)
- [Object Types 文档](https://palantir.com/docs/foundry/object-link-types/object-types-overview/)
