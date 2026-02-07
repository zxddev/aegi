<!-- Author: msq -->

## Context

chat.py 当前用硬编码字符串代替 LLM 回答。STORM 的 grounded QA 模式
（`format_search_results` → `AnswerQuestion` with inline citations → `extract_cited_info`）
是成熟方案，参考其算法但不引入依赖。

## Goals / Non-Goals

**Goals:**
- LLM 基于编号证据生成带 [N] 内联引用的回答
- 引用回映到 EvidenceCitation
- LLM 不可用 = 硬错误（不降级为模板字符串）

**Non-Goals:**
- 不改 claim_extractor（本次只改回答生成）
- 不改 query_planner
- 不加新 API 端点

## Decisions

### Decision 1: answer_renderer 新增两个函数

- `format_evidence_context(citations) -> (str, dict[int, EvidenceCitation])`
  编号格式化，返回上下文字符串 + 索引映射
- `generate_grounded_answer(question, context, llm, trace_id) -> AnswerV1`
  调用 LLM，提取引用编号，调用现有 `render_answer` 完成 hallucination gate

### Decision 2: prompt 设计

系统提示要求：
- 基于提供的编号证据回答问题
- 必须用 [N] 格式内联引用
- 不得编造证据中没有的信息
- 若证据不足以回答，明确说明

### Decision 3: 引用提取

用正则 `\[(\d+)\]` 从 LLM 回答中提取引用编号，映射回 EvidenceCitation。
未被引用的证据不进入 evidence_citations。
