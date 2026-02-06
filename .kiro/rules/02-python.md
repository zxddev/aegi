<!-- Author: msq -->

# Python 开发规范（Google Style + 项目约束）

## 1. 优先级

1. **项目现有配置**（最高）：以 `code/*/pyproject.toml` 的 ruff/pytest/uv 配置为准
2. **Google Python Style Guide**：默认风格与可读性标准
3. 不确定时：先搜索仓库内同类代码作为"活例子"

已知项目约束：
- Python 3.12（`requires-python = >=3.12`）
- 依赖管理：`uv`
- Lint/format：`ruff`，`line-length = 100`
- 测试：`pytest` + `pytest-asyncio`

## 2. 必做（强制）

- **类型标注**：所有新/修改代码必须写 type hints（含返回类型）；尽量避免 `Any`。
- **Docstring**：Google 风格（Args/Returns/Raises）；类型信息放签名里，不在 docstring 重复。
- **错误处理**：禁止裸 `except:`；捕获异常必须具体，保留上下文。
- **异步**：FastAPI 路由优先 `async def`；避免在 async 路径做阻塞 I/O。
- **可测试**：逻辑拆成纯函数/可注入依赖；避免业务逻辑塞进路由层。

## 3. 测试与质量门禁

- 新功能/修复必须有测试覆盖（优先单元测试）。
- 测试必须可复现、无随机性；尽量不依赖网络。
- 提交前至少运行：
  ```bash
  uv run ruff check .
  uv run ruff format .
  uv run pytest
  ```

## 4. Python 开发参考 Skills（orchestkit + superpowers）

涉及以下场景时，必须先加载对应 skill 再动手：

- **异步编程**：加载 `.kiro/skills/orchestkit/asyncio-advanced/SKILL.md`
  - TaskGroup 模式、结构化并发、异步上下文管理器、取消与超时处理
- **FastAPI 高级模式**：加载 `.kiro/skills/orchestkit/fastapi-advanced/SKILL.md`
  - 依赖注入、中间件、后台任务、WebSocket、生命周期管理
- **gRPC Python**：加载 `.kiro/skills/orchestkit/grpc-python/SKILL.md`
  - 流式模式、拦截器、健康检查、错误处理
- **多 Agent 框架对比**：加载 `.kiro/skills/orchestkit/alternative-agent-frameworks/SKILL.md`
  - LangGraph vs CrewAI vs OpenAI Agents SDK vs Microsoft Agent Framework 对比与迁移路径
- **TDD/调试/验证**：继续使用 superpowers 对应 skills（见 `00-mandatory.md`）
