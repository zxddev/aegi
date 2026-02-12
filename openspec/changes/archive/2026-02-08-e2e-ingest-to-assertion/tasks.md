# Tasks

## 1. 实现

- [x] 1.1 创建 `tests/test_e2e_ingest_to_assertion.py`
- [x] 1.2 实现 Gateway ASGI ToolClient（_RealAsyncClient 避免 patch 冲突）
- [x] 1.3 mock Gateway 内部 httpx 调用 + LLM 后端
- [x] 1.4 编写全链路测试：ingest → claim_extract → assertion_fuse

## 2. 验收

- [x] 2.1 pytest 通过（206 passed）
- [x] 2.2 ruff clean