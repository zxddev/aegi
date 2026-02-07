<!-- Author: msq -->

# 代码质量与审查规范（orchestkit + beagle skills 参考）

## 1. 适用范围

任何代码审查、质量检查、架构评估场景，本规则生效。

## 2. 审查流程 Skills（按阶段加载）

### 2.1 架构与设计审查

- `orchestkit/clean-architecture/SKILL.md` — SOLID 原则、六边形架构、DDD 战术模式
- `beagle/beagle-analysis/12-factor-apps/` — 12-Factor 合规检查
- `beagle/beagle-analysis/adr-writing/` — 架构决策记录（ADR）

### 2.2 通用代码审查

- `orchestkit/code-review-playbook/SKILL.md` — 审查框架：可读性、命名、DRY、SOLID、安全清单
- `beagle/beagle-core/review-verification-protocol/` — 审查验证协议
- `beagle/beagle-core/llm-artifacts-detection/` — 检测 LLM 生成代码的常见问题

### 2.3 Python 专项审查

- `beagle/beagle-python/python-code-review/` — Python 通用审查
- `beagle/beagle-python/fastapi-code-review/` — FastAPI 专项
- `beagle/beagle-python/sqlalchemy-code-review/` — SQLAlchemy 专项
- `beagle/beagle-python/pytest-code-review/` — 测试代码审查
- `beagle/beagle-python/postgres-code-review/` — PostgreSQL 相关代码审查

### 2.4 AI/Agent 代码审查

- `beagle/beagle-ai/langgraph-code-review/` — LangGraph 代码审查
- `beagle/beagle-ai/langgraph-architecture/` — LangGraph 架构审查
- `beagle/beagle-ai/pydantic-ai-*/` — Pydantic AI 系列审查

## 3. 强制规则

- 代码审查时，必须先加载 `orchestkit/code-review-playbook` 作为审查框架。
- Python 代码审查必须同时加载 `beagle/beagle-python/python-code-review`。
- 涉及 LangGraph 的代码必须同时加载 `beagle/beagle-ai/langgraph-code-review`。
- LLM 生成的代码提交前，必须用 `beagle/beagle-core/llm-artifacts-detection` 检查。
- 所有审查结论必须有 `verification-before-completion`（superpowers）验证支撑。

## 4. 审查输出格式

```
【品味评分】
🟢 好品味 / 🟡 凑合 / 🔴 垃圾

【致命问题】
- ...

【改进方向】
- ...
```

## 5. Skills 路径前缀

所有路径相对于 `.kiro/skills/`。
