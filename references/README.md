# AEGI 参考资料索引

> 维护：白泽
> 更新：2026-02-11

---

## 开源项目 (references/opensource/)

| 项目 | 目录 | 用途 | 关注重点 |
|------|------|------|----------|
| **DoWhy** (Microsoft) | `dowhy/` | 因果推断框架 | `dowhy/causal_model.py`, `dowhy/causal_estimators/` |
| **PyKEEN** | `pykeen/` | KG embedding + 链接预测 | `pykeen/models/`, `pykeen/training/` |
| **OpenCTI** | `opencti/` | 威胁情报平台（架构参考） | 整体架构、数据模型、connector 机制 |
| **pgmpy** | `pgmpy/` | 贝叶斯网络库（数学参考） | `pgmpy/models/BayesianNetwork.py`, `pgmpy/inference/` |
| **CausalNex** | `causalnex/` | 因果图发现 | `causalnex/structure/`, `causalnex/inference/` |

## 论文 (references/papers/)

| 论文 | 文件 | 核心价值 |
|------|------|----------|
| Approaching Human-Level Forecasting with LMs (2024) | `approaching-human-level-forecasting-2024.pdf` | AEGI 事件预判模块蓝图：检索增强 + LLM 预测 + 聚合 |
| ThinkTank-ME: Multi-Expert Event Forecasting (2026.01) | `thinktank-me-multi-expert-2026.pdf` | 多 LLM agent 扮演不同专家角色做预测 |
| Do LLMs Know Conflict? (2025) | `llm-know-conflict-2025.pdf` | LLM 参数知识不够，必须结合外部数据 |
| Causal Cartographer (2025) | `causal-cartographer-2025.pdf` | 因果世界模型 + 反事实推理 |
| LLM-as-a-Prophet (2025) | `llm-as-prophet-2025.pdf` | LLM 预测能力评估框架 |

## 经典书籍（未下载，推荐阅读）

| 书名 | 作者 | 核心价值 |
|------|------|----------|
| Superforecasting | Philip Tetlock | 结构化预测方法论：分解→基准概率→增量更新→校准 |
| Psychology of Intelligence Analysis | Richards Heuer | ACH 方法论原著，认知偏见分析 |
| Structured Analytic Techniques | Heuer & Pherson | 情报分析结构化技术大全 |

---

## 使用方式

让 CC 直接读源码分析：
```
请阅读 /home/user/workspace/gitcode/aegi/references/opensource/dowhy/dowhy/causal_model.py
分析其因果推断的核心接口设计，评估是否适合集成到 AEGI...
```
