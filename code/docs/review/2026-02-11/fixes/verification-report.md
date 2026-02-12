# 交叉验证报告 — CC-1/2/3 修复验证

验证人：CC-4 独立验证员
日期：2026-02-11

---

## 全量测试结果

```
uv run pytest tests/ -x -v
267 passed, 26 skipped, 2 warnings in 89.34s
```

所有测试通过。26 个 skip 均为基础设施依赖（SearXNG、Neo4j、LiteLLM 等），属正常。

---

## CC-1: AdversarialEvaluateStage 签名修复

### ✅ 通过

**代码审查** (`builtin.py:113-142`):

1. **类型映射正确**：`HypothesisV1.label → ACHResult.hypothesis_text`，`HypothesisV1.supporting_assertion_uids → ACHResult.supporting_assertion_uids`，`HypothesisV1.confidence → ACHResult.confidence` — 字段名和类型完全匹配。

2. **`confidence` 空值处理**：`hyp.confidence or 0.0` — `HypothesisV1.confidence` 类型为 `float | None`，`ACHResult.confidence` 类型为 `float`，`or 0.0` 正确处理了 `None` 情况。

3. **`aevaluate_adversarial()` 签名匹配**：
   - 函数签名：`(ach: ACHResult, assertions: list[AssertionV1], source_claims: list[SourceClaimV1], *, case_uid: str, trace_id: str | None = None, llm: LLMClient | None = None)`
   - 调用方式：`aevaluate_adversarial(ach, ctx.assertions, ctx.source_claims, case_uid=ctx.case_uid, llm=ctx.llm)`
   - ✅ 位置参数和关键字参数完全匹配

4. **返回值解构**：`adv, action, trace = await aevaluate_adversarial(...)` — 函数返回 `tuple[AdversarialResult, ActionV1, ToolTraceV1]`，三元组解构正确。

5. **遍历逻辑**：逐个遍历 `ctx.hypotheses`，为每个构造 `ACHResult` 后调用，与 `PipelineOrchestrator._run_adversarial_llm()` 的模式一致。

**无新 bug 引入。**

---

## CC-2: OSINT Claims 回流 + Playbook YAML 加载

### ✅ 通过

**问题 A — Claims 回流** (`osint_collect.py:53-59`):

1. **回流逻辑正确**：采集完成后检查 `result.source_claim_uids`，若非空则：
   - 存入 `ctx.config["osint_claim_uids"]`（保留原有行为）
   - 通过 `_load_claims()` 从 DB 加载 `SourceClaimV1` 对象
   - `ctx.source_claims.extend(loaded)` 合入上下文

2. **`_load_claims()` 实现正确** (`osint_collect.py:74-103`):
   - 使用 `sa.select(SourceClaim).where(SourceClaim.uid.in_(uids))` 查询
   - 转换为 `SourceClaimV1` Pydantic 对象，字段映射完整
   - 包含多语言字段（`language`, `original_quote`, `translation`, `translation_meta`）

3. **下游消费验证**：`ctx.source_claims` 被 `AssertionFuseStage`（line 59）、`NarrativeBuildStage`（line 159）等直接使用，类型为 `list[SourceClaimV1]`，与 `_load_claims()` 返回类型一致。

4. **`StageResult.output` 新增 `claims_loaded`**：`len(ctx.source_claims)` 反映加载后的总量，便于观测。

**问题 B — Playbook 加载** (`main.py:77-83`):

5. **`load_playbooks()` 已在 lifespan 中调用**：
   - 路径计算：`Path(__file__).resolve().parent.parent.parent.parent / "deploy" / "playbooks.yaml"` — 从 `api/main.py` 向上 4 级到 `aegi-core/`，拼接 `deploy/playbooks.yaml`，路径正确。
   - 条件加载：`if _pb_path.exists()` 防止文件不存在时报错。

6. **`playbooks.yaml` 内容验证**：
   - `default` playbook 包含 `report_generate` ✅
   - `deep` playbook 包含 `report_generate` ✅
   - `osint_deep` playbook 包含 `report_generate` ✅
   - `osint_deep` 首个 stage 为 `osint_collect` ✅

7. **`DEFAULT_STAGES`** (`playbook.py:19-28`)：包含 `report_generate` 作为第 8 个 stage ✅

**无新 bug 引入。**

---

## CC-3: ReportGenerateStage 跳过修复 + SSE progress 回调修复

### ⚠️ 通过（有小问题，不影响功能）

**问题 A — ReportGenerateStage** (`builtin.py:239-291`):

1. **`should_skip()` 修复正确** (line 242-244)：
   - 旧逻辑：`if not ctx.config.get("generate_report")` — `None` 为 falsy，总是跳过
   - 新逻辑：`if ctx.config.get("generate_report") is False` — 只有显式 `False` 才跳过
   - ✅ 语义正确

2. **`_PipelineCtx` duck-typing 兼容性**：
   - `_ReportContext` 需要：`case_uid`, `assertions`, `hypotheses`, `source_claims`, `narratives`, `judgments`
   - `_PipelineCtx` 提供：`case_uid`, `assertions`, `hypotheses`, `source_claims`, `narratives`, `judgments`（空列表）
   - ✅ 属性完全匹配

3. **⚠️ 小问题：`ReportGenerator` 实例化但未使用**：
   - Line 251: `generator = ReportGenerator()` 创建了实例但从未引用
   - 不影响功能，但属于死代码，建议清理

4. **section generator 调用**：`await fn(pipe_ctx, ctx.llm)` — 所有 section generator 签名为 `(ctx: _ReportContext, llm: LLMClient | None)`，duck-typing 兼容 ✅

**问题 B — SSE stages_completed** (`pipeline_stream.py:99-111`):

5. **修复逻辑正确**：
   - 新增 `completed_stages: list[str] = []` 局部变量（line 99）
   - `_on_progress` 回调中：当 `status in ("success", "skipped")` 且 stage 不在列表中时追加（line 102-103）
   - `tracker.update()` 传入 `stages_completed=list(completed_stages)` — 使用 `list()` 拷贝防止引用问题 ✅

6. **回调签名匹配**：`async def _on_progress(stage: str, status: str, pct: float, msg: str)` 与 `ProgressCallback = Callable[[str, str, float, str], Awaitable[None]]` 完全匹配 ✅

7. **执行时序正确**：`_on_progress` 在 `orch.run_playbook()` 执行期间被调用，此时 `completed_stages` 已存在且可变，不再依赖 `result` 变量 ✅

**总结：功能正确，仅有一处死代码（`generator = ReportGenerator()`），建议后续清理。**

---

## 综合结论

| 修复 | 状态 | 说明 |
|------|------|------|
| CC-1: AdversarialEvaluateStage 签名 | ✅ 通过 | 类型映射正确，调用签名完全匹配 |
| CC-2: OSINT 回流 + Playbook 加载 | ✅ 通过 | Claims 正确回流到 ctx.source_claims，playbook 加载逻辑完整 |
| CC-3: Report 跳过 + SSE progress | ✅ 通过 | should_skip 语义修正，SSE 回调逻辑正确（有一处死代码待清理） |

全量测试 267 passed / 26 skipped / 0 failed。三个修复均未引入新 bug。
