<!-- Author: msq -->

## 1. 查询规划

- [x] 1.1 新增 `services/query_planner.py`（NL -> QueryPlanV1）
- [x] 1.2 增加风险标记（证据不足/时间范围冲突/来源不足）

## 2. 回答渲染

- [x] 2.1 新增 `services/answer_renderer.py`（AnswerV1）
- [x] 2.2 增加 FACT/INFERENCE/HYPOTHESIS 分级逻辑
- [x] 2.3 增加 hallucination gate（无证据降级）

## 3. API

- [x] 3.1 新增 `POST /cases/{case_uid}/analysis/chat`
- [x] 3.2 新增 `GET /cases/{case_uid}/analysis/chat/{trace_id}`
- [x] 3.3 响应统一包含 trace_id 和 citations

## 4. 测试

- [x] 4.1 新增 `test_conversational_query_api.py`
- [x] 4.2 新增 `test_conversational_hallucination_gate.py`
- [x] 4.3 增加 `defgeo-chat-001` / `defgeo-chat-002` fixtures

## 5. 验收

- [x] 5.1 验证 FACT 响应均有有效证据引用
- [x] 5.2 验证证据不足时稳定返回 cannot_answer
