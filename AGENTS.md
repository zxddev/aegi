<!-- Author: msq -->

# 项目 AI 开发总则（AGENTS.md）

本文件是本项目里 AI 助手的默认工作规则。目标只有三个：**可复现**、**可审计**、**不瞎改**。

## 0) 强制规则（必须遵守）

### 0.1 先技能（Skills）后行动

- 任何请求开始时，先判断是否有相关技能；只要有 1% 可能适用，就必须先加载并严格遵循技能流程。
- 常用技能（按场景）：
  - 需求/方案/架构：`brainstorming` → `writing-plans`
  - 实施计划执行：`subagent-driven-development`（同会话）或 `executing-plans`（独立会话）
  - Bug/失败：`systematic-debugging`
  - 新功能/修复实现：`test-driven-development`
  - 代码评审：`requesting-code-review`、`receiving-code-review`
  - 完成/通过宣称前：`verification-before-completion`
  - 分支收尾：`finishing-a-development-branch`
  - 多个独立子任务：`dispatching-parallel-agents`
  - 需要隔离环境：`using-git-worktrees`（前提：仓库是 git）
  - 写/改技能：`writing-skills`

### 0.2 先证据后结论（Evidence before claims）

- 任何“已完成/已修复/已通过/没问题”的表述，都必须有**刚刚运行**的验证命令输出作为证据。
- 对应技能：`verification-before-completion`（强制）。

### 0.3 复杂问题必须“深度思考”

- 满足任一条件，必须调用 `sequentialthinking` MCP 工具做分步推理：
  - 多阶段决策/多约束权衡（架构、安全、性能、兼容性、成本）
  - 不确定根因的排错/失败定位
  - 需要融合多来源信息（代码 + 文档 + 运行结果）
- 产出要求：最终回答必须明确列出 **关键假设**、**证据来源**、**决策点与取舍**（不要求公开完整推理链，但必须可审计）。

### 0.4 强制使用 MCP/工具获取事实（禁止“凭记忆编造”）

- 需要最新 API/第三方库用法：优先 `context7` / `langchain-docs`，其次 `exa` / `tavily`。
- 需要看外部仓库结构/文档：优先 `deepwiki`，需要具体 PR/Issue/文件则用 `github`。
- 需要网页交互/下载/截图：用 `playwright`。
- 需要数据库查询：用 `postgres`（只读，禁止写操作）。
- 需要理解/修改当前代码：优先 `serena`（语义级）→ `Grep/Glob`（文本级）→ `repomix`（大范围索引）。

### 0.5 工具使用纪律（减少壳命令，避免误操作）

- 代码探索：优先用 `Glob`/`Grep`/（如可用）目录列表工具；避免 shell 的 `find/grep/sed/awk`。
- 语义编辑：优先 `serena_*` 工具（找符号、找引用、精确替换/插入），避免“拍脑袋全局替换”。
- 并发：**禁止**对同一个文件并行调用编辑工具。
- 路径：优先使用绝对路径或明确的仓库相对路径，避免歧义。

### 0.6 文件作者标记（强制）

- 每次**修改**任意文件时，若文件头部尚未包含作者标记，则在文件头部补充作者标记；已存在则不重复添加。
- 作者标记必须使用规范英文：`Author: msq`。
- 按文件类型使用对应注释语法，示例：
  - `# Author: msq`（Python/YAML/TOML/Shell 等）
  - `// Author: msq`（JS/TS 等）
  - `<!-- Author: msq -->`（HTML/Vue/Markdown 等）
- `-- Author: msq`（SQL 等）
- 若文件包含 shebang（如 `#!/usr/bin/env python3`），作者标记应放在 shebang 下一行。

### 0.7 三能力自动编排（superpowers + OhMyOpenCode + OpenSpec）

- 默认由 AI 自动触发能力，不要求用户手工指定；命中多个条件时，必须组合执行，不是三选一。
- 三能力职责分层（先判定职责，再决定执行顺序）：
  - `superpowers`：流程纪律与质量门禁（如 `brainstorming`、`writing-plans`、`test-driven-development`、`verification-before-completion`）。
  - `OhMyOpenCode`：工具与子代理编排（如 `explore`/`librarian`/`oracle`、并行任务调度、本地工具调用）。
  - `OpenSpec`：需求-任务-验收工件与变更生命周期（`opsx-new`/`opsx-continue`/`opsx-apply`/`opsx-verify`/`opsx-archive`）。
- 自动触发矩阵（命中任一即触发，对应列可同时生效）：

| 请求信号 | superpowers（自动） | OhMyOpenCode（自动） | OpenSpec（自动） |
| --- | --- | --- | --- |
| 新功能/重构/跨模块改动/接口契约变化 | `brainstorming` → `writing-plans` → `test-driven-development` | `explore` 并行摸清现状；涉及外部库时并行 `librarian` | `opsx-new` 或 `opsx-continue`，实施后 `opsx-verify` |
| Bug/回归/测试失败 | `systematic-debugging` → `test-driven-development` | `explore` 定位链路；2 次失败后 `oracle` | 若修复涉及行为/契约变化，自动补建或续写 change |
| “look into” + “create PR” | 按完整交付链路执行，不得只做调研 | 并行调研 + 实施 + 验证 | 必须进入 OpenSpec 变更流程 |
| 单文件小改且无行为变化 | `verification-before-completion` | 直接工具或 `quick` 子代理 | 默认不触发（除非用户明确要求） |

- 并发规则：
  - 相互独立的检索/分析任务必须并发执行（如多个 `explore`/`librarian`）。
  - 禁止并行编辑同一文件；并发仅用于互不依赖的任务。
- 决策优先级：正确性与可审计性 > 兼容性 > 速度；冲突时按该顺序裁决。

## 1) 项目结构速览（先看清楚再动手）

- 文档入口：`docs/foundry/README.md`
- 需求研究（归档）：`docs/archive/需求研究/`
- Python 代码：`code/aegi-core/`、`code/aegi-mcp-gateway/`
- 注意：`code/**/.venv/` 可能很大，默认不要把它纳入索引/搜索范围。

## 2) MCP 使用手册（什么时候用什么）

说明：不同运行环境里工具 ID 可能显示为 `mcp__<server>__<tool>`、`<server>___<tool>` 或类似形式，以实际 UI 为准。

### 2.1 `serena`（语义代码分析与精确编辑）

适用场景：
- 需要“按符号”理解/修改代码（类/方法/函数/引用关系），避免盲改。
- 需要精准插入/替换代码段。

常用工具：
- `serena_get_symbols_overview`：快速看文件的顶层符号结构
- `serena_find_symbol`：按名称/路径查符号
- `serena_find_referencing_symbols`：找某符号的引用点
- `serena_read_file`：读取文件/片段
- `serena_replace_content`：用 literal/regex 安全替换
- `serena_insert_before_symbol` / `serena_insert_after_symbol`：在符号边界插入内容

### 2.2 `sequentialthinking`（深度思考/分步推理）

适用场景：见 0.3（强制）。

要求：
- 先用它把问题拆成步骤，再开始改代码/改文档。
- 每一步都要能对应到“证据/输入/输出”，避免拍脑袋。

### 2.3 `context7`（权威库文档/用法查询）

适用场景：
- 需要某个第三方库/框架的最新用法、参数、示例；或你对 API 细节不确定。

推荐流程：
1) `context7_resolve-library-id`（先定位库 ID）
2) `context7_query-docs`（再按问题检索片段）

### 2.4 `langchain-docs`（LangChain 文档检索）

适用场景：
- 只要问题涉及 LangChain/LangGraph/Deep Agents 等，优先用它查官方 docs。

工具：
- `langchain-docs_SearchDocsByLangChain`

### 2.5 `deepwiki`（外部仓库结构化阅读）

适用场景：
- 快速理解 GitHub 仓库的模块结构、关键文件、设计思路。

常用工具：
- `deepwiki_read_wiki_structure`
- `deepwiki_read_wiki_contents`
- `deepwiki_ask_question`

### 2.6 `github`（GitHub 读写操作）

适用场景：
- Issue/PR/文件内容读取，创建 issue/PR，查询 PR diff/状态等。
- 能用 `gh`/网页做的也可以，但在自动化流程里优先 MCP。

### 2.7 `repomix`（代码库打包索引/跨文件搜索）

适用场景：
- 需要“全局理解”或跨大量文件检索时，用 repomix 打包并在输出里 grep。

常用工具：
- `repomix_pack_codebase`
- `repomix_attach_packed_output`
- `repomix_grep_repomix_output`

### 2.8 `exa` / `tavily`（网络搜索：最佳实践/教程/新闻）

适用场景：
- 需要互联网信息，但不一定是官方 API 文档；或需要多来源交叉验证。

建议：
- `exa_get_code_context_exa`：优先找“代码示例/官方仓库/StackOverflow 片段”
- `exa_web_search_exa` / `tavily_tavily_search`：通用检索

### 2.9 `playwright`（网页交互/可视化抓取）

适用场景：
- 需要登录后页面抓取、复杂网页渲染、下载、截图、表单交互。

### 2.10 `postgres`（只读数据库查询）

适用场景：
- 需要用 SQL 验证数据、排查问题、抽样检查。

强制：
- 只允许只读查询（SELECT）。任何写操作（INSERT/UPDATE/DELETE/DDL）一律禁止。

## 3) Python 开发规范（Google + 本项目约束）

### 3.1 优先级

1) **项目现有配置**（优先）：以 `code/*/pyproject.toml` 的 ruff/pytest/uv 配置为准
2) **Google Python Style Guide**：作为默认风格与可读性标准
3) 不确定时：先搜索仓库内同类代码作为“活例子”，再动手

已知项目约束（当前仓库）：
- Python：3.12（`requires-python = >=3.12`）
- 依赖管理：`uv`（`[tool.uv]`）
- Lint/format：`ruff`，`line-length = 100`
- 测试：`pytest` + `pytest-asyncio`

### 3.2 必做（强制）

- 类型标注：所有新/修改的 Python 代码必须写 type hints（含返回类型）；尽量避免 `Any`。
- Docstring：使用 Google 风格（Args/Returns/Raises）；类型信息放在函数签名里，不在 docstring 里重复。
- 错误处理：禁止裸 `except:`；捕获异常必须具体，并保留上下文（msg/异常链）。
- 异步：FastAPI 路由优先 `async def`；避免在 async 路径里做阻塞 I/O。
- 可测试：逻辑尽量拆成纯函数/可注入依赖；避免把业务逻辑塞进路由层。

### 3.3 测试与质量门禁

- 新功能/修复必须有测试覆盖（优先单元测试）。
- 测试必须可复现、无随机性；尽量不依赖网络。
- 在宣称通过前（或提交/PR 前），至少运行：
  - `uv run ruff check .`
  - `uv run ruff format .`（若项目启用格式化）
  - `uv run pytest`

## 4) 设计理念（写代码前先把“问题”说清楚）

### 4.1 核心思维

- 先数据结构后代码：先把核心数据与边界定义清楚，再写逻辑。
- 消除特殊情况：优先通过更正确的数据建模/抽象消除分支，而不是堆 if/else。
- Never break userspace：任何破坏现有行为/接口的改动都需要显式迁移方案与兼容策略。
- 实用主义：解决真实问题；不要为了“看起来高级”引入复杂性。

### 4.2 决策输出模板（用于架构/方案/大改）

```
【核心判断】
✅ 值得做 / ❌ 不值得做

【关键洞察】
- 数据结构：...
- 复杂度：...
- 风险点：...

【方案】
1. ...
2. ...

【验证方式】
- 用什么命令/指标证明它是对的：...
```

## 5) 操作细则（工具使用）

- 先 `Glob` 找文件，再 `Grep` 定位内容，再用 `serena_*` 做符号级修改。
- 大范围理解用 `repomix`，但要排除 `.venv/`、`node_modules/`、大文件等无关目录。
- 永远不要并行编辑同一个文件。
- 需要运行命令前，先确认工具存在（例如 `uv`、`ruff`、`pytest`），并在正确目录执行。

## 6) 开发技能（Skills）怎么落地（强制执行）

### 6.1 推荐主流程（从需求到交付）

- **新需求/新能力**：`brainstorming` → `writing-plans` → `using-git-worktrees`（若仓库为 git）→ `test-driven-development` → `verification-before-completion` → `requesting-code-review` → `finishing-a-development-branch`
- **Bug 修复/失败排查**：`systematic-debugging` →（补回归测试）→ `test-driven-development` → `verification-before-completion`
- **多独立任务**：`dispatching-parallel-agents`（拆成互不冲突的子任务）
- **计划执行**：
  - 同会话快迭代：`subagent-driven-development`
  - 独立会话批执行：`executing-plans`
- **收到 review 意见**：先 `receiving-code-review`（先验证/复现/澄清），再修改

### 6.2 强制“工具优先级”

- **改代码前先理解**：`serena`（符号级）优先；找不到再用 `Grep/Glob`；全局理解再用 `repomix`。
- **查外部知识**：`context7`/`langchain-docs` 优先；不够再用 `exa`/`tavily`。
- **任何完成宣称**：必须先跑验证命令（`verification-before-completion`）。

### 6.3 三能力联合流程模板（自动触发示例）

- 需求类任务默认走“三能力联合链路”：`superpowers` 定义流程与门禁，`OhMyOpenCode` 负责并行探索/实施，`OpenSpec` 负责工件沉淀与验收归档。
- 推荐执行骨架：
  1) 识别请求类型与风险，自动选择 superpowers 过程技能。
  2) 使用 OhMyOpenCode 并行收集事实（代码、外部文档、历史变更）。
  3) 判断是否进入 OpenSpec（跨模块、契约变化、需长期追溯时默认进入）。
  4) 实施最小改动并完成验证，再同步 OpenSpec 工件状态。
- 约束：不得因为“已启用某一能力”而跳过其他已命中触发条件的能力。

## 7) API 设计原则（REST / GraphQL）

适用场景：设计新 API、重构现有 API、为团队建立 API 设计标准、实现前审查 API 规范。

### 7.1 REST 设计

- 资源导向：资源是名词（`users`/`orders`），操作用 HTTP 方法表达。
- HTTP 方法语义：
  - `GET`：读取（安全、幂等）
  - `POST`：创建（非幂等）
  - `PUT`：整体替换（幂等）
  - `PATCH`：部分更新
  - `DELETE`：删除（幂等）
- 典型端点：

```
GET    /api/users
POST   /api/users
GET    /api/users/{id}
PUT    /api/users/{id}
PATCH  /api/users/{id}
DELETE /api/users/{id}
GET    /api/users/{id}/orders
```

- 最佳实践（强制偏好）：
  - 一致命名（集合用复数）
  - 正确状态码（2xx/4xx/5xx）
  - 大集合必须分页
  - 从第一天就规划版本化（或兼容策略）
  - 限流与鉴权必须工程化
  - 文档优先：OpenAPI/Swagger

### 7.2 GraphQL 设计

- Schema-first：先设计 schema 再写 resolver。
- 避免 N+1：使用 DataLoader/batching。
- 输入验证：schema + resolver 双层兜底。
- 错误处理：mutation payload 返回结构化错误。
- 分页：优先游标分页（Relay 规范）。

## 8) PostgreSQL 表设计（最佳实践）

适用场景：设计 schema/表结构、索引、约束与性能路径。

### 8.1 核心规则

- 引用型表优先 **PRIMARY KEY**；日志/事件流类表可按场景决定。
- ID 优先 `BIGINT GENERATED ALWAYS AS IDENTITY`；仅在需要不透明全局唯一性时使用 `UUID`。
- 先规范化（到 3NF）消除冗余；只有在测量证明 join 成本不可接受时才反规范化。
- 能 `NOT NULL` 就 `NOT NULL`；常见值提供 `DEFAULT`。
- 索引按真实查询路径设计：PK/unique（自动）、**FK 列（手动！）**、常用过滤/排序、连接键。

### 8.2 PostgreSQL 常见“坑”

- 标识符：不带引号会自动小写化；避免带引号/混合大小写名称；统一 `snake_case`。
- `UNIQUE` + `NULL`：允许多个 `NULL`；需要时用 `UNIQUE (...) NULLS NOT DISTINCT`（PG15+）。
- FK 不会自动建索引：必须手动为外键列建索引。
- identity/序列有间隙是正常现象，不要试图“修复”。

### 8.3 数据类型偏好

- 时间：一律用 `TIMESTAMPTZ`（不要用无时区 `timestamp`）。
- 金额：`NUMERIC(p,s)`（不要用 float，也不要用 `money` 类型）。
- 字符串：优先 `TEXT`；长度限制用 `CHECK (LENGTH(col) <= n)`。
- JSON：优先 `JSONB`；需要查询时配 GIN 索引；仅用于可选/半结构化属性。

### 8.4 索引选择

- B-tree：等值/范围/排序（默认）。
- 复合索引：最左前缀原则；顺序比“包含哪些列”更重要。
- 覆盖索引：`INCLUDE` 提升仅索引扫描命中率。
- 部分索引：只为热子集建（`WHERE status = 'active'`）。
- GIN：JSONB/数组/全文。
- BRIN：超大且自然有序（时间序列）。

## 9) 代码质量准则（Linus Torvalds 风格）

你要用工程标准说话：批评针对技术，不针对人；但不允许“糊弄式正确”。

### 9.1 核心哲学

- “好品味”（Good Taste）：用更好的数据结构/抽象，让特殊情况消失。
- Never break userspace：任何会破坏现有使用的改动，默认视为 bug，除非有兼容/迁移方案。
- 实用主义：解决真实问题，不为“理论完美”堆复杂度。
- 简洁执念：缩进层级太深/函数太长，通常是抽象错了。

### 9.2 沟通与输出要求

- 用中文表达，结论明确、可验证、可复现。
- 代码/文档注释一律使用中文，表述保持工程化，避免拟人化或 AI 口吻（例如“我认为/我建议/让我们/作为 AI”等）。
- 任何不确定点必须点名并询问用户（不要自行猜测关键决策）。

### 9.3 Linus 式分析框架（做设计/排错/评审时使用）

1) **数据结构**：核心数据是什么？谁拥有它？谁修改它？
2) **特殊情况**：哪些 if/else 是业务必需，哪些是糟糕建模的补丁？能否通过抽象消除？
3) **复杂度**：概念数量是否过多？模块边界是否清晰？
4) **破坏性**：会破坏什么？现有接口/行为/依赖如何保持兼容？
5) **实用性**：问题是否真实存在？投入产出是否匹配？

代码评审输出建议格式：

```
【品味评分】
🟢 好品味 / 🟡 凑合 / 🔴 垃圾

【致命问题】
- ...

【改进方向】
- ...
```

## 10) 额外强制约束（避免工具误用）

- 运行任何命令前，先确认命令存在；不要假设环境已安装。
- 禁止并行编辑同一个文件（包括同时对同一文件做 replace/insert）。
- 探索代码库优先用 `Grep`/`Glob`/目录列表工具；不要用 shell 的 `find/grep` 代替。
- 路径默认用绝对路径；引用文件时用“仓库相对路径 + 行号”更可审计。
