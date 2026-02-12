# CC 任务：修复 Phase 1 改造后的测试失败

## 背景

Phase 1 三个任务（source_credibility 多信号评分、DS 融合引擎、feedback 系统）已完成。
全量测试跑出 1 个失败，需要修复。

## 已知失败

### `tests/test_collection_api.py::test_search_preview`

```
assert data[0]["credibility"]["score"] == 0.9
AssertionError: assert 0.82 == 0.9
```

**原因：** 旧逻辑 `score_domain` 直接返回域名 `base_score`（Reuters = 0.9），新的多信号评分系统加权了 `domain_reputation`、`tld_trust`、`url_heuristics`，Reuters 输出变为 ~0.82。

**同文件还有：**
```python
assert data[1]["credibility"]["tier"] == "unknown"
assert data[1]["credibility"]["score"] == 0.5
```
这个也可能因为新评分逻辑变化而失败，一并检查。

## 修复要求

1. **不要改业务代码**，只改测试断言
2. 对 credibility score 的断言改为范围检查，不要硬编码精确值：
   - Reuters（高可信域名）：`score >= 0.75`，`tier == "high"`
   - Unknown 域名：`score <= 0.55`，`tier in ("unknown", "low")`
3. 修完后运行：
   ```bash
   source .venv/bin/activate && source env.sh
   python -m pytest tests/test_collection_api.py -x --tb=short -q
   ```
4. 确认通过后，再跑一次全量（跳过需要真实 DB 的集成测试）：
   ```bash
   python -m pytest tests/ -x --tb=short -q \
     --ignore=tests/test_feedback_service.py \
     --ignore=tests/test_stub_routes_integration.py
   ```
5. 如果发现其他因 Phase 1 改造导致的断言失败（score 精确值变化），用同样的范围检查策略修复

## 注意

- `test_feedback_service.py` 和 `test_stub_routes_integration.py` 依赖真实 DB 连接，当前环境可能连不上，跳过即可
- 如果遇到 DB 连接超时导致的失败，不算 Phase 1 引入的问题，忽略
- 目标：所有非 DB 依赖的测试全绿
