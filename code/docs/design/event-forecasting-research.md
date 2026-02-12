<!-- Author: msq -->
# 方向 2：事件预测与预判 — 深度调研报告

## 搜索过程记录

### Round 1: 地缘政治事件预测 + 机器学习
- 关键词: `event forecasting machine learning geopolitical prediction 2024 2025 2026`
- 发现: arXiv 上有多篇 2025-2026 年新论文，LLM 用于地缘事件预测是当前热点

### Round 2: GDELT 事件预测模型
- 关键词: `GDELT event prediction model neural network`
- 发现: STFT-VNNGP（Sparse Temporal Fusion Transformer + Gaussian Process）直接基于 GDELT 数据做冲突预测，获 2023 年威胁检测竞赛冠军

### Round 3: 时序点过程
- 关键词: `temporal point process event prediction Hawkes process neural`
- 发现: 20+ 篇相关论文，从经典 Hawkes Process 到 Transformer Hawkes Process (THP)、Mamba Hawkes Process (MHP)，演化路径清晰

### Round 4: 冲突预测与预警系统
- 关键词: `conflict prediction AI crisis early warning system machine learning`
- 发现: ViEWS（Violence & Impacts Early-Warning System）是最成熟的开源冲突预警系统，Uppsala 大学维护，月度发布预测

### Round 5: 超级预测与聚合算法
- 关键词: `superforecasting algorithm prediction aggregation Tetlock`
- 发现: Satopaa/Ungar 的 extremizing 框架提供了预测聚合的理论基础；Halawi et al. 2024 证明 LLM + 检索增强可接近人类预测水平

### Round 6: ICEWS/CAMEO 事件编码
- 关键词: `ICEWS CAMEO event coding prediction automation`
- 发现: POLECAT 数据库作为 GDELT/ICEWS 的新一代替代正在被多篇论文采用

### Round 7: 预测市场聚合
- 关键词: `prediction market aggregation algorithm Metaculus Polymarket`
- 发现: TruthTensor 框架用预测市场评估 LLM；一致性检查（arbitrage-based consistency）可实时评估预测质量

### Round 8: 开源项目
- 关键词: `github event forecasting geopolitical prediction open source`
- 发现: MIRAI（90 stars）、EasyTPP（333 stars）、ViEWS pipeline 是三个最相关的开源项目

---

## 核心论文（精选 5 篇）

### 论文 1: MIRAI — 评估 LLM Agent 的事件预测能力

- **标题**: MIRAI: Evaluating LLM Agents for Event Forecasting
- **作者**: Yecchen et al.
- **年份**: 2024
- **会议/期刊**: arXiv preprint
- **arXiv ID**: [2407.01231](https://arxiv.org/abs/2407.01231)

**核心贡献**:
MIRAI 是首个系统评估 LLM Agent 国际事件预测能力的 benchmark。基于清洗后的 GDELT 事件数据库构建预测任务，支持短期到长期不同预测窗口。Agent 需自主从全球数据库检索信息、编写代码调用领域 API、对多格式历史知识做时序推理。评估了 GPT-4o、Mistral 等模型在 Direct IO、CoT、ReAct 三种策略下的表现。

**与 AEGI 的关联**:
AEGI 已有 GDELT monitor + pipeline 架构，MIRAI 的 agentic 预测范式可直接复用。其 GDELT 数据清洗和任务构建方法可作为 AEGI 预测模块的数据预处理参考。ReAct 策略与 AEGI 的 pipeline orchestrator 天然契合。

---

### 论文 2: STFT-VNNGP — 基于 GDELT 的冲突预测混合模型

- **标题**: Forecasting Geopolitical Events with a Sparse Temporal Fusion Transformer and Gaussian Process Hybrid
- **作者**: Hsin-Hsiung Huang, Hayden Hampton
- **年份**: 2025
- **会议/期刊**: arXiv preprint
- **arXiv ID**: [2506.20935](https://arxiv.org/abs/2506.20935)

**核心贡献**:
针对 GDELT 数据稀疏性和突发性导致标准深度学习模型长期预测不可靠的问题，提出两阶段混合方法：第一阶段用 Temporal Fusion Transformer 生成多分位数预测捕获时序动态，第二阶段用 Variational Nearest Neighbor Gaussian Process (VNNGP) 做时空平滑和不确定性量化。获 2023 年 Algorithms for Threat Detection 竞赛冠军。案例聚焦中东和美国冲突动态。

**与 AEGI 的关联**:
直接基于 GDELT 数据，与 AEGI 的 gdelt_monitor 数据源完全一致。TFT + GP 的混合架构可作为 AEGI 预测引擎的核心模型。不确定性量化能力与 AEGI 的贝叶斯 ACH 互补——ACH 评估假设可信度，STFT-VNNGP 量化事件发生概率的置信区间。

---

### 论文 3: Transformer Hawkes Process (THP)

- **标题**: Transformer Hawkes Process
- **作者**: Simiao Zuo, Haoming Jiang, Zichong Li, Tuo Zhao, Hongyuan Zha
- **年份**: 2020 (ICML 2020)
- **会议/期刊**: ICML 2020
- **arXiv ID**: [2002.09291](https://arxiv.org/abs/2002.09291)

**核心贡献**:
将 self-attention 机制引入时序点过程建模，解决 RNN-based 点过程模型难以捕获长程依赖的问题。在似然估计和事件预测精度上超越已有 RNN 模型，同时保持计算效率。还展示了结合结构知识（关系信息）学习多个点过程的能力。

**与 AEGI 的关联**:
THP 是 EasyTPP 库的核心模型之一，可直接通过 EasyTPP 集成到 AEGI。AEGI 的 GDELT 事件流天然是异步事件序列，THP 的 self-attention 机制能捕获事件间的长程因果关系。结合 AEGI 的知识图谱（Neo4j），可实现 "结构感知的事件预测"。

---

### 论文 4: Approaching Human-Level Forecasting with Language Models

- **标题**: Approaching Human-Level Forecasting with Language Models
- **作者**: Halawi, Shlegeris, Steinhardt et al.
- **年份**: 2024
- **会议/期刊**: arXiv preprint
- **arXiv ID**: [2402.18563](https://arxiv.org/abs/2402.18563)

**核心贡献**:
构建了检索增强 LLM 预测系统，自动搜索相关信息、生成预测、聚合多个预测结果。在竞争性预测平台的大规模数据集上评估，系统接近甚至在部分场景超越人类预测者的群体聚合水平。使用模型知识截止日期之后发布的测试数据确保评估公正性。证明 LLM 可为机构决策提供可扩展的预测能力。

**与 AEGI 的关联**:
这是 AEGI 预测模块最直接的参考架构。AEGI 已有 LLMClient + SearXNG 检索 + pipeline orchestrator，可直接实现类似的 "检索→生成→聚合" 预测流水线。论文的聚合策略（多次采样 + 聚合）可与 AEGI 的贝叶斯 ACH 结合，用 ACH 作为结构化聚合框架。

---

### 论文 5: ONSEP — 在线神经符号事件预测框架

- **标题**: ONSEP: A Novel Online Neural-Symbolic Framework for Event Prediction Based on Large Language Model
- **作者**: Xuanqing Yu, Wangtao Sun, Jingwei Li, Kang Liu, Chengbao Liu, Jie Tan
- **年份**: 2024
- **会议/期刊**: arXiv preprint
- **arXiv ID**: [2408.07840](https://arxiv.org/abs/2408.07840)

**核心贡献**:
结合动态因果规则挖掘（DCRM）和双历史增强生成（DHAG）的神经符号框架。DCRM 从实时数据动态构建因果规则，快速适应新因果关系；DHAG 用双分支方法融合短期和长期历史上下文。在多个时序知识图谱数据集上取得显著 Hit@k 提升，且无需大规模 LLM 微调。

**与 AEGI 的关联**:
ONSEP 的神经符号方法与 AEGI 的架构高度契合：AEGI 已有 Neo4j 知识图谱（符号层）+ LLM（神经层）+ DoWhy 因果推断。DCRM 的动态因果规则挖掘可增强 AEGI 的 DoWhy 因果分析，DHAG 的双历史机制可改进 AEGI pipeline 的时序推理能力。

---

## 补充论文（值得关注）

| 论文 | arXiv ID | 年份 | 关键点 |
|------|----------|------|--------|
| ThinkTank-ME: Multi-Expert Framework for Middle East Event Forecasting | [2601.17065](https://arxiv.org/abs/2601.17065) | 2026 | 多专家协作预测，模拟智库分析流程 |
| Do LLMs Know Conflict? Parametric vs Non-Parametric Knowledge | [2505.09852](https://arxiv.org/abs/2505.09852) | 2025 | LLM 参数知识 vs RAG 外部数据的冲突预测对比 |
| Toward Better Temporal Structures for Geopolitical Events Forecasting | [2601.00430](https://arxiv.org/abs/2601.00430) | 2026 | 超关系时序知识图谱 + POLECAT 数据集 |
| Mamba Hawkes Process | [2407.05302](https://arxiv.org/abs/2407.05302) | 2024 | Mamba SSM 架构用于 Hawkes 过程，长程依赖 |
| Graph Hawkes Neural Network for TKG Forecasting | [2003.13432](https://arxiv.org/abs/2003.13432) | 2020 | 图结构 Hawkes 过程，时序知识图谱预测 |
| Consistency Checks for LM Forecasters | [2412.18544](https://arxiv.org/abs/2412.18544) | 2024 | 基于套利的一致性指标，实时评估预测质量 |
| TruthTensor: LLM Evaluation on Prediction Markets | [2601.13545](https://arxiv.org/abs/2601.13545) | 2026 | 用预测市场评估 LLM，漂移诊断 |
| Extremizing Forecast Aggregation | [1406.2148](https://arxiv.org/abs/1406.2148) | 2014 | 预测聚合极端化理论，信息重叠建模 |
| SPARK: LLM-based TKG Forecasting | [2503.22748](https://arxiv.org/abs/2503.22748) | 2025 | Beam 序列生成 + TKG Adapter，高效 LLM 预测 |

---

## 开源项目（精选 3 个）

### 项目 1: EasyTPP — 时序点过程工具库

- **GitHub**: [ant-research/EasyTemporalPointProcess](https://github.com/ant-research/EasyTemporalPointProcess)
- **Stars**: 333
- **最近更新**: 2025 年 11 月（活跃维护）
- **License**: Apache 2.0
- **论文**: [2307.08097](https://arxiv.org/abs/2307.08097) (ICLR 2024)

**核心功能**:
蚂蚁集团开源的 PyTorch 时序点过程开发工具库。内置 9 个经典模型实现：RMTPP、NHP、FullyNN、SAHP、THP、IntensityFree、ODETPP、AttNHP、S2P2。支持模块化配置、Optuna 超参优化、HuggingFace 数据集加载。提供 6+ 预处理数据集（Synthetic Hawkes、Retweet、StackOverflow、Taobao 等）。

**集成可行性评估**: ★★★★★（高）
- PyTorch 实现，与 AEGI 的 Python 技术栈完全兼容
- `pip install easy-tpp` 即可安装，零侵入
- 模块化设计，可单独使用模型组件
- 配置驱动，适合 AEGI 的 pipeline 架构

**具体集成建议**:
1. 将 GDELT 事件流转换为 EasyTPP 的事件序列格式（timestamp + event_type + marks）
2. 用 THP 或 AttNHP 模型训练事件预测器，预测下一事件的类型和时间
3. 封装为 `EventForecaster` 服务，注入 AEGI pipeline 作为新 stage
4. 利用 Optuna 集成做自动超参搜索，按地区/事件类型训练专用模型
5. 预测结果输出为 `ForecastResult` Pydantic model，包含事件类型概率分布 + 时间分布 + 置信区间

---

### 项目 2: MIRAI — LLM Agent 事件预测 Benchmark

- **GitHub**: [yecchen/MIRAI](https://github.com/yecchen/MIRAI)
- **Stars**: 90
- **最近更新**: 2024 年 7 月
- **License**: 未标注
- **论文**: [2407.01231](https://arxiv.org/abs/2407.01231)

**核心功能**:
评估 LLM Agent 国际事件预测能力的 benchmark 框架。基于清洗后的 GDELT 数据构建预测任务，支持 Direct IO / CoT / ReAct 三种 agent 策略。提供结构化历史事件数据库 API 和新闻文章检索工具。支持 GPT-4o、Mistral 等多模型评估。

**集成可行性评估**: ★★★★☆（中高）
- GDELT 数据清洗和任务构建逻辑可直接复用
- Agent 策略（特别是 ReAct）与 AEGI pipeline 架构兼容
- 需要适配 AEGI 的 LLMClient 和 SearXNG 检索

**具体集成建议**:
1. 复用 MIRAI 的 GDELT 数据清洗 pipeline，增强 AEGI 的 `gdelt_monitor` 数据质量
2. 参考 ReAct agent 策略，在 AEGI pipeline 中实现 "检索→推理→预测" 循环
3. 将 MIRAI 的评估指标（预测准确率、校准度）集成到 AEGI 的预测质量监控
4. 用 MIRAI 的任务格式构建 AEGI 的预测训练/评估数据集

---

### 项目 3: ViEWS — 暴力冲突预警系统

- **GitHub**: [prio-data/views_pipeline](https://github.com/prio-data/views_pipeline) + [prio-data/viewsforecasting](https://github.com/prio-data/viewsforecasting)
- **Stars**: 7 + 15
- **最近更新**: 2025 年 11 月 / 2026 年 1 月（活跃维护）
- **License**: 未标注
- **机构**: Uppsala 大学 / PRIO（奥斯陆和平研究所）

**核心功能**:
全球最成熟的开源冲突预警系统，每月发布 1-36 个月的武装冲突预测。基于 UCDP-GED（地理编码事件数据集）训练集成模型，支持国家级和次国家级预测。采用 Prefect 编排的 MLOps pipeline，包含模型训练、评估、部署全流程。数据处理包括缺失值插补、对数缩放、时间衰减函数、空间/时间滞后。

**集成可行性评估**: ★★★☆☆（中）
- 数据源不同（ViEWS 用 UCDP，AEGI 用 GDELT），但 CAMEO 编码体系兼容
- 集成模型方法论（多模型加权集成）可直接借鉴
- pipeline 架构（Prefect）与 AEGI 的 pipeline orchestrator 理念一致
- 代码量大，完整集成成本高，建议选择性借鉴

**具体集成建议**:
1. 借鉴 ViEWS 的集成模型方法论：多个子模型 + 加权集成 + 校准
2. 参考其特征工程：时间衰减、空间滞后、邻域效应等，应用到 AEGI 的 GDELT 数据
3. 复用其评估框架：月度预测 + 滚动窗口验证 + 多尺度评估
4. 不建议直接集成代码，而是提取方法论应用到 AEGI 自己的 pipeline 中

---

## 关键发现与建议

### 发现 1: LLM + 检索增强是当前事件预测的主流范式

2024-2026 年的论文几乎全部围绕 LLM 展开。Halawi et al. 证明检索增强 LLM 可接近人类超级预测者水平，MIRAI 提供了系统评估框架，ThinkTank-ME 展示了多专家协作预测的优势。AEGI 已有 LLMClient + SearXNG + pipeline，实现这一范式的基础设施已就绪。

**建议**: 优先实现 "检索增强 LLM 预测" 作为 AEGI 预测模块的第一版，复用现有基础设施，快速出 MVP。

### 发现 2: 时序点过程是事件时间预测的理论基础

从经典 Hawkes Process → THP (2020) → AttNHP (2022) → Mamba Hawkes (2024)，时序点过程模型持续演进。EasyTPP 库提供了 9 个模型的统一实现，降低了集成门槛。这类模型擅长回答 "下一个事件什么时候发生" 和 "什么类型的事件最可能发生"。

**建议**: 用 EasyTPP 的 THP/AttNHP 模型作为 AEGI 的 "事件时间预测器"，与 LLM 预测互补——LLM 负责语义层面的预测（"会发生什么"），点过程模型负责时间层面的预测（"什么时候发生"）。

### 发现 3: 时序知识图谱预测是连接 KG 和预测的桥梁

ONSEP、SPARK、G2S 等论文展示了在时序知识图谱上做链接预测的方法。AEGI 已有 Neo4j 知识图谱 + 时序事件追踪，天然适合这一方向。Graph Hawkes Neural Network 直接将 Hawkes 过程应用于图结构，是连接发现 2 和 KG 的关键。

**建议**: 将 AEGI 的 Neo4j 事件图谱建模为时序知识图谱，用 ONSEP 的神经符号方法做关系预测。这与 AEGI 已有的 DoWhy 因果推断形成互补：DoWhy 分析已知因果关系，TKG 预测发现新的潜在关系。

### 发现 4: 预测聚合和校准是提升预测质量的关键

Satopaa/Ungar 的 extremizing 理论、Consistency Checks 的套利一致性指标、TruthTensor 的漂移诊断，都指向同一个问题：单一预测不可靠，需要多源聚合 + 质量校准。

**建议**: 在 AEGI 中实现预测聚合层：
1. 多次 LLM 采样 + extremizing 聚合（参考 Satopaa 理论）
2. 一致性检查（参考 Consistency Checks 论文的套利指标）
3. 与贝叶斯 ACH 结合——ACH 的假设评分本身就是一种结构化聚合

### 发现 5: GDELT 数据的稀疏性和突发性是核心挑战

STFT-VNNGP 论文明确指出标准深度学习模型在 GDELT 长期预测上不可靠，根因是数据稀疏和突发性。这与 AEGI 的 gdelt_monitor 面临的问题一致。

**建议**: 采用 STFT-VNNGP 的两阶段方法：先用 TFT 捕获时序模式，再用 GP 做不确定性量化。在 AEGI 的预测结果中必须包含置信区间，避免给用户虚假的确定性。

---

## AEGI 预测模块建议架构

```
┌─────────────────────────────────────────────────────┐
│                  Prediction Pipeline                 │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌───────────┐  ┌───────────┐  ┌────────────────┐  │
│  │  GDELT    │  │  Neo4j    │  │  SearXNG       │  │
│  │  Monitor  │  │  KG Store │  │  Search        │  │
│  └─────┬─────┘  └─────┬─────┘  └───────┬────────┘  │
│        │              │                 │           │
│        ▼              ▼                 ▼           │
│  ┌─────────────────────────────────────────────┐    │
│  │         Feature Engineering Layer            │    │
│  │  (时间衰减 / 空间滞后 / 事件编码 / 嵌入)     │    │
│  └──────────────────┬──────────────────────────┘    │
│                     │                               │
│        ┌────────────┼────────────┐                  │
│        ▼            ▼            ▼                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐        │
│  │ EasyTPP  │ │ LLM      │ │ TKG          │        │
│  │ (THP/    │ │ Forecast │ │ Link         │        │
│  │  AttNHP) │ │ (ReAct)  │ │ Prediction   │        │
│  │ 时间预测  │ │ 语义预测  │ │ 关系预测      │        │
│  └────┬─────┘ └────┬─────┘ └──────┬───────┘        │
│       │            │              │                 │
│       ▼            ▼              ▼                 │
│  ┌─────────────────────────────────────────────┐    │
│  │       Prediction Aggregation Layer           │    │
│  │  (Extremizing + Consistency Check + ACH)     │    │
│  └──────────────────┬──────────────────────────┘    │
│                     │                               │
│                     ▼                               │
│  ┌─────────────────────────────────────────────┐    │
│  │       ForecastResult (Pydantic Model)        │    │
│  │  event_type / probability / time_window /    │    │
│  │  confidence_interval / evidence_chain /       │    │
│  │  contributing_sources                        │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 实施优先级

| 优先级 | 模块 | 依赖 | 预估工作量 |
|--------|------|------|-----------|
| P0 | LLM 检索增强预测（ReAct 策略） | LLMClient + SearXNG + GDELT monitor | 3-5 天 |
| P1 | EasyTPP 事件时间预测器 | GDELT 事件序列数据 | 3-5 天 |
| P1 | 预测聚合层（extremizing + 一致性检查） | P0 完成 | 2-3 天 |
| P2 | TKG 关系预测 | Neo4j KG + 时序建模 | 5-7 天 |
| P2 | 不确定性量化（GP 层） | P1 完成 | 3-5 天 |

### 数据流与证据链

预测结果必须遵循 AEGI 的 Evidence-first 红线：

```
ForecastResult → Judgment（预测判断）
  → Assertion（基于什么断言）
    → SourceClaim（来自哪些数据源的声明）
      → Evidence（GDELT 事件 / 新闻 / KG 关系）
        → ArtifactVersion（原始数据快照）
```

每个预测必须可追溯到具体的 GDELT 事件、新闻来源和 KG 关系，不允许 "黑箱预测"。
