<!-- Author: msq -->

# 项目 AI 开发总则

本项目的 AI 开发规则统一维护在 `.kiro/rules/` 目录下，由 `.kiro/agents/dev.json` → `KIRO.md` 加载。

## 规则索引

| 文件 | 覆盖范围 |
|------|----------|
| `00-mandatory.md` | 强制规则：先技能后行动、先证据后结论、深度思考、工具纪律、三能力编排、主流程、作者标记 |
| `01-tools.md` | MCP/工具使用手册与操作细则 |
| `02-python.md` | Python 开发规范（Google Style + 项目约束） |
| `03-design.md` | 设计理念 + 代码质量准则（Linus 风格） |
| `04-api-database.md` | REST/GraphQL API 设计 + PostgreSQL 表设计 |
| `05-langgraph.md` | LangGraph 开发规范 |
| `06-code-quality.md` | 代码质量与审查规范 |
| `07-ontology.md` | aegi 本体与证据链设计规则（项目核心） |

## 技能索引

| 来源 | 路径 | 定位 |
|------|------|------|
| superpowers | `.kiro/skills/superpowers/` | 流程纪律与质量门禁 |
| orchestkit | `.kiro/skills/orchestkit/` | LangGraph + Python 高级 + 架构 |
| beagle | `.kiro/skills/beagle/` | 代码质量审查 |
| designing-ontologies | `.kiro/skills/designing-ontologies/` | 本体设计（项目核心） |
| OpenSpec | `.kiro/skills/openspec/` | 需求-任务-验收工件 |

## 项目结构

- 文档入口：`docs/foundry/README.md`
- Python 代码：`code/aegi-core/`、`code/aegi-mcp-gateway/`
- 注意：`code/**/.venv/` 默认排除。

如使用非 Kiro 的 AI 工具，请直接阅读上述 `.kiro/rules/*.md` 文件。
