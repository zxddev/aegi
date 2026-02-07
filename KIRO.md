<!-- Author: msq -->

# aegi — Kiro Agent 总纲

本文件是 Kiro agent 的入口索引。详细规则按主题拆分在 `.kiro/rules/`，技能在 `.kiro/skills/`。

## 项目概况

- **文档入口**：`docs/foundry/README.md`
- **需求研究（归档）**：`docs/archive/需求研究/`
- **Python 代码**：`code/aegi-core/`、`code/aegi-mcp-gateway/`
- **注意**：`code/**/.venv/` 默认排除，不纳入索引/搜索。

## 规则索引

| 文件 | 覆盖范围 |
|------|----------|
| `00-mandatory.md` | 强制规则：先技能后行动、先证据后结论、深度思考、工具纪律、双能力编排、主流程、作者标记 |
| `01-tools.md` | MCP/工具使用手册与操作细则 |
| `02-python.md` | Python 开发规范（Google Style + 项目约束 + orchestkit skills 参考） |
| `03-design.md` | 设计理念 + 代码质量准则（Linus 风格） |
| `04-api-database.md` | REST/GraphQL API 设计 + PostgreSQL 表设计 |
| `05-langgraph.md` | LangGraph 开发规范（orchestkit 10 个 langgraph skills 参考） |
| `06-code-quality.md` | 代码质量与审查规范（orchestkit + beagle skills 参考） |
| `07-ontology.md` | aegi 本体与证据链设计规则（架构红线、Object-first、因果推理、元认知） |

## 技能索引

| 来源 | 路径 | Skills 数 | 定位 |
|------|------|-----------|------|
| superpowers | `.kiro/skills/superpowers/` | 13 | 流程纪律与质量门禁（TDD/审查/验证/调试/分支） |
| orchestkit | `.kiro/skills/orchestkit/` | 16 | LangGraph 开发 + Python 高级 + 架构 + 审查框架 |
| beagle | `.kiro/skills/beagle/` | 32 | 代码质量审查（Python/AI/架构/LLM 检测） |
| designing-ontologies | `.kiro/skills/designing-ontologies/` | 1 | Palantir 本体设计参考 |
| OpenSpec | `.kiro/skills/openspec/` | 9 | 需求-任务-验收工件与变更生命周期 |

## 核心原则

1. **先技能后行动**：任何请求先判断适用技能，命中即加载执行。
2. **先证据后结论**：任何完成宣称必须有刚运行的验证输出。
3. **正确性 > 兼容性 > 速度**：冲突时按此优先级裁决。
