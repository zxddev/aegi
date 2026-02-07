<!-- Author: msq -->

# ADR-001: 开源项目参考分层策略

> 状态：已批准（v4）
> 日期：2026-02-07
> 决策者：msq

## 背景

`开源项目参考/` 目录下有 29 个项目。需要明确哪些可以用、怎么用、什么不能做，
防止核心仓库变成大杂烩。

## 核心原则

1. **黑盒服务化 + MCP 封装**：后端运行依赖一律以独立服务接入，通过 gateway tool 调用。前端 npm 库不受此约束，按前端参考层规则管理。
2. **一种能力只允许一个主参考项目**。
3. **每季度活跃集成项目不超过 4 个**。
4. **AGPL 项目必须"服务化调用"，禁止源码拷贝进 aegi-core / aegi-mcp-gateway**。
5. **每个引入必须有 ADR**：目标能力、替代方案、退出策略、许可证结论。
6. **每个工具必须有 contract test + replay test + audit 字段校验**。
7. **未进入白名单的项目只能写"调研笔记"，不能进运行依赖**。

## 分层

### P1 运行白名单（现在就用，服务化接入）

| 项目 | 端口 | 状态 | 用法 |
|------|------|------|------|
| searxng | 8701 | ✅ 已集成 | meta_search gateway tool |
| unstructured | 8703 | ✅ 已集成 | doc_parse gateway tool |
| archivebox | 8702 | ⚠️ 容器运行但代码未对接 | archive_url 待改为调用 ArchiveBox API |

### P1 设计参考（不引入依赖，只参考算法/模式/schema）

| 项目 | 许可证 | 主/次 | 参考什么 | 映射到 AEGI |
|------|--------|-------|---------|------------|
| baize-core | 内部 | 主 | STORM pipeline、OODA 循环、DeepResearchLoop、SectionWriter 引用重写、证据去重、冲突表、Z3 校验 | pipeline_orchestrator 能力回移源 |
| baize-mcp-gateway | 内部 | 主 | 工具合同、策略层、审计设计 | aegi-mcp-gateway 同类前身 |
| storm | MIT | 主 | 多视角 persona 生成 + grounded QA + 内联引用 | hypothesis_engine + chat pipeline |
| opencti | Apache-2.0 + EE 专有 | 主 | STIX2 数据模型 + KG schema（⚠️ 逐文件检查许可头，只参考 CE 部分） | kg_mapper 实体/关系类型体系 |
| deepagents | MIT | 次 | LangGraph 同栈 Agent 编排模式 | pipeline_orchestrator 补充参考（主参考为 baize-core） |
| yeti | Apache-2.0 | 次 | 威胁情报图模型（TTPs/Indicators/Observables 关系建模） | kg_mapper 补充参考（主参考为 opencti） |

### P2 白名单（能力增强，服务化接入）

| 项目 | 许可证 | 能力 | 触发条件 |
|------|--------|------|---------|
| grobid | Apache-2.0 | 学术文献结构化 | unstructured 对学术 PDF 不够时 |
| misp | AGPL-3.0 | IOC 共享互操作 | 需要与外部威胁情报平台对接时 |
| intelmq | AGPL-3.0 | 威胁情报处理 pipeline | 需要自动化情报采集管道时 |
| opa | Apache-2.0 | 策略引擎 | policy.py 不够用时 |
| opentelemetry-collector | Apache-2.0 | 可观测性 | ToolTrace 不够用时 |

### 前端参考层

- 图谱主选：cytoscape.js（MIT）
- 地图主选：maplibre-gl-js（BSD-3-Clause）
- graphology（MIT）/ sigma.js（MIT）：仅在确认性能瓶颈时引入，避免双图引擎并存

### 暂缓

| 项目 | 许可证 | 原因 |
|------|--------|------|
| crewAI | MIT | 框架重叠，但允许参考 Flow/Memory 设计思想 |
| tika | Apache-2.0 | 与 unstructured 功能重叠 |
| great_expectations | Apache-2.0 | 与 confidence_scorer 场景不匹配 |
| thehive | AGPL-3.0 | 已归档（v3/v4） |
| dfir-iris-web | LGPL-3.0 | 运维复杂，后期前端参考 |
| intelowl | AGPL-3.0 | 运维复杂 / 场景偏移 |
| cortex | AGPL-3.0 | 运维复杂 / 场景偏移 |
| spiderfoot | MIT | 场景偏移 |
| openmetadata | Apache-2.0 + CCLA | 数据治理，与情报分析不匹配（⚠️ 根目录 Apache，子模块 Collate Community License Agreement，含 Excluded Purpose 限制） |
| amundsen | Apache-2.0 | 数据治理，与情报分析不匹配 |
| timesketch | Apache-2.0 | 后期前端时再考虑 |

## 许可证全表

| 许可证 | 项目 | 规则 |
|--------|------|------|
| AGPL-3.0 | searxng、misp、cortex、intelmq、intelowl、thehive | 独立服务调用，禁止源码拷贝 |
| Apache-2.0 + EE 专有 | opencti | 逐文件检查许可头，只参考 CE 部分 |
| Apache-2.0 + CCLA | openmetadata | 根目录 Apache，子模块 Collate Community License Agreement（含 Excluded Purpose 限制），需逐模块判断 |
| LGPL-3.0 | dfir-iris-web | 可链接调用，不修改源码 |
| Apache-2.0 | yeti、opa、grobid、opentelemetry-collector、unstructured、amundsen、timesketch、great_expectations、tika | 可参考设计，服务化接入 |
| MIT | storm、deepagents、spiderfoot、archivebox、crewAI、cytoscape.js、graphology、sigma.js | 可自由参考 |
| BSD-3-Clause | maplibre-gl-js | 可自由参考 |
| 内部 | baize-core、baize-mcp-gateway | 能力回移源 |

## 待办

- [x] archive_url 对接 ArchiveBox CLI（6e26528）
- [ ] baize-core 能力回移评估：哪些模块可以迁移到 aegi-core
