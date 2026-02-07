<!-- Author: msq -->

## 1. answer_renderer.py

- [x] 1.1 新增 `format_evidence_context(citations) -> tuple[str, dict[int, EvidenceCitation]]`
- [x] 1.2 新增 `generate_grounded_answer(question, evidence_context, index_map, llm, trace_id) -> AnswerV1`
- [x] 1.3 内部用正则提取 [N] 引用编号，映射回 EvidenceCitation

## 2. chat.py

- [x] 2.1 替换硬编码 answer_text 为 `generate_grounded_answer` 调用
- [x] 2.2 LLM 不可用时返回 cannot_answer（不降级为模板字符串）

## 3. 验收

- [x] 3.1 现有测试全部通过（纯单元测试通过，DB 相关测试因 PG 未启动跳过）
- [x] 3.2 ruff lint + format 通过
