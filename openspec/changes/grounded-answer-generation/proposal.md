<!-- Author: msq -->

## Why

chat 端点当前回答是硬编码字符串 `f"基于 {len(citations)} 条证据的分析结果。"`，
从未调用 LLM 基于检索到的证据生成实际分析。需要参考 STORM grounded QA 模式，
让 LLM 基于编号证据片段生成带内联引用的回答。

## What Changes

- answer_renderer 新增证据格式化（编号 [1][2]…）和 LLM grounded 回答生成。
- chat.py 替换硬编码字符串为 LLM 生成的 grounded answer。
- 回答中的 [N] 引用回映到实际 EvidenceCitation。

## Capabilities

### Modified Capabilities

- `conversational-analysis-evidence-qa`：从模板字符串升级为 LLM grounded 回答

## Dependencies

- Hard dependency: `answer_renderer.py`（现有 hallucination gate 保留）
- Hard dependency: `LLMClient`（已有 infra）

## Impact

- `code/aegi-core/src/aegi_core/services/answer_renderer.py`
- `code/aegi-core/src/aegi_core/api/routes/chat.py`
