<!-- Author: msq -->

# LangGraph 开发规范（orchestkit skills 参考）

## 1. 适用范围

涉及 LangGraph 的任何开发（agent workflow、状态图、多 agent 编排）时，本规则生效。

## 2. 强制：先加载 Skill 再动手

按场景加载对应 skill（路径前缀 `.kiro/skills/orchestkit/`）：

| 场景 | Skill | 关键内容 |
|---|---|---|
| 状态管理与 TypedDict | `langgraph-state/SKILL.md` | State 定义、Reducer、消息注解 |
| 条件路由与分支 | `langgraph-routing/SKILL.md` | conditional_edges、语义路由、重试循环 |
| Supervisor 多 agent | `langgraph-supervisor/SKILL.md` | Supervisor 模式、agent 注册、任务分发 |
| 并行执行 | `langgraph-parallel/SKILL.md` | Fan-out/fan-in、并行 agent 模板 |
| 工具调用 | `langgraph-tools/SKILL.md` | ToolNode、工具绑定、错误处理 |
| 子图组合 | `langgraph-subgraphs/SKILL.md` | 子图嵌套、状态映射、invoke vs add_as_node |
| 检查点与持久化 | `langgraph-checkpoints/SKILL.md` | PostgresCheckpointer、Store memory、状态检查 |
| 流式输出 | `langgraph-streaming/SKILL.md` | stream modes、LLM token streaming、自定义事件 |
| Human-in-the-loop | `langgraph-human-in-loop/SKILL.md` | 中断点、人工审批、恢复执行 |
| 函数式 API（装饰器） | `langgraph-functional/SKILL.md` | @entrypoint/@task 装饰器、副作用管理、迁移指南 |

## 3. LangGraph 编码要求

- State 必须用 `TypedDict` + 类型标注，禁止用裸 dict。
- 所有 node 函数必须有明确的输入/输出类型。
- 优先使用 `StateGraph` 而非手动拼接。
- 检查点：生产环境必须配置持久化（PostgresCheckpointer 优先）。
- 流式：面向用户的 agent 必须支持 streaming。
- 错误处理：每个 node 必须有异常捕获，避免整个 graph 崩溃。

## 4. 框架选型参考

涉及多 agent 框架选型时，加载 `.kiro/skills/orchestkit/alternative-agent-frameworks/SKILL.md`，包含：
- LangGraph vs CrewAI vs OpenAI Agents SDK vs Microsoft Agent Framework 对比
- 各框架适用场景与迁移路径
