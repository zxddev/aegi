## Context

AEGI Foundry 的核心不变量要求：锚点（anchor_set/health）与可回源证据链必须可回归验证。
现有文档已经提出指标方向（例如 anchor_locate_rate、drift_rate、claim_grounding_rate），但尚未冻结为 P0 的验收合同与 fixtures 组织方式。

P0 采用 fixtures-only：不接入 SearxNG/ArchiveBox/Unstructured 的真实服务，所有输入来自固定归档产物与预期输出。

## Goals / Non-Goals

**Goals:**
- 冻结 fixtures pack 的最小组成与目录结构
- 冻结 metrics 的定义、测量方法与阈值
- 冻结 gate 行为（失败时如何处理）

**Non-Goals:**
- 不在本 change 中实现真实解析/抽取逻辑
- 不在本 change 中决定 P1 的完整评测体系（仅 P0 最小门禁）

## Decisions

### Decision 1: Fixtures 必须包含“可复现引用合同”

fixtures 不仅包含原文/归档产物，还必须包含：
- 解析产物（elements/文本）
- 预期 chunk anchors（anchor_set）
- 预期 SourceClaims（含 selectors）

### Decision 2: 指标阈值优先来自现有研究文档的建议

P0 阈值建议以研究文档给出的目标为起点（后续可调整，但必须版本化）。

## Risks / Trade-offs

- **[Risk] fixtures 覆盖不足导致“通过但无意义”】【Mitigation】至少覆盖 HTML+PDF 两类，并包含多语言/带引用的样本。
- **[Risk] 指标过严导致研发阻塞】【Mitigation】区分 P0(最低门槛) 与 P1(更高门槛)，并提供 fail-fast 报告。
