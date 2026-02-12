# OpenClaw ↔ AEGI 集成进度

## 已完成

### P1.1 tools.py 接入真实服务 ✅
- `submit_evidence` → 创建 ArtifactIdentity→ArtifactVersion→Chunk→Evidence 链 + Qdrant embed
- `create_case` → case_service.create_case()
- `query_kg` → Neo4j keyword search + Qdrant semantic search
- `run_pipeline` → PipelineOrchestrator.run_full_async()
- `get_report` → 统计 evidence/claim/assertion/hypothesis + 返回假设和叙事列表

### P1.2 Agent System Prompt ✅
- `deploy/agents/team/SYSTEM.md` — 情报分析助手角色
- `deploy/agents/crawler/SYSTEM.md` — 深度爬取代理
- `openclaw.yaml` 已引用 systemPromptFile

### P1.3 Gateway 客户端健壮化 ✅
- `gateway_client.py` 新增 `_reconnect()` 指数退避重连

### P1.4 权限注入 ✅
- `chat_send()` 新增 `extra_system_prompt` 参数
- `ws/handler.py` 调用 `_build_permission_prompt()` 注入

### P2 反向调用 ✅
- `openclaw/dispatch.py` — dispatch_research(), notify_user(), dispatch_and_notify()
- `tools.py` 新增 `/dispatch_research` 和 `/notify_user` 端点
- `api/main.py` lifespan 中同步设置 dispatch 模块的 gateway 实例

### 测试验证 ✅
- 129 passed, 57 skipped, 0 failed

## 修改的文件
- `aegi-core/src/aegi_core/openclaw/tools.py` — 5+2 个端点实现
- `aegi-core/src/aegi_core/openclaw/gateway_client.py` — extra_system_prompt + reconnect
- `aegi-core/src/aegi_core/openclaw/dispatch.py` — 新文件，反向调用
- `aegi-core/src/aegi_core/ws/handler.py` — 权限注入
- `aegi-core/src/aegi_core/api/main.py` — dispatch gateway 注入
- `aegi-core/deploy/openclaw.yaml` — systemPromptFile
- `aegi-core/deploy/agents/team/SYSTEM.md` — 新文件
- `aegi-core/deploy/agents/crawler/SYSTEM.md` — 新文件

### P3 Pipeline 可插拔化 ✅
- `stages/base.py` — `AnalysisStage` ABC + `StageContext` + `_StageRegistry` (auto-discover via `__subclasses__()`)
- `stages/builtin.py` — 7 个内置阶段子类，包装现有逻辑
- `stages/playbook.py` — `Playbook` dataclass + YAML loader + `get_playbook()`/`list_playbooks()`
- `deploy/playbooks.yaml` — 5 个预设 playbook (default/quick/deep/kg_only/narrative_only)
- `pipeline_orchestrator.py` — 新增 `run_playbook()` 方法，用注册表驱动
- `tools.py` — `run_pipeline` 端点支持 `playbook` 参数；新增 `/playbooks` + `/stages` 查询端点
- `api/main.py` — lifespan 中加载 playbooks + 触发 stage discovery

### 测试验证 ✅
- 129 passed, 57 skipped, 0 failed

## 修改的文件（新增）
- `aegi-core/src/aegi_core/services/stages/__init__.py` — 新文件
- `aegi-core/src/aegi_core/services/stages/base.py` — 新文件
- `aegi-core/src/aegi_core/services/stages/builtin.py` — 新文件
- `aegi-core/src/aegi_core/services/stages/playbook.py` — 新文件
- `aegi-core/deploy/playbooks.yaml` — 新文件

### P4 多视角分析 + 文档解析 + SearXNG ✅

**P4.1 多视角 Persona 假设生成：**
- `services/persona_generator.py` — `generate_personas()` + `generate_hypotheses_multi_perspective()`
- `stages/multi_perspective.py` — `MultiPerspectiveHypothesisStage` 插件阶段
- `contracts/schemas.py` — `HypothesisV1` 新增 `metadata` 字段（存 persona/perspective）
- `deploy/playbooks.yaml` — 新增 `deep_multi` playbook（4 persona + 对抗评估）

**P4.2 文档解析：**
- `services/document_parser.py` — `parse_document()` 支持 PDF/DOCX/HTML/MD/TXT + `chunk_text()`
- `api/routes/ingest.py` — `POST /ingest/document`（上传+解析+分块+入库+embed）+ `POST /ingest/parse`（仅解析预览）
- `pyproject.toml` — 新增 `[ingest]` optional deps (pypdf, python-docx, beautifulsoup4, markdownify) + python-multipart

**P4.3 SearXNG 搜索：**
- `infra/searxng_client.py` — `SearXNGClient` async HTTP 客户端
- `api/routes/search.py` — `GET /search?q=...` 端点
- `api/deps.py` — `get_searxng_client()` 依赖注入
- `settings.py` — `searxng_base_url` 配置项

**验证：** 8 stages, 6 playbooks, 129 tests passed

### P5 LLM Proxy 接入 AntiHub Plugin API ✅

**问题：** AEGI_LITELLM_BASE_URL 指向 8713（未运行），AntiHub Plugin API 在 8045 但需要 `X-Account-Type: kiro` header 才能使用 Kiro 账号代理 Claude 模型。

**修改：**
- `settings.py` — 默认 litellm_base_url 改为 8045，新增 `litellm_extra_headers` 配置项（JSON dict）
- `infra/llm_client.py` — `__init__` 新增 `extra_headers` 参数，注入到 httpx 和 AsyncOpenAI
- `api/deps.py` — `get_llm_client()` 解析 `litellm_extra_headers` 并传递
- `scripts/e2e_test.sh` — 新增 `AEGI_LITELLM_EXTRA_HEADERS='{"X-Account-Type":"kiro"}'`

**运行时环境变量：**
```
AEGI_LITELLM_BASE_URL=http://localhost:8045
AEGI_LITELLM_API_KEY=sk-9ce69cfddf90f90c3720e71d65aecfc1f210e3e66b2921ef773a4dd8e8c278af
AEGI_LITELLM_EXTRA_HEADERS='{"X-Account-Type":"kiro"}'
AEGI_LITELLM_DEFAULT_MODEL=claude-sonnet-4-20250514
```

**验证：** 151 passed, invoke() + invoke_structured() 均可用

## 待做
- 端到端集成测试（启动所有服务，走完整 pipeline 流程）
- 前端 Vue 聊天 UI（用户明确不做）