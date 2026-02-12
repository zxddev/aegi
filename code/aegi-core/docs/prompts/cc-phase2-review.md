# CC 任务：Phase 2 代码审查 + 补缺

## 背景

Phase 2 双轨（贝叶斯 ACH + 事件驱动主动推送）的核心代码已经写好了，需要做一次系统性审查，确认完整度、修复问题、补齐缺失。

## 审查范围

### 1. 贝叶斯 ACH 模块

文件：
- `src/aegi_core/services/bayesian_ach.py` — 贝叶斯引擎
- `src/aegi_core/services/hypothesis_engine.py` — 静态 ACH
- `src/aegi_core/db/models/hypothesis.py`
- `src/aegi_core/db/models/evidence_assessment.py`
- `src/aegi_core/db/models/probability_update.py`

测试：
- `tests/test_bayesian_math.py`
- `tests/test_bayesian_assess.py`
- `tests/test_bayesian_api.py`
- `tests/test_bayesian_event_integration.py`
- `tests/test_ach_hypothesis_engine.py`
- `tests/test_hypothesis_engine_generate.py`

检查项：
- [ ] 贝叶斯更新公式数学正确性（归一化、似然度映射、先验→后验）
- [ ] `recalculate` 从头重放逻辑：删除旧记录→按时间重放→写新记录，事务安全吗？
- [ ] `assess_evidence` LLM 失败时返回空列表，后续 `update` 用 0.5 填充——确认这个降级行为是否有日志/告警
- [ ] `create_bayesian_update_handler` 串行处理 claim_uids 是正确的（注释已说明），确认没有被改成并行
- [ ] `bayesian_update_threshold` 配置项是否存在于 settings.py？默认值是多少？是否合理？
- [ ] DB 模型的 Alembic migration 是否存在？
- [ ] 所有测试能否通过？跑一下：
  ```bash
  source .venv/bin/activate && source env.sh
  python -m pytest tests/test_bayesian_math.py tests/test_bayesian_assess.py tests/test_bayesian_api.py tests/test_bayesian_event_integration.py tests/test_ach_hypothesis_engine.py tests/test_hypothesis_engine_generate.py -x --tb=short -q
  ```

### 2. 事件驱动推送模块

文件：
- `src/aegi_core/services/push_engine.py` — 推送决策引擎
- `src/aegi_core/services/event_bus.py` — 事件总线
- `src/aegi_core/services/event.py` — 事件定义
- `src/aegi_core/services/gdelt_monitor.py` — GDELT 监测
- `src/aegi_core/db/models/subscription.py`
- `src/aegi_core/db/models/push_log.py`
- `src/aegi_core/db/models/gdelt_event.py`
- `src/aegi_core/db/models/event_log.py`
- `src/aegi_core/api/routes/subscriptions.py`
- `src/aegi_core/openclaw/event_bridge.py`
- `src/aegi_core/openclaw/dispatch.py`

测试：
- `tests/test_push_engine.py`
- `tests/test_event_bus.py`
- `tests/test_event_driven_integration.py`
- `tests/test_gdelt_monitor.py`
- `tests/test_gdelt_client.py`
- `tests/test_gdelt_events_csv.py`
- `tests/test_gdelt_anomaly.py`
- `tests/test_gdelt_api.py`
- `tests/test_gdelt_scheduler.py`

检查项：
- [ ] PushEngine 完整链路：event → rule_match → semantic_match → merge → throttle → deliver → record，每一步是否有错误处理？
- [ ] `_semantic_match` 依赖 `expert_profiles` Qdrant 集合——这个集合的数据写入逻辑在哪？如果不存在，语义匹配就是空的
- [ ] `_deliver` 调用 `notify_user` → `GatewayClient.chat_inject`，确认 GatewayClient 的 `chat_inject` 方法存在且实现完整
- [ ] `session_manager.session_key_for_user` 的逻辑是什么？user_id 如何映射到 session_key？
- [ ] GDELT 监测：`GDELTClient` 的实际 HTTP 调用是否正确？API URL、参数、解析逻辑
- [ ] GDELT `ingest_event` 把事件转为 Evidence → SourceClaim → emit `claim.extracted`，这会触发贝叶斯更新——确认这个跨模块链路能跑通
- [ ] 异常检测 `detect_anomalies`：三种异常类型的阈值是否可配置？
- [ ] Subscription API 路由：CRUD 是否完整？参数校验？
- [ ] 所有测试能否通过？跑一下：
  ```bash
  python -m pytest tests/test_push_engine.py tests/test_event_bus.py tests/test_event_driven_integration.py tests/test_gdelt_monitor.py tests/test_gdelt_client.py tests/test_gdelt_events_csv.py tests/test_gdelt_anomaly.py tests/test_gdelt_api.py tests/test_gdelt_scheduler.py -x --tb=short -q
  ```

### 3. 跨模块集成

- [ ] EventBus 的 handler 注册：`create_push_handler` 和 `create_bayesian_update_handler` 在哪里注册到 EventBus？是 app 启动时？找到注册代码
- [ ] 完整事件流验证：GDELT 事件 → `gdelt.event_detected` → PushEngine 推送 + `ingest_event` → `claim.extracted` → BayesianACH 更新 → `hypothesis.updated`。这条链路的每个环节都接上了吗？
- [ ] `event_bridge.py` 的作用是什么？和 EventBus 的关系？

## 输出要求

1. 先跑测试，记录结果
2. 对每个检查项给出结论（✅ 通过 / ⚠️ 需要修复 / ❌ 缺失）
3. 发现的问题直接修复（不要只报告不修）
4. 如果有缺失的关键模块（如 expert_profiles 写入、handler 注册），补上
5. 最后再跑一次全量测试确认没有 break：
   ```bash
   python -m pytest tests/ -x --tb=short -q \
     --ignore=tests/test_feedback_service.py \
     --ignore=tests/test_stub_routes_integration.py
   ```

## 注意

- 不要改动核心算法逻辑（贝叶斯公式、推送决策），除非发现数学错误
- 可以改测试断言、补缺失代码、修 import 错误
- `test_feedback_service.py` 和 `test_stub_routes_integration.py` 依赖真实 DB，跳过
- 如果遇到 DB 连接超时，不算 Phase 2 的问题，跳过
