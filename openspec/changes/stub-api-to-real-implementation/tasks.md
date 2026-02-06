<!-- Author: msq -->

# 桩 API → 真实实现

> 目标：将 5 个桩 API 路由升级为真实实现，注入 DB session 读写 + 调用已有 service 层函数。

## 1. 基础设施

- [ ] 1.1 确认 api/deps.py 的 get_db_session 可被所有路由使用（已就绪）
- [ ] 1.2 如需 LLM backend 依赖注入，在 deps.py 新增 get_llm_backend（Protocol 模式）

## 2. 升级路由（每个路由：注入 session → 查 DB → 调 service → 写 DB → 返回）

- [ ] 2.1 routes/hypotheses.py：generate 调 hypothesis_engine、score 调 hypothesis_engine.analyze、explain 查 DB
- [ ] 2.2 routes/narratives.py：build 调 narrative_builder、detect 调 coordination_detector、trace 查 DB
- [ ] 2.3 routes/kg.py：build_from_assertions 调 kg_mapper、upgrade 调 ontology_versioning、report 查 DB
- [ ] 2.4 routes/forecast.py：generate 调 scenario_generator、backtest 调 scenario_generator.backtest、explain 查 DB
- [ ] 2.5 routes/quality.py：score_judgment 调 confidence_scorer+bias_detector+blindspot_detector、get 查 DB
- [ ] 2.6 routes/pipelines.py：claim_extract 调 claim_extractor、assertion_fuse 调 assertion_fuser（当前也是桩）

## 3. Action + ToolTrace 审计

- [ ] 3.1 每个写操作创建 Action 记录（参考 cases.py 的 call_tool_archive_url 模式）
- [ ] 3.2 LLM 调用创建 ToolTrace 记录

## 4. 验证

- [ ] 4.1 每个升级后的路由有至少 1 个集成测试（用 TestClient + 内存 DB）
- [ ] 4.2 全量 pytest 无回归
- [ ] 4.3 ruff check 通过
