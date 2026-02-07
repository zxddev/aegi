<!-- Author: msq -->

# 强制规则（必须遵守）

## 0.1 先技能（Skills）后行动

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
  - 需要隔离环境：`using-git-worktrees`
  - 写/改技能：`writing-skills`
  - 设计本体/领域模型/对象关系/AI agent 工具面：`designing-ontologies`（见 `07-ontology.md`）
  - 证据链/Action/SourceClaim/因果推理相关改动：必须先读 `07-ontology.md` 架构红线
  - LangGraph 开发（状态图/多 agent/工具调用/流式）：`orchestkit/langgraph-*`（见 `05-langgraph.md`）
  - Python 异步/FastAPI/gRPC：`orchestkit/asyncio-advanced`、`orchestkit/fastapi-advanced`、`orchestkit/grpc-python`
  - 多 Agent 框架选型（LangGraph/CrewAI/OpenAI Agents）：`orchestkit/alternative-agent-frameworks`
  - 代码质量审查：`orchestkit/code-review-playbook`、`orchestkit/clean-architecture`（见 `06-code-quality.md`）
  - Python 专项审查：`beagle/beagle-python/*`（见 `06-code-quality.md`）
  - AI/LangGraph 代码审查：`beagle/beagle-ai/langgraph-code-review`、`beagle/beagle-ai/langgraph-architecture`
  - LLM 生成代码检查：`beagle/beagle-core/llm-artifacts-detection`
  - 架构分析（12-Factor/ADR）：`beagle/beagle-analysis/*`

## 0.2 先证据后结论（Evidence before claims）

- 任何"已完成/已修复/已通过/没问题"的表述，都必须有**刚刚运行**的验证命令输出作为证据。
- 对应技能：`verification-before-completion`（强制）。

## 0.3 复杂问题必须"深度思考"

- 满足任一条件，必须调用 `sequentialthinking` 工具做分步推理：
  - 多阶段决策/多约束权衡（架构、安全、性能、兼容性、成本）
  - 不确定根因的排错/失败定位
  - 需要融合多来源信息（代码 + 文档 + 运行结果）
- 产出要求：最终回答必须明确列出**关键假设**、**证据来源**、**决策点与取舍**。

## 0.4 禁止降级（绝对硬要求）

- **禁止**在遇到困难时自行降级、简化、mock、stub、跳过、用 TODO 占位、或把功能改成"简化版"。
- 遇到不会的、报错的、不确定的，必须：
  1. 用 `sequentialthinking` 深度分析问题根因
  2. 用 `context7` / `langchain-docs` 查官方文档
  3. 用 `exa` / `tavily` 搜索解决方案和社区实践
  4. 仍然解决不了，**必须停下来问用户**，不允许自行决定降级
- 典型违规行为（一律禁止）：
  - 把完整实现改成 `pass` / `raise NotImplementedError` / `# TODO`
  - 把类型标注从具体类型改成 `Any`
  - 把异步实现改成同步"先跑通"
  - 跳过校验/权限/审计中的任何一步
  - 用 `print` 代替结构化日志
  - 把真实逻辑替换为硬编码返回值
  - 执行任何降级命令（如 `alembic downgrade`、`pip install` 低版本、回退配置等）——开发阶段降级会掩盖问题
- 降级 = bug。宁可停下来说"我搞不定，需要你的输入"，也不允许偷偷降级。



## 0.5 工具使用（禁止凭记忆编造）

- 禁止凭记忆编造 API 用法、库行为、代码结构。必须用工具获取事实。
- 工具选择、优先级、操作细则：详见 `01-tools.md`。
- 并发：**禁止**对同一个文件并行调用编辑工具。

## 0.6 双能力自动编排（superpowers + OpenSpec）

- 默认由 AI 自动触发，不要求用户手工指定；命中多个条件时必须组合执行。
- 职责分层：
  - `superpowers`：流程纪律与质量门禁（brainstorming、writing-plans、TDD、verification）
  - `OpenSpec`：需求-任务-验收工件与变更生命周期（opsx-new/continue/apply/verify/archive）
- 自动触发矩阵：

| 请求信号 | superpowers | OpenSpec |
|---|---|---|
| 新功能/重构/跨模块/契约变化 | brainstorming → writing-plans → TDD | opsx-new 或 opsx-continue，实施后 opsx-verify |
| Bug/回归/测试失败 | systematic-debugging → TDD | 若涉及行为/契约变化，补建 change |
| "look into" + "create PR" | 按完整交付链路，不得只做调研 | 必须进入变更流程 |
| 单文件小改且无行为变化 | verification-before-completion | 默认不触发 |

- 决策优先级：正确性与可审计性 > 兼容性 > 速度。

## 0.7 推荐主流程（从需求到交付）

- **新需求/新能力**：brainstorming → writing-plans → using-git-worktrees → TDD → verification-before-completion → requesting-code-review → finishing-a-development-branch
- **Bug 修复**：systematic-debugging → 补回归测试 → TDD → verification-before-completion
- **多独立任务**：dispatching-parallel-agents
- **计划执行**：同会话用 subagent-driven-development，独立会话用 executing-plans
- **收到 review**：先 receiving-code-review（验证/复现/澄清），再修改

## 0.8 文件作者标记（强制）

- 每次**修改**任意文件时，若文件头部尚未包含作者标记，则在文件头部补充；已存在则不重复添加。
- 标记格式：`Author: msq`，按文件类型使用对应注释语法：
  - `# Author: msq`（Python/YAML/TOML/Shell）
  - `// Author: msq`（JS/TS）
  - `<!-- Author: msq -->`（HTML/Vue/Markdown）
  - `-- Author: msq`（SQL）
- 若文件包含 shebang，作者标记放在 shebang 下一行。
