# Pipeline 编排系统审查报告

> 审查日期：2026-02-11
> 审查范围：pipeline_orchestrator / pipeline_tracker / stages/ / pipelines.py / pipeline_stream.py

---

## 1. Stage 实现状态表

| # | Stage 名称 | 注册类 | 文件 | 实现状态 | 说明 |
|---|-----------|--------|------|---------|------|
| 1 | `assertion_fuse` | `AssertionFuseStage` | `builtin.py:53` | **完整** | 同步规则融合 + 可选 LLM 语义冲突检测 |
| 2 | `hypothesis_analyze` | `HypothesisAnalyzeStage` | `builtin.py:86` | **完整** | 调用 `hypothesis_engine.generate_hypotheses()` |
| 3 | `adversarial_evaluate` | `AdversarialEvaluateStage` | `builtin.py:113` | **有问题** | 签名不匹配（见 P0） |
| 4 | `narrative_build` | `NarrativeBuildStage` | `builtin.py:134` | **完整** | 异步 + 可选 embedding |
| 5 | `kg_build` | `KgBuildStage` | `builtin.py:156` | **完整** | 调用 `kg_mapper.build_kg_triples` + Neo4j 写入 |
| 6 | `forecast_generate` | `ForecastGenerateStage` | `builtin.py:180` | **完整** | 异步 + 可选 LLM |
| 7 | `quality_score` | `QualityScoreStage` | `builtin.py:202` | **完整** | 同步规则评分 |
| 8 | `report_generate` | `ReportGenerateStage` | `builtin.py:225` | **完整** | 从 pipeline ctx 构建内存报告 |
| 9 | `hypothesis_multi_perspective` | `MultiPerspectiveHypothesisStage` | `multi_perspective.py:14` | **完整** | STORM 多 Persona 假设生成 |
| 10 | `osint_collect` | `OSINTCollectStage` | `osint_collect.py:9` | **可用但耦合重** | 需要 config 注入 searxng/db_session/qdrant |

## 2. 数据流图

```
                    ┌─────────────────┐
                    │  osint_collect   │ (可选，osint_deep playbook)
                    │  → config中存    │
                    │  osint_claim_uids│
                    └────────┬────────┘
                             │ (注意：新 claims 未合入 ctx.source_claims!)
                             ▼
┌──────────────┐    ┌─────────────────┐
│ source_claims│───▶│ assertion_fuse   │
│ (输入)       │    │ → ctx.assertions │
└──────────────┘    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │hypothesis_analyze│  (或 hypothesis_multi_perspective)
                    │→ ctx.hypotheses  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │adversarial_eval  │
                    │→ 评估结果(不回写)│
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ narrative_build  │
                    │→ ctx.narratives  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │    kg_build      │
                    │→ Neo4j triples   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │forecast_generate │
                    │→ ctx.forecasts   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  quality_score   │
                    │→ 质量评分        │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ report_generate  │ (可选，需 config.generate_report=true)
                    │→ markdown 报告   │
                    └─────────────────┘
```

## 3. 发现的问题

### P0 — `adversarial_evaluate` stage 签名不匹配

`builtin.py:125-128`:
```python
sr = await _safe(self.name, aevaluate_adversarial(
    ctx.hypotheses, ctx.assertions, ctx.source_claims,
    case_uid=ctx.case_uid, llm=ctx.llm,
))
```

但 `pipeline_orchestrator.py:546` 中旧路径调用的是：
```python
adv, _, _ = await aevaluate_adversarial(
    ach,  # 单个 ACHResult
    assertions, source_claims, ...
)
```

`ctx.hypotheses` 是 `list[HypothesisV1]`，而 `aevaluate_adversarial` 的第一个参数期望的是单个 `ACHResult`。这个 stage 在 playbook 模式下运行时会直接报错。

### P1 — `osint_collect` 采集结果未回流到 pipeline 数据流

`osint_collect.py:54-57`:
```python
if result.source_claim_uids:
    ctx.config["osint_claim_uids"] = result.source_claim_uids
```

OSINT 采集到的 source_claim_uids 只存到了 `ctx.config` 里，没有加载为 `SourceClaimV1` 对象合入 `ctx.source_claims`。后续 `assertion_fuse` 拿到的 `ctx.source_claims` 仍然是空的（或者只有调用者传入的初始值）。`osint_deep` playbook 实际上跑不通完整链路。

### P2 — `report_generate` 不在 default playbook 中且永远被 skip

`playbooks.yaml` 的 default playbook 只有 7 个 stage，不含 `report_generate`。`builtin.py` 中 `ReportGenerateStage.should_skip` 检查 `ctx.config.get("generate_report")`，但没有任何 playbook 配置了这个参数。报告生成 stage 实际上永远被 skip。

### P3 — `pipeline_stream.py` 中 `_on_progress` 回调有 bug

`pipeline_stream.py:106-107`:
```python
stages_completed=[
    s for s in tracker.get(run_id).stages_total
    if s in [sr.stage for sr in result.stages if sr.status == "success"]
] if 'result' in dir() else [],
```

`'result' in dir()` 检查的是当前闭包的局部变量，但 `result` 在 `_on_progress` 被调用时可能还没赋值（它在 `await orch.run_playbook()` 返回后才有值）。这个回调在 pipeline 执行过程中被调用，此时 `result` 尚未定义，所以 `stages_completed` 永远是 `[]`。不过这不会崩溃，只是 SSE 中间进度的 `stages_completed` 字段始终为空。

### P4 — pipeline_tracker 无持久化、无失败重试

- `PipelineTracker` 是纯内存 dict，进程重启后所有 run state 丢失
- 没有任何重试机制 — stage 失败后直接记录 error 状态，pipeline 继续执行下一个 stage
- 没有 stage 级别的超时控制
- `cleanup` 在 `run_streamed` 中 60 秒后自动调用，但如果 SSE 连接断开，run state 可能永远不被清理

### P5 — `run_streamed` 绕过 DI 直接实例化依赖

`pipeline_stream.py:67-69`:
```python
llm = get_llm_client()
neo4j = get_neo4j_store()
orch = PipelineOrchestrator(llm=llm, neo4j_store=neo4j)
```

这里直接调用 `get_llm_client()` / `get_neo4j_store()` 而不是通过 FastAPI `Depends`，因为它在 async generator 内部。这意味着测试时无法通过 `app.dependency_overrides` 注入 mock。

### P6 — 两套并行的 pipeline 执行路径

`PipelineOrchestrator` 有三个入口：
1. `run_playbook()` — 新的 pluggable stage 路径
2. `run_full_async()` — 旧的硬编码异步路径
3. `run_full()` — 旧的同步路径

`run_full_async()` 和 `run_full()` 中的逻辑与 `builtin.py` 中的 stage 实现是重复的。两套代码可能随时间漂移。

### P7 — Playbook YAML 未在启动时加载

`playbook.py` 中 `load_playbooks()` 需要显式调用，但没看到 `main.py` 的 startup 事件中调用它。`get_playbook("osint_deep")` 会 fallback 到 `Playbook.default()`，即 7-stage default，而不是 YAML 中定义的 osint_deep。

---

## 4. SSE/WebSocket 流式输出状态

| 通道 | 端点 | 状态 |
|------|------|------|
| SSE pipeline 启动 | `POST /cases/{id}/pipelines/run_streamed` | **已实现**，但 progress 回调有 bug (P3) |
| SSE pipeline 订阅 | `GET /cases/{id}/pipelines/runs/{id}/stream` | **已实现**，含 keepalive |
| SSE chat | `POST /chat/stream` | **已实现**，轻量 LLM 直通 |
| WS push | `ws_manager.notify()` | **已实现**，支持 `pipeline_progress` / `collection_done` |
| WS 协议帧 | `protocol.py` | **已定义**，5 种 NotifyKind |

---

## 5. 缺失项清单

| 优先级 | 缺失项 | 影响 |
|--------|--------|------|
| P0 | `adversarial_evaluate` stage 传参类型错误 | playbook 模式下该 stage 必崩 |
| P1 | OSINT claims 未回流 ctx.source_claims | osint_deep playbook 跑不通 |
| P2 | report_generate 永远 skip | 报告生成形同虚设 |
| P3 | SSE progress 回调中 stages_completed 始终为空 | 前端无法显示已完成阶段 |
| P4 | 无持久化/重试/超时 | 生产环境不可靠 |
| P5 | run_streamed 绕过 DI | 不可测试 |
| P6 | 两套重复的 pipeline 逻辑 | 维护负担，容易漂移 |
| P7 | Playbook YAML 未自动加载 | 自定义 playbook 不生效 |
| — | 无 pipeline 执行历史持久化 | 无法查询历史 run |
| — | 无 stage 级别超时 | 单个 stage 卡死会阻塞整个 pipeline |
| — | 无并发 pipeline 限流 | 多个 pipeline 同时跑可能耗尽资源 |

---

## 6. 总结

pipeline 的骨架设计合理 — pluggable stage + playbook + SSE streaming 的架构方向正确。但有几个实际运行时会崩溃的 bug（P0 签名不匹配、P1 数据断流），以及 playbook YAML 未加载导致自定义 playbook 不生效的问题。建议优先修复 P0-P3，然后考虑合并两套重复的 pipeline 路径。
