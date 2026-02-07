<!-- Author: msq -->

# aegi 本体与证据链设计规则

本规则是 aegi 项目的核心——所有代码改动都必须符合这些原则。违反任何一条红线等同于引入 bug。

## 1. 架构红线（任何阶段都不能破）

1. **Evidence-first + Archive-first**：任何进入对象层的断言/判断都必须绑定来源声称，再由 SourceClaim 回溯证据链。证据必须追溯到 Artifact 快照（固化版本），否则视为不合格。
2. **SourceClaim-first**：SourceClaim 是平台"可追责语义"的最小单位。先有 SourceClaim，再有 Assertion，再有 Judgment。不允许跳过。
3. **Action-only writes**：所有写入只能通过 Action 发生（校验 → 权限 → 审计 → 可回滚）。禁止绕过 Action 直接改数据库。
4. **工具外联统一走 Gateway**：外部访问必须经 `aegi-mcp-gateway`，策略可审计。
5. **派生索引可重建**：权威源在 PostgreSQL + 对象存储，所有派生索引（图谱、搜索、物化视图）必须可从权威源重建。

## 2. 本体设计原则

- **Ontology/Object-first**：系统流通的主产物是对象（Entity/Event/Relation/SourceClaim/Assertion），不是 markdown。报告只是一种渲染视图。
- **Deterministic IDs**：身份与版本分离。`artifact_identity_uid`（稳定身份）+ `artifact_version_uid`（本次采集内容）。禁止"同 URL = 同内容"的假设。
- **冲突是一等公民**：冲突不是注释里一句话，而是模型里的显式结构（`assertion.conflicts_with[]`）。允许多套并行解释（竞争性假设），必须标注证据与不确定性。
- **Agent 只产生结构化工件，不直接落库**：LLM 产出的候选实体/关系/断言，落库前必须经过 Schema 校验、规则校验、质量闸门、风险策略（高风险走 HITL）。
- **命名 = 自然语言**：Object Type、Property、Link、Action 的命名必须是业务人员能直接理解的自然语言，不是技术缩写。
- **属性最小化**：不复制可派生的数据。能通过 Link 或 Function 计算的，不存为 Property。

设计本体时，必须先加载 `designing-ontologies` skill。

## 3. 证据链完整性

引用链路必须完整闭合：
```
Judgment → Assertion → SourceClaim → Evidence → Chunk(anchor) → ArtifactVersion → ArtifactIdentity
```

- 每条 SourceClaim 必须有：evidence_uid、chunk_uid、quote、modality（confirmed/likely/alleged/denied/unknown）。
- 每条 Assertion 必须有：supporting_source_claim_uids[]、confidence、conflicts_with[]。
- 锚点（anchor_set）必须多选择器冗余（至少两种定位方式），支持健康检查与回退。

## 4. Action Type 设计

每个 Action 必须满足四要素：
1. **校验**：输入参数 + 业务规则校验
2. **权限**：谁能执行、在什么条件下
3. **审计**：完整的 ToolTrace 记录（who/when/what/why）
4. **可回滚**：支持撤销或补偿操作

Action 同时是 AI Agent 的工具面——设计时要考虑人类和 Agent 都能调用。

## 5. 前沿能力设计约束

### 5.1 因果推理与假设检验（ACH）
- 假设-证据关系必须可追溯，可导出解释路径。
- 支持竞争性假设并存，每个假设有独立的证据支持/反驳评分。
- 因果链必须显式建模（CAUSED_BY/FOLLOWS 关系），不能隐含在文本里。

### 5.2 叙事分析与信息战检测
- 叙事传播链可回放，冲突叙事可并存展示。
- Narrative 作为一等对象类型，关联到 SourceClaim 和传播路径。

### 5.3 元认知（偏见/盲区/可信度）
- 每个 Judgment 必须有可解释的可信度评分。
- 偏差和盲区提示必须可纳入分析流程闭环，不是事后附注。

### 5.4 预测分析
- 预警规则和输出必须有可解释依据，绑定到具体的 Assertion 和 Evidence。

## 6. 代码改动策略

- 优先"加法"：补字段、增模型、增模块。
- 谨慎"改法"：仅在局部复杂度过高时做小重构。
- 禁止"重写"：不推倒现有证据链主干。
- 核心竞争力不是"有 AI"，而是"AI 输出可回源、可审计、可回放、可质疑"。
