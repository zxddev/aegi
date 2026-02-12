# Author: msq

# CLAUDE.md — aegi 项目规范（Claude Code 专用）

## 项目概况

- **主应用**：`code/aegi-core/`（FastAPI，端口 8700）
- **MCP 网关**：`code/aegi-mcp-gateway/`
- **文档入口**：`docs/foundry/README.md`
- **排除**：`code/**/.venv/` 不纳入索引/搜索
- **详细规则**：`.kiro/rules/`（8 个规则文件），`.kiro/skills/`（70+ skill 文件）

## 基础设施

| 服务 | 地址 | 凭据 |
|------|------|------|
| PostgreSQL | localhost:8710 | user=aegi, password=aegi, db=aegi |
| Neo4j | bolt://localhost:8715 | user=neo4j, password=aegi-neo4j |
| Qdrant | http://localhost:8716 (gRPC 8717) | 无认证 |
| MinIO/S3 | http://localhost:8711 | key=aegi, secret=aegi-minio-password |
| LLM Backend | http://localhost:8045 | api_key=sk-aegi-dev, model=claude-sonnet-4-20250514 |
| Embedding | http://localhost:8001 | model=embedding-3, dim=1024 |
| SearXNG | http://localhost:8888 | 无认证 |

LLM extra headers 通过 `AEGI_LITELLM_EXTRA_HEADERS` 环境变量配置（JSON dict）。

## 设计理念

1. **先数据结构后代码**：核心数据与边界定义清楚，再写逻辑
2. **好品味**：从不同角度看问题，消除边界情况优于增加条件判断
3. **Never break userspace**：已发布 API 破坏性改动视为 bug，必须有迁移方案
4. **实用主义**：解决真实问题，拒绝理论完美但实际复杂的方案
5. **简洁执念**：函数短小只做一件事，关注认知复杂度而非物理缩进
6. **依赖方向单一**：通过 Protocol 隔离，禁止循环依赖
7. **Fail fast**：前置校验，尽早暴露错误
8. **可观测性内建**：关键路径必须有结构化日志和指标
9. **Make the implicit explicit**：隐式规则、依赖、副作用都应显式化
10. **Composition over inheritance**：组合 + Protocol 代替继承，继承超过 2 层就该警惕

## 本体与证据链红线

以下 5 条红线任何阶段都不能破，违反等同于引入 bug：

1. **Evidence-first + Archive-first**：断言/判断必须绑定 SourceClaim，再回溯证据链到 Artifact 快照
2. **SourceClaim-first**：先有 SourceClaim → 再有 Assertion → 再有 Judgment，不允许跳过
3. **Action-only writes**：业务数据写入只能通过 Action（校验→权限→审计→可回滚），禁止绕过
4. **工具外联统一走 Gateway**：外部访问必须通过 `aegi-mcp-gateway`，不允许直接 httpx 外部 URL
5. **派生索引可重建**：权威源在 PostgreSQL + 对象存储，图谱/搜索/物化视图必须可从权威源重建

证据链路径：
```
Judgment → Assertion → SourceClaim → Evidence → Chunk → ArtifactVersion → ArtifactIdentity
```

## 通用开发要求

- **风格规范**：所有语言遵循对应的 Google Style Guide（Python / TypeScript / Shell 等）
- **注释语言**：代码注释和文档一律中文
- **注释风格**：简洁、工程化、说人话。禁止 AI 味表述（"让我们…"、"值得注意的是…"、"需要强调…"），直接说事实和原因
- **注释原则**：只在逻辑不自明处加注释，不复述代码本身。好代码自己说话，注释解释 why 不解释 what

## Python 开发规范

### 项目约束
- Python 3.12, 依赖管理 `uv`, Lint `ruff` (line-length=100), 测试 `pytest` + `pytest-asyncio`
- 优先级：项目 pyproject.toml 配置 > Google Python Style Guide > 仓库内同类代码

### 强制规则
- **类型标注**：所有新/修改代码必须写 type hints（含返回类型），尽量避免 `Any`
- **Docstring**：Google 风格（Args/Returns/Raises），类型信息放签名不在 docstring 重复
- **错误处理**：禁止裸 `except:`，捕获异常必须具体并保留上下文
- **异步**：FastAPI 路由优先 `async def`，避免在 async 路径做阻塞 I/O
- **数据模型**：API schema 用 `pydantic.BaseModel`，纯数据容器用 `dataclass`，禁止裸 dict 传递结构化数据
- **可测试**：逻辑拆成纯函数/可注入依赖，避免业务逻辑塞进路由层

### 提交前必须运行
```bash
cd code/aegi-core
uv run ruff check .
uv run ruff format .
uv run pytest
```

## API + 数据库规范

### REST 强制偏好
- 集合用复数（`/api/users`），正确状态码（2xx/4xx/5xx）
- 大集合必须分页，从第一天规划版本化
- 文档优先：OpenAPI/Swagger

### PostgreSQL 核心规则
- ID 优先 `BIGINT GENERATED ALWAYS AS IDENTITY`，仅需全局唯一时用 UUID
- 先规范化到 3NF，测量证明 join 成本不可接受时才反规范化
- 能 `NOT NULL` 就 `NOT NULL`，FK 列必须手动建索引
- 时间用 `TIMESTAMPTZ`，金额用 `NUMERIC(p,s)`，字符串用 `TEXT + CHECK`，JSON 用 `JSONB + GIN`

## 工作流纪律

### 先证据后结论
- 任何"已完成/已修复/已通过"的表述，必须有刚运行的验证命令输出作为证据
- 不要声称修复了什么，除非你刚跑过测试并看到通过

### Bug 修复必须先定位根因
- 禁止盲猜式修复，必须先理解问题再动手
- 复杂问题做分步推理：列出关键假设、证据来源、决策点与取舍

### 新功能/修复必须有测试
- 优先单元测试，测试必须可复现、无随机性、尽量不依赖网络

### 禁止降级
- 遇到困难时禁止自行降级、简化、mock、stub、跳过、TODO 占位
- 禁止把完整实现改成 `pass` / `raise NotImplementedError`
- 禁止把类型标注改成 `Any`，禁止把异步改同步"先跑通"
- 禁止跳过校验/权限/审计中的任何一步
- 搞不定就停下来问用户，不允许偷偷降级

### 代码改动自检（动手前过一遍）
1. **数据结构对吗？** — 核心数据是什么、谁拥有、谁修改、有没有多余的复制/转换
2. **特殊情况能消除吗？** — 哪些 if/else 是业务必需，哪些是糟糕建模的补丁，能否通过更好的抽象消除
3. **复杂度合理吗？** — 概念数量是否过多，模块边界是否清晰，缩进过深通常是抽象错了
4. **会破坏什么？** — 列出受影响的现有功能和依赖，确保零破坏
5. **问题真实存在吗？** — 不解决臆想问题，投入与问题严重性匹配

### 代码改动策略
- 优先"加法"（补字段、增模型、增模块）
- 谨慎"改法"（仅在局部复杂度过高时做小重构）
- "重写"需要论证（现有问题、新方案优势、数据迁移策略）

### 作者标记
- 修改文件时，若头部无作者标记则补充 `Author: msq`（按文件类型用对应注释语法）
- Python/YAML/Shell: `# Author: msq` | JS/TS: `// Author: msq` | Markdown: `<!-- Author: msq -->`

### 沟通要求
- 代码/文档注释一律中文，表述工程化，避免拟人化或 AI 口吻
- 不确定点必须询问用户，不自行猜测关键决策
