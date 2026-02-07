<!-- Author: msq -->

## Decisions

### 1. LLM ACH 分析输出 schema

```python
class AssertionJudgment(BaseModel):
    assertion_uid: str
    relation: Literal["support", "contradict", "irrelevant"]
    reason: str  # 一句话理由

class ACHAnalysisResult(BaseModel):
    hypothesis_text: str
    judgments: list[AssertionJudgment]
```

LLM 返回 JSON，Pydantic 校验。从 judgments 计算 supporting/contradicting/gap_list/coverage/confidence。

### 2. Prompt 设计

系统 prompt 要求 LLM 扮演情报分析师，对每个 assertion 逐一判断与假设的关系。
输入：hypothesis_text + assertions 列表（uid + value）。
输出：JSON `ACHAnalysisResult`。

### 3. 无降级策略

与 GraphRAG pipeline 一致：LLM 不可用 = hard error，不 fallback 到规则引擎。
`_stage_hypothesis_sync` 删除，`run_full` 同步路径的 hypothesis 阶段改为 skip。

### 4. 调用点改造

| 调用点 | 当前 | 改后 |
|--------|------|------|
| `_hypothesis_with_llm` | LLM 生成 + 规则 ACH | LLM 生成 + LLM ACH |
| `_stage_hypothesis_sync` | 规则 ACH | 删除 |
| `run_full` sync | 调 `_stage_hypothesis_sync` | skip hypothesis 阶段 |
| API `score_hypothesis` | 规则 `analyze_hypothesis` | LLM `analyze_hypothesis_llm` |
| API `generate_hypotheses` | `svc_generate` (规则 ACH) | `svc_generate` 内部改用 LLM ACH |

### 5. 保留 `analyze_hypothesis` 签名

旧的规则版 `analyze_hypothesis()` 保留但标记 deprecated，仅供测试 fixture 使用。
新增 `async analyze_hypothesis_llm()` 作为主路径。
