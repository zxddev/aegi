<!-- Author: msq -->

# Parallel AI Execution Protocol

## 1. 目标

本协议用于“一个 AI 一个 openspec”并行开发，确保不破坏证据链合同与迁移链。

## 2. 角色

- **Schema 协调者（唯一）**：负责共享 migration 与 schema-change-request 合并。
- **Merge 协调者（唯一）**：负责分支合并顺序、router 冲突、依赖冲突处理。
- **Feature AI（多个）**：只实现各自 openspec，遵守公共合同。

## 3. 分支命名

- `feat/foundation-common-contracts`
- `feat/multilingual-evidence-chain`
- `feat/conversational-analysis-evidence-qa`
- `feat/automated-claim-extraction-fusion`
- `feat/ach-hypothesis-analysis`
- `feat/narrative-intelligence-detection`
- `feat/knowledge-graph-ontology-evolution`
- `feat/predictive-causal-scenarios`
- `feat/meta-cognition-quality-scoring`
- `coord/schema-owner`
- `coord/merge-owner`

## 4. 执行分层

### Gate-0（串行）

1. `foundation-common-contracts`
2. schema 协调者统一提交共享 migration
3. merge 协调者确认合同测试通过

### Layer-1（并行）

1. `automated-claim-extraction-fusion`
2. `multilingual-evidence-chain`
3. `conversational-analysis-evidence-qa`

### Layer-2（并行，依赖 Layer-1）

1. `knowledge-graph-ontology-evolution`（依赖 claim/assertion schema）
2. `ach-hypothesis-analysis`（依赖 source claim/assertion 输出）
3. `narrative-intelligence-detection`（依赖 source claim 输出）

### Layer-3（并行，依赖 Layer-2）

1. `predictive-causal-scenarios`（依赖 KG + ACH + narrative）
2. `meta-cognition-quality-scoring`（依赖所有上游能力输出）

## 5. 强制规则

1. 功能分支默认禁止新增 Alembic revision。
2. 所有 LLM 调用必须遵守 foundation 的 LLM governance 合同。
3. 所有回答级输出必须带 evidence citation 或降级标签。
4. 未通过公共 contract tests 的分支禁止合并。

## 6. 合并顺序与冲突处理

1. 仅 merge 协调者可向主干执行最终合并。
2. 合并顺序必须按 Gate-0 -> Layer-1 -> Layer-2 -> Layer-3。
3. router 注册冲突由 merge 协调者统一改 `api/main.py`。
4. 依赖冲突（`pyproject.toml`）由 merge 协调者统一锁定版本。

## 7. PR 最小门禁

1. 对应 openspec `tasks.md` 至少完成一个完整端到端子流。
2. 通过公共 contract tests。
3. 通过本功能回归 tests。
4. 提供变更证据：关键日志/测试结果/失败处置。

## 8. 协调者执行方式

默认执行方式如下：

1. **Schema 协调者**：独立 AI 会话（`coord/schema-owner` 分支）执行；人工仅做最终审批。
2. **Merge 协调者**：独立 AI 会话（`coord/merge-owner` 分支）执行合并与冲突处理；人工可接管最终合并。
3. **人工兜底**：当 CI 连续 2 次冲突未解或迁移链异常时，自动切换人工接管。

若团队选择纯人工模式，需满足：

1. 按本协议分层顺序手工合并。
2. 保持同等门禁（contract tests + feature tests）。
