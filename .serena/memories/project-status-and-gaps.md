# 当前项目状态与待修复差距

## 测试状态（2026-02-09 10:15 更新）
- aegi-core: **215 passed**, 0 failed
- aegi-mcp-gateway: **11 passed**
- ruff check/format: clean

## 分析服务升级状态 — 全部完成 + 接通 ✅

### Phase 0: OSS 120B 接入 ✅
### Phase 1: 纯规则改进（7 个服务）✅
### Phase 2: LLM 驱动升级（4 个服务）✅
### 接通层：API 路由 + orchestrator ✅

| 路由 | 接通内容 |
|------|---------|
| chat.py | `aplan_query(llm=)` — LLM 查询规划 |
| narratives.py | `abuild_narratives_with_uids(embed_fn=)` + `embeddings` 传入 |
| forecast.py | `agenerate_forecasts(llm=)` — LLM 情景推演 |
| hypotheses.py | `aevaluate_adversarial(llm=)` — 三角对抗评估 |
| orchestrator | STAGE_ORDER += adversarial_evaluate，async 路径升级 |

### Bug 修复
- narrative embedding 阈值：0.35 → max(threshold, 0.6) when embedding
- query_planner max_tokens：512 → 1024（避免 JSON 截断）
- query_planner prompt 优化：2 步 → 5 步精细检索

### 冒烟测试结果
- aplan_query: 5 步精细检索计划 ✅
- abuild_narratives: embedding cosine 聚类正确（3 narratives）✅
- agenerate_forecasts: 3 个 LLM 情景（规则版只有 1 个）✅
- aevaluate_adversarial: defense/prosecution/judge 三角辩论 ✅

### OpenSpec YPDTS
- 14 个 change 文档（11 原有 + wiring-llm-to-routes + narrative-embedding-threshold-fix + query-planner-prompt-optimization）

## 待修复差距
### 全部已修复 ✅

## 项目约定
- `# Author: msq`、中文注释、ruff、pytest asyncio_mode=auto
- 架构红线：Evidence-first, SourceClaim-first, Action-only writes
- 所有 LLM 升级保留 sync fallback（不传 LLMClient = 原有行为）
