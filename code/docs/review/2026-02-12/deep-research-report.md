<!-- Author: msq -->
# AEGI 深度学术调研报告

> 日期：2026-02-12
> 调研范围：8 个方向，60+ 篇论文，30+ 个开源项目
> 搜索轮次：64+ 轮 WebSearch + 100+ 次 WebFetch 深度抓取

## 执行摘要

本次调研覆盖 LLM+情报分析、事件预测、因果推断、知识图谱推理、虚假信息检测、多源融合、态势感知、人机协作 8 个方向。核心发现：

1. **LLM 预测能力已接近但未超越人类专家**（ForecastBench, AIA Forecaster），AEGI 应定位为"增强分析师"而非"替代分析师"。结构化论证框架（MArgE 论证树、CheckWhy 因果验证）是提升 LLM 可靠性的关键。
2. **时序因果发现是 AEGI 最大增量价值点**。AEGI 有两个独立因果模块（DoWhy 路径 + LLM 路径）但未统一，ALCM 框架提供了"数据驱动发现→LLM 精炼→DoWhy 估计"的三阶段蓝图。tigramite PCMCI 可从 GDELT 时序数据发现滞后因果关系。
3. **Dempster-Shafer 理论是贝叶斯 ACH 的天然互补**。DS 层处理 SourceClaim→Assertion 的证据融合，Bayesian 层处理 Assertion→Judgment 的假设更新。当前 assertion_fuser 的硬编码 confidence（0.5/0.9）应升级为 DS 组合规则。
4. **LLM 正在颠覆 TKG 推理范式**。GenTKG 和 ICL-TKG 证明 LLM 仅通过 in-context learning 即可达到专用 TKG 模型水平，AEGI 无需从零训练模型。Think-on-Graph 的迭代 beam search 可升级当前 2-hop 邻居方案。
5. **多 Agent 辩论是 2025 年事实核查主流范式**（D2D EMNLP 2025），可作为 AEGI pipeline 的 claim_verification stage。DISARM 框架（MITRE ATT&CK 风格）是信息操作分类的事实标准。
6. **态势感知需从硬阈值升级为概率化检测**。BOCPD + River ADWIN 做在线检测，PELT + Matrix Profile 做离线确认，BERTopic partial_fit 做新兴话题发现。
7. **反馈闭环决定人机协同效果**。74 项研究元分析表明：反馈+解释=正向协同，只有解释没有反馈=负向协同。AEGI 需增加 Assertion 反馈 API。

---

## 方向 1：LLM + 情报分析（核心方向）

### 搜索过程记录

共执行 8 轮主搜索 + 多轮补充搜索：

| 轮次 | 关键词 | 主要收获 |
|------|--------|----------|
| 1 | `LLM intelligence analysis AI assisted analytic tradecraft` | IARPA REASON 项目线索 |
| 2 | `large language model structured analytic techniques hypothesis generation` | Solomonoff 假设排序、LLM 标准化分析流程 |
| 3 | `IARPA AI intelligence community automated analysis` | IARPA REASON 项目（BAA W911NF-23-S-0007） |
| 4 | `multi-agent LLM geopolitical analysis forecasting` | AIA Forecaster、Autocast、冲突预测 |
| 5 | `LLM cognitive bias detection intelligence assessment reliability` | Choice-Supportive Bias 消除、System 1/2 去偏 |
| 6 | `AI assisted analysis of competing hypotheses ACH` | VivaBench 假设固着问题 |
| 7 | `LLM evidence assessment national security intelligence` | MArgE 论证树、CheckWhy 因果验证、HalluHard 幻觉基准 |
| 8 | `automated intelligence report generation NLP` | STORM 研究报告生成、ConvergeWriter |

### 核心论文（精选 5 篇）

#### 1. Approaching Human-Level Forecasting with Language Models
- **作者**: Danny Halawi, Fred Zhang, Chen Yueh-Han, Jacob Steinhardt
- **年份**: 2024 | **arXiv**: [2402.18563](https://arxiv.org/abs/2402.18563)
- **核心贡献**: 基于检索增强的 LLM 预测系统，在竞争性预测平台上接近人类预测者群体聚合水平。三阶段：搜索相关信息→生成预测→聚合多次预测。
- **与 AEGI 的关联**: 直接适用于 `hypothesis_engine` 和 `gdelt_monitor`。建议在 `PipelineOrchestrator` 中增加"证据检索→LLM 概率评估→聚合校准"三阶段预测流水线。

#### 2. ForecastBench: A Dynamic Benchmark of AI Forecasting Capabilities
- **作者**: Ezra Karger, Houtan Bastani, Chen Yueh-Han, Zachary Jacobs, Danny Halawi, Fred Zhang, **Philip E. Tetlock**
- **年份**: 2024（ICLR 2025）| **arXiv**: [2409.19839](https://arxiv.org/abs/2409.19839)
- **核心贡献**: Tetlock 团队参与的动态预测基准，1000 个自动生成问题。核心发现：专家预测者显著优于最佳 LLM（p < 0.001）。
- **与 AEGI 的关联**: 引入预测校准度指标到 `report_generator`；用 ForecastBench 问题格式作为假设评估标准化模板。

#### 3. MArgE: Meshing Argumentative Evidence from Multiple LLMs
- **作者**: Ming Pok Ng, Junqi Jiang, Gabriel Freedman, Antonio Rago, Francesca Toni
- **年份**: 2025 | **arXiv**: [2508.02584](https://arxiv.org/abs/2508.02584)
- **核心贡献**: 多 LLM 论证树框架用于声明验证。每个 LLM 生成结构化论证树，通过计算论证学框架聚合。从初始论据到最终决策的完整可检查路径。
- **与 AEGI 的关联**: 对 AEGI 证据链架构（Judgment→Assertion→SourceClaim→Evidence）最直接的学术验证。建议在 `claim_extractor` 中引入论证树结构，在 `hypothesis_engine` 中用多 LLM 论证聚合替代单次评估。

#### 4. AIA Forecaster: Technical Report
- **作者**: Rohan Alur, Bradly C. Stadie, Daniel Kang 等 14 人
- **年份**: 2025 | **arXiv**: [2511.07678](https://arxiv.org/abs/2511.07678)
- **核心贡献**: 首个在 ForecastBench 上达到专家级预测水平的 LLM 系统。三大组件：Agent 新闻搜索、Supervisor Agent 协调、统计校准去偏。
- **与 AEGI 的关联**: 架构与 `PipelineOrchestrator` 高度对应。建议引入 Supervisor Agent 模式和 Platt scaling 校准层。

#### 5. Increasing AI Explainability by LLM Driven Standard Processes
- **作者**: Marc Jansen, Marcel Pehlke
- **年份**: 2025 | **arXiv**: [2511.07083](https://arxiv.org/abs/2511.07083)
- **核心贡献**: 将 LLM 嵌入标准化分析框架（QOC、敏感性分析、博弈论），将不透明推理转化为可审计决策轨迹。
- **与 AEGI 的关联**: 在 `hypothesis_engine` 中实现 QOC 框架作为 ACH 补充；在 `report_generator` 中增加决策轨迹章节。

#### 补充重要论文

| 论文 | 年份 | 关键贡献 | AEGI 关联 |
|------|------|----------|-----------|
| [CheckWhy](https://arxiv.org/abs/2408.10918) (ACL 2024 杰出论文) | 2024 | 19K+ 因果声明-证据-论证三元组 | 训练/评估 `claim_extractor` 因果推理 |
| [HalluHard](https://arxiv.org/abs/2602.01031) | 2026 | 高风险领域幻觉率约 30% | 证据链中必须内建幻觉检测 |
| [Do LLMs Know Conflict?](https://arxiv.org/abs/2505.09852) | 2025 | RAG 增强显著提升冲突预测 | 验证 GDELT+RAG 架构方向正确 |
| [STORM](https://arxiv.org/abs/2402.14207) (EMNLP 2024) | 2024 | 多视角研究+模拟专家对话 | 直接适用于 `report_generator` 改进 |

### 开源项目（精选 3 个）

#### 1. STORM (Stanford) — 27,900+ stars
- **GitHub**: [stanford-oval/storm](https://github.com/stanford-oval/storm)
- **核心功能**: LLM 驱动的研究报告自动生成。两阶段：预写（多视角研究、模拟专家对话）+ 写作（带引用长文生成）。支持 SearXNG + litellm。
- **集成建议**: 将多视角研究阶段集成到 `report_generator`；STORM 的 VectorRM 对接 Qdrant `aegi_chunks` 集合；Co-STORM 模式实现人机协作报告编写。预估 2-3 周。

#### 2. CrewAI — 44,000+ stars
- **GitHub**: [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI)
- **核心功能**: 轻量级多 Agent 协作框架。Crews（角色化团队）+ Flows（事件驱动工作流）。
- **集成建议**: 不建议全量引入，借鉴 Crew 模式在 `hypothesis_engine` 中实现红队/蓝队/魔鬼代言人多视角评估。

#### 3. OpenCTI — 8,200+ stars
- **GitHub**: [OpenCTI-Platform/opencti](https://github.com/OpenCTI-Platform/opencti)
- **核心功能**: 开源网络威胁情报管理平台，STIX2 标准，GraphQL API，连接器生态。
- **集成建议**: 借鉴 STIX2 数据模型设计情报对象标准化表示；参考连接器架构设计外部数据源集成模式。

### 关键发现与建议

1. **LLM 预测接近但未超越专家**：AEGI 应定位为"增强分析师"，LLM 输出必须经人类审核，突出不确定性。
2. **结构化论证框架是可靠性关键**：MArgE 论证树 + CheckWhy 因果验证 + 标准化分析流程，将自由文本推理约束在结构化框架中。AEGI 证据链方向正确，应进一步引入论证树结构。
3. **幻觉问题严重**：HalluHard 显示即使有 Web 搜索，前沿模型幻觉率约 30%。Evidence-first 红线必须严格执行。
4. **多 Agent + 统计校准是下一步**：Supervisor Agent 模式 + Platt scaling 校准 + STORM 多视角研究。

---

## 方向 2：事件预测与预判

### 搜索过程记录

| 轮次 | 关键词 | 主要收获 |
|------|--------|----------|
| 1 | `event forecasting machine learning geopolitical prediction` | LLM 地缘事件预测是当前热点 |
| 2 | `GDELT event prediction model neural network` | STFT-VNNGP 冲突预测竞赛冠军 |
| 3 | `temporal point process event prediction Hawkes process neural` | 20+ 篇，THP→AttNHP→Mamba Hawkes 演化清晰 |
| 4 | `conflict prediction AI crisis early warning system` | ViEWS 最成熟开源冲突预警系统 |
| 5 | `superforecasting algorithm prediction aggregation Tetlock` | extremizing 聚合理论 |
| 6 | `ICEWS CAMEO event coding prediction automation` | POLECAT 新一代数据库 |
| 7 | `prediction market aggregation algorithm Metaculus Polymarket` | TruthTensor、一致性检查 |
| 8 | `github event forecasting geopolitical prediction open source` | MIRAI、EasyTPP、ViEWS |

### 核心论文（精选 5 篇）

#### 1. MIRAI: Evaluating LLM Agents for Event Forecasting
- **作者**: Yecchen et al. | **年份**: 2024 | **arXiv**: [2407.01231](https://arxiv.org/abs/2407.01231)
- **核心贡献**: 首个系统评估 LLM Agent 国际事件预测能力的 benchmark，基于清洗后 GDELT 数据，支持 Direct IO/CoT/ReAct 三种策略。
- **与 AEGI 的关联**: GDELT 数据清洗和 ReAct 策略可直接复用于 AEGI pipeline。

#### 2. STFT-VNNGP: 基于 GDELT 的冲突预测混合模型
- **作者**: Hsin-Hsiung Huang, Hayden Hampton | **年份**: 2025 | **arXiv**: [2506.20935](https://arxiv.org/abs/2506.20935)
- **核心贡献**: TFT 多分位数预测 + VNNGP 时空平滑和不确定性量化。2023 年威胁检测竞赛冠军。
- **与 AEGI 的关联**: 直接基于 GDELT 数据，不确定性量化与贝叶斯 ACH 互补。

#### 3. Transformer Hawkes Process (THP)
- **作者**: Simiao Zuo et al. | **年份**: 2020 (ICML) | **arXiv**: [2002.09291](https://arxiv.org/abs/2002.09291)
- **核心贡献**: Self-attention 引入时序点过程，解决长程依赖问题。
- **与 AEGI 的关联**: 通过 EasyTPP 库集成，GDELT 事件流天然是异步事件序列。

#### 4. Approaching Human-Level Forecasting with Language Models
- **作者**: Halawi et al. | **年份**: 2024 | **arXiv**: [2402.18563](https://arxiv.org/abs/2402.18563)
- **核心贡献**: 检索增强 LLM 预测系统接近人类群体聚合水平。
- **与 AEGI 的关联**: AEGI 已有 LLMClient + SearXNG + pipeline，可直接实现"检索→生成→聚合"预测流水线。

#### 5. ONSEP: 在线神经符号事件预测框架
- **作者**: Xuanqing Yu et al. | **年份**: 2024 | **arXiv**: [2408.07840](https://arxiv.org/abs/2408.07840)
- **核心贡献**: 动态因果规则挖掘（DCRM）+ 双历史增强生成（DHAG），无需 LLM 微调。
- **与 AEGI 的关联**: 神经符号方法与 AEGI 架构高度契合（Neo4j 符号层 + LLM 神经层 + DoWhy 因果）。

#### 补充论文

| 论文 | arXiv | 年份 | 关键点 |
|------|-------|------|--------|
| ThinkTank-ME | [2601.17065](https://arxiv.org/abs/2601.17065) | 2026 | 多专家协作预测 |
| Mamba Hawkes Process | [2407.05302](https://arxiv.org/abs/2407.05302) | 2024 | Mamba SSM 长程依赖 |
| SPARK: LLM-based TKG Forecasting | [2503.22748](https://arxiv.org/abs/2503.22748) | 2025 | Beam 序列生成 + TKG Adapter |
| Consistency Checks for LM Forecasters | [2412.18544](https://arxiv.org/abs/2412.18544) | 2024 | 套利一致性指标 |
| Extremizing Forecast Aggregation | [1406.2148](https://arxiv.org/abs/1406.2148) | 2014 | 预测聚合极端化理论 |

### 开源项目（精选 3 个）

#### 1. EasyTPP — 333 stars
- **GitHub**: [ant-research/EasyTemporalPointProcess](https://github.com/ant-research/EasyTemporalPointProcess)
- **核心功能**: 蚂蚁集团开源，9 个时序点过程模型（THP、AttNHP 等），Optuna 超参优化，ICLR 2024 论文。
- **集成建议**: GDELT 事件流→EasyTPP 事件序列格式→THP/AttNHP 训练→封装为 `EventForecaster` 服务。

#### 2. MIRAI — 90 stars
- **GitHub**: [yecchen/MIRAI](https://github.com/yecchen/MIRAI)
- **核心功能**: LLM Agent 事件预测 benchmark，GDELT 数据清洗 + ReAct agent 策略。
- **集成建议**: 复用 GDELT 数据清洗 pipeline，参考 ReAct 策略实现"检索→推理→预测"循环。

#### 3. ViEWS — Uppsala 大学冲突预警系统
- **GitHub**: [prio-data/views_pipeline](https://github.com/prio-data/views_pipeline)
- **核心功能**: 全球最成熟开源冲突预警，月度 1-36 个月预测，集成模型 + MLOps pipeline。
- **集成建议**: 借鉴集成模型方法论和特征工程（时间衰减、空间滞后），不建议直接集成代码。

### 关键发现与建议

1. **LLM + 检索增强是主流范式**：AEGI 基础设施已就绪，优先实现检索增强 LLM 预测作为 MVP。
2. **时序点过程是事件时间预测的理论基础**：LLM 负责"会发生什么"，点过程模型负责"什么时候发生"。
3. **预测聚合和校准是质量关键**：多次 LLM 采样 + extremizing 聚合 + 一致性检查 + ACH 结构化聚合。
4. **GDELT 数据稀疏性是核心挑战**：采用 TFT+GP 两阶段方法，预测结果必须包含置信区间。

---

## 方向 3：因果推断在情报分析中的应用

### 搜索过程记录

| 轮次 | 关键词 | 主要收获 |
|------|--------|----------|
| 1 | `causal inference intelligence analysis geopolitical events` | 转向直接获取核心论文 |
| 2 | `causal discovery event data GDELT ICEWS` | tigramite/PCMCI 项目 |
| 3 | `DoWhy Microsoft causal inference Python` | PyWhy 完整生态（DoWhy + EconML + causal-learn） |
| 4 | `causal relation extraction NLP text mining` | DAPrompt 事件因果识别 |
| 5 | `counterfactual reasoning AI intelligence analysis` | CLadder 基准（NeurIPS 2023） |
| 6 | `causal inference knowledge graph reasoning` | pywhy-graphs 因果图表示 |
| 7 | `LLM causal reasoning causal inference` | Kiciman TMLR、Corr2Cause ICLR 2024、ALCM 框架 |
| 8 | `github causal discovery open source tools` | gCastle、causal-learn、tigramite 等 10+ 项目 |

### 核心论文（精选 5 篇）

#### 1. Causal Reasoning and Large Language Models: Opening a New Frontier
- **作者**: Emre Kiciman, Robert Ness, Amit Sharma, Chenhao Tan | **年份**: 2023 | **发表**: TMLR
- **arXiv**: [2305.00050](https://arxiv.org/abs/2305.00050)
- **核心贡献**: GPT-4 成对因果发现 97%、反事实推理 92%、事件因果 86%。能泛化到新数据集，但有不可预测失败模式。
- **与 AEGI 的关联**: 验证 `causal_reasoner.py` 用 LLM 做因果推理的可行性，fallback 到规则版本的设计是正确防御。

#### 2. Efficient Causal Graph Discovery Using Large Language Models
- **作者**: Thomas Jiralerspong, Xiaoyin Chen, Yash More, Vedant Shah, **Yoshua Bengio**
- **年份**: 2024 | **arXiv**: [2402.01207](https://arxiv.org/abs/2402.01207)
- **核心贡献**: BFS 方法将 LLM 因果图发现查询复杂度从 O(n²) 降到 O(n)，在真实因果图上达到 SOTA。
- **与 AEGI 的关联**: `build_causal_graph` 当前完全依赖图结构，可引入 BFS 方法用 LLM 判断因果方向。

#### 3. ALCM: Autonomous LLM-Augmented Causal Discovery Framework
- **作者**: Elahe Khatibi et al. | **年份**: 2024 | **arXiv**: [2405.01744](https://arxiv.org/abs/2405.01744)
- **核心贡献**: 数据驱动因果发现 + LLM 精炼的混合框架，7 个数据集上超越纯 LLM 和纯数据驱动方法。
- **与 AEGI 的关联**: 最直接可借鉴的架构——统一 `causal_inference.py`（DoWhy）和 `causal_reasoner.py`（LLM）为三阶段流水线。

#### 4. CLadder: Assessing Causal Reasoning in Language Models
- **作者**: Zhijing Jin et al. (Scholkopf 团队) | **年份**: 2023 | **发表**: NeurIPS 2023
- **arXiv**: [2312.04350](https://arxiv.org/abs/2312.04350)
- **核心贡献**: 10K 样本因果推理基准，发现 LLM 在形式化因果推理上表现很差。提出 CausalCoT 提示策略。
- **与 AEGI 的关联**: LLM 适合因果"发现"和"表述"，不适合"计算"。形式化推断交给 DoWhy。

#### 5. Causal Inference in NLP: Estimation, Prediction, Interpretation and Beyond
- **作者**: Amir Feder et al. | **年份**: 2022 | **发表**: TACL
- **arXiv**: [2109.00725](https://arxiv.org/abs/2109.00725)
- **核心贡献**: NLP 因果推断系统综述，覆盖文本作为结果/处理/混淆变量三大场景。
- **与 AEGI 的关联**: 指导因果模块设计——从新闻提取因果声明、评估事件因果影响、处理来源偏见作为混淆变量。

### 开源项目（精选 3 个）

#### 1. tigramite — 1,600+ stars (GPL-3.0)
- **GitHub**: [jakobrunge/tigramite](https://github.com/jakobrunge/tigramite)
- **核心功能**: 时序因果发现 PCMCI 及变体，多种条件独立性检验，因果效应估计和中介分析。
- **集成建议**: 新增 `discover_temporal_causes` 方法，从 GDELT 时序发现滞后因果关系（"A 国制裁→3 天后→B 国军事调动"）。注意 GPL 许可证需作为独立服务调用。

#### 2. gCastle (华为) — 1,100+ stars (Apache-2.0)
- **GitHub**: [huawei-noah/trustworthyAI/gcastle](https://github.com/huawei-noah/trustworthyAI/tree/master/gcastle)
- **核心功能**: 20+ 因果发现算法，NOTEARS 系列连续优化 DAG 学习，先验注入，评估指标。
- **集成建议**: 优先集成 NOTEARS，用 Neo4j 已知关系作为先验约束。Python 版本兼容性需测试。

#### 3. causal-learn (CMU) — 1,600+ stars (MIT)
- **GitHub**: [cmu-phil/causal-learn](https://github.com/cmu-phil/causal-learn)
- **核心功能**: Tetrad 的 Python 移植，PC 算法、Granger 因果、独立性检验。PyWhy 生态成员，与 DoWhy 天然兼容。
- **集成建议**: PC 算法做初始因果结构发现→LLM 定向无向边→DoWhy 效应估计。Granger 因果可作为 PCMCI 的轻量替代。

### 关键发现与建议

1. **AEGI 两个因果模块需统一**：`causal_inference.py`（DoWhy）和 `causal_reasoner.py`（LLM）完全独立。参考 ALCM 框架统一为：数据驱动发现→LLM 精炼→DoWhy 估计。
2. **LLM 因果能力边界明确**：擅长因果"发现"（97%），不擅长因果"计算"（接近随机）。让 LLM 构建图，DoWhy 做数值计算。
3. **时序因果发现是最大增量**：tigramite PCMCI 可从 GDELT 时序数据发现滞后因果关系，当前完全未利用。
4. **PyWhy 生态是最佳选择**：DoWhy + causal-learn + EconML，全部 MIT，API 兼容。

---

## 方向 4：知识图谱推理与时序推理

### 搜索过程记录

| 轮次 | 关键词 | 主要收获 |
|------|--------|----------|
| 1 | `temporal knowledge graph reasoning completion` | 转向 WebFetch 抓取已知资源 |
| 2 | `dynamic knowledge graph link prediction event forecasting` | 直接抓取项目 |
| 3 | `knowledge graph LLM reasoning beyond GraphRAG` | LightRAG、Think-on-Graph、RoG、KG-GPT |
| 4 | `graph neural network event prediction geopolitical` | ICEWS/GDELT 相关项目 |
| 5 | `temporal knowledge graph embedding TKG model` | GitHub topics 获取 TKG 项目列表 |
| 6 | `knowledge graph question answering intelligence analysis` | RoG (ICLR 2024) |
| 7 | `knowledge graph reasoning political security domain` | 通用 TKG 方法 + ICEWS/GDELT 数据集 |
| 8 | `github temporal knowledge graph open source` | 完整 TKG 项目列表 |

补充：抓取 tkger 仓库获取 100+ 篇 TKG 论文列表，深度抓取 RE-Net、LightRAG、GenTKG、ICL-TKG 等。

### 核心论文（精选 5 篇）

#### 1. GenTKG: Generative Forecasting on Temporal Knowledge Graph with LLMs
- **作者**: Ruotong Liao et al. | **年份**: 2024 | **会议**: Findings of NAACL 2024
- **链接**: [2310.07793](https://arxiv.org/abs/2310.07793)
- **核心贡献**: 检索增强生成框架，时序逻辑规则检索策略，仅需 16 个样本即可达到强性能，支持跨域零样本泛化。
- **与 AEGI 的关联**: 时序逻辑规则检索可复用 Neo4j 子图查询；生成式预测与 LLM pipeline 无缝衔接；few-shot 适合冷启动。

#### 2. Think-on-Graph: Deep and Responsible Reasoning of LLM on KG
- **作者**: Jiashuo Sun et al. | **年份**: 2024 | **会议**: ICLR 2024
- **链接**: [2307.07697](https://arxiv.org/abs/2307.07697)
- **核心贡献**: LLM⊗KG 范式，LLM 作为 agent 在 KG 上执行迭代 beam search。无需训练，即插即用。小模型+ToG 可超越 GPT-4 单独推理。
- **与 AEGI 的关联**: 推理路径可追溯性完美匹配证据链红线。建议替代当前 2-hop 邻居方案。

#### 3. Reasoning on Graphs (RoG): Faithful and Interpretable LLM Reasoning
- **作者**: Linhao Luo et al. | **年份**: 2024 | **会议**: ICLR 2024
- **链接**: [2310.01061](https://arxiv.org/abs/2310.01061)
- **核心贡献**: Planning-Retrieval-Reasoning 三阶段框架，KG 结构知识蒸馏到 LLM，KGQA 基准 SOTA。
- **与 AEGI 的关联**: 三阶段直接映射 AEGI pipeline：Planning→query_planner，Retrieval→Neo4j 查询，Reasoning→LLM 推理。

#### 4. TKG Forecasting Without Knowledge Using In-Context Learning
- **作者**: Dong-Ho Lee et al. | **年份**: 2023 | **会议**: EMNLP 2023
- **链接**: [2305.10613](https://arxiv.org/abs/2305.10613)
- **核心贡献**: LLM 仅通过 ICL 即可达到 SOTA TKG 模型水平。语义信息非必需（±0.4% Hit@1）。
- **与 AEGI 的关联**: 低成本 TKG 预测路径——从 Neo4j 提取历史序列→格式化 prompt→LLM 预测，与 `invoke_structured()` 完全兼容。

#### 5. TKGC 综述：时序知识图谱补全的分类体系
- **作者**: Jiapu Wang et al. | **年份**: 2023 | **链接**: [2308.02457](https://arxiv.org/abs/2308.02457)
- **核心贡献**: 插值（补全缺失）和外推（预测未来）两大类方法的完整分类体系。
- **与 AEGI 的关联**: 技术选型参考——图谱补全用 TComplEx/TNTComplEx，事件预测用 RE-GCN/RE-Net。

### 开源项目（精选 3 个）

#### 1. RE-Net — 457 stars
- **GitHub**: [INK-USC/RE-Net](https://github.com/INK-USC/RE-Net)
- **核心功能**: 循环事件编码器 + 邻域聚合器预测未来事实，支持 GDELT/ICEWS 五个数据集。
- **集成建议**: 提取核心模型为 `tkg_predictor.py`，预测结果写入 Neo4j 作为"预测边"。

#### 2. RoG — 494 stars
- **GitHub**: [RManLuo/reasoning-on-graphs](https://github.com/RManLuo/reasoning-on-graphs)
- **核心功能**: ICLR 2024 官方实现，Planning-Retrieval-Reasoning 框架，支持多种 LLM。
- **集成建议**: 提取 Planning 模块集成到 `graph_analysis.py`，编写 Neo4j→RoG 适配层。

#### 3. LightRAG — 28,300 stars
- **GitHub**: [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG)
- **核心功能**: 图增强 RAG，双层检索（实体+关系），直接支持 Neo4j/PostgreSQL，增量更新。
- **集成建议**: 作为 GraphRAG 升级方案，双层检索增强 `query_planner.py`。注意需 32B+ 模型。

### 关键发现与建议

1. **LLM 正在颠覆 TKG 推理范式**：GenTKG/ICL-TKG 证明无需训练专用模型，直接利用现有 LLM 后端。
2. **结构化引导优于暴力注入**：ToG/RoG 的 beam search/path planning 比 GraphRAG 的子图塞 prompt 更高效可解释。
3. **GDELT 是天然 TKG 资源**：RE-Net、HGLS、TFLEX 都支持 GDELT 格式，AEGI 数据管道可直接复用。
4. **可解释性是 KG 推理核心优势**：推理路径可映射到证据链，纯 LLM 推理无法提供。

---

## 方向 5：虚假信息检测与信息战分析

### 搜索过程记录

| 轮次 | 关键词 | 主要收获 |
|------|--------|----------|
| 1 | `misinformation detection NLP deep learning 2024-2026` | TRGCN、多模态检测趋势 |
| 2 | `disinformation campaign detection coordinated inauthentic behavior` | ACCD 因果协调检测 F1=87.3%，跨平台 CIB |
| 3 | `propaganda detection NLP information warfare AI` | GPT-4 宣传技术分类达 SOTA |
| 4 | `fake news detection knowledge graph claim verification` | GraphFC 声明图三元组验证 |
| 5 | `narrative analysis framing detection NLP` | 叙事框架检测仍小众 |
| 6 | `bot detection social media coordinated behavior` | BLOC 行为语言 |
| 7 | `LLM fact checking misinformation multi-modal` | **最丰富**，44 篇论文，多 Agent 辩论是主流 |
| 8 | `github misinformation detection disinformation tools` | DISARM 264★、DISINFOX 50★、FailSafe |

### 核心论文（精选 5 篇）

#### 1. ACCD: Adaptive Causal Coordination Detection
- **年份**: 2026 | **核心贡献**: 因果推断做协调传播检测，F1=87.3%，比最强基线提升 15.2%。
- **与 AEGI 的关联**: `coordination_detector` 当前用 `(similarity + burst) / 2`，ACCD 可替换为因果检验层，显著降低误报。

#### 2. Debate-to-Detect (D2D): Multi-Agent Debate for Misinformation Detection
- **作者**: Chen Han et al. | **年份**: 2025 | **会议**: EMNLP 2025 | **arXiv**: [2505.18596](https://arxiv.org/abs/2505.18596)
- **核心贡献**: 5 阶段结构化辩论（开场→反驳→自由辩论→总结→裁决），5 维评估（事实性、来源可靠性、推理质量、清晰度、伦理性）。
- **与 AEGI 的关联**: 作为 `claim_verification` pipeline stage，5 维评估与 assertion→judgment 证据链天然契合。

#### 3. GraphFC: Graph-based Verification Framework for Fact-Checking
- **作者**: Yani Huang et al. | **年份**: 2025 | **arXiv**: [2503.07282](https://arxiv.org/abs/2503.07282)
- **核心贡献**: 声明分解为三元组，构建声明图和证据图，图引导交叉验证，三个数据集 SOTA。
- **与 AEGI 的关联**: 三元组分解可复用 Neo4j 基础设施，比纯文本匹配更结构化可解释。

#### 4. Exposing Cross-Platform Coordinated Inauthentic Activity
- **作者**: Federico Cinus, Luca Luceri, Emilio Ferrara | **年份**: 2024
- **核心贡献**: 75% 协调网络在平台封禁后仍活跃（转移平台继续运作）。
- **与 AEGI 的关联**: `coordination_detector` 需扩展为跨平台检测，增加持续追踪能力。

#### 5. Toward Verifiable Misinformation Detection: Multi-Tool LLM Agent
- **作者**: Zikun Cui et al. | **年份**: 2025 | **arXiv**: [2508.03092](https://arxiv.org/abs/2508.03092)
- **核心贡献**: 可验证检测 Agent，三个工具（搜索、来源评估、数值验证），维护证据日志和透明推理链。
- **与 AEGI 的关联**: 架构与 Evidence-first 红线高度契合，三个工具映射到 `osint_collector`、`source_credibility`、新增数值验证。

### 开源项目（精选 3 个）

#### 1. DISARM Framework — 264 stars
- **GitHub**: [DISARMFoundation/DISARMframeworks](https://github.com/DISARMFoundation/DISARMframeworks)
- **核心功能**: MITRE ATT&CK 风格虚假信息 TTP 框架，Red/Blue Framework，STIX2 输出。
- **集成建议**: 导入 TTP 分类表到 PostgreSQL，`coordination_detector` 输出自动匹配 DISARM TTP。

#### 2. FailSafe — 6 stars（架构价值高）
- **GitHub**: [Amin7410/FailSafe-AI-Powered-Fact-Checking-System](https://github.com/Amin7410/FailSafe-AI-Powered-Fact-Checking-System)
- **核心功能**: 四层流水线（筛选→分解→检索验证→报告），结构化论证图（SAG），科学声明准确率 89%。
- **集成建议**: 借鉴 SAG 概念增强 `claim_extractor`，借鉴煽情检测补充 `source_credibility`。不建议直接依赖代码。

#### 3. DISINFOX — 50 stars
- **GitHub**: [CyberDataLab/disinfox](https://github.com/CyberDataLab/disinfox)
- **核心功能**: STIX2 标准虚假信息威胁情报平台，事件管理、行为者画像、多格式导出。
- **集成建议**: 借鉴事件数据模型和 STIX2 集成能力，不建议直接部署。

### 关键发现与建议

1. **AEGI 三个明确差距**：协调检测缺因果推断、声明验证环节缺失、来源可信度过于简单（仅 13 个高可信域名）。
2. **多 Agent 辩论是 2025 主流**：D2D、Multi-Agent Debate、FactAgent、Veracity 都采用此范式，与 AEGI pipeline 天然契合。
3. **KG 在事实核查中被低估**：GraphFC 证明三元组化+图验证优于纯文本匹配，AEGI 已有完整 Neo4j 基础设施。
4. **DISARM 是信息操作分类事实标准**：直接采用而非自建，与国际情报社区对齐。
5. **对抗攻击必须考虑**：Fact2Fiction 揭示 Agent 事实核查系统的投毒攻击威胁。

---

## 方向 6：多源情报融合

### 搜索过程记录

| 轮次 | 关键词 | 主要收获 |
|------|--------|----------|
| 1 | `multi-source intelligence fusion data fusion` | Information Fusion 期刊方向 |
| 2 | `Dempster-Shafer evidence theory applications intelligence` | 23 篇相关论文 |
| 3 | `belief function theory evidence aggregation conflicting sources` | 冲突证据管理核心论文 |
| 4 | `information fusion uncertainty quantification propagation` | 20+ 不确定性量化项目 |
| 5 | `conflicting evidence aggregation multi-source reliability` | ICEF、PCR、LNS-CR 组合规则 |
| 6 | `OSINT fusion framework open source intelligence integration` | 转向 GitHub topics |
| 7 | `Bayesian evidence fusion multi-modal intelligence` | Dirichlet-DS 融合方向 |
| 8 | `github evidence fusion Dempster-Shafer belief function tools` | dstz、pyevidence、ClusterBBA |

同时阅读了 AEGI 现有代码：`assertion_fuser.py`、`bayesian_ach.py`、`source_credibility.py`。

### 核心论文（精选 5 篇）

#### 1. Deep Evidential Fusion with Contextual Discounting
- **作者**: Ling Huang, Su Ruan, Pierre Decazes, Thierry Denoeux | **年份**: 2023/2024
- **arXiv**: [2309.05919](https://arxiv.org/abs/2309.05919)
- **核心贡献**: 上下文折扣机制——可靠性不是全局标量，而是按任务/上下文变化的向量。折扣后证据通过 Dempster 规则组合。
- **与 AEGI 的关联**: `source_credibility.py` 只输出全局标量，无法表达"某来源在军事领域可信但经济领域不可信"。contextual discounting 可直接升级。

#### 2. Trusted Multi-View Classification with Dynamic Evidential Fusion (TMC)
- **作者**: Zongbo Han et al. | **年份**: 2022/2024 | **发表**: IEEE TPAMI
- **arXiv**: [2204.11423](https://arxiv.org/abs/2204.11423)
- **核心贡献**: Dirichlet 分布参数化每个信息源的类别概率，DS 组合规则动态融合，区分 aleatoric/epistemic uncertainty。
- **与 AEGI 的关联**: 替代 assertion_fuser 硬编码 confidence（0.5/0.9），Dirichlet 是 Categorical 的共轭先验，与贝叶斯 ACH 框架一致。

#### 3. ICEF: Guaranteeing Consistency in Evidence Fusion
- **作者**: Chaoxiong Ma et al. | **年份**: 2025
- **核心贡献**: 迭代可信证据融合，plausibility-belief 散度度量冲突，解决 Zadeh 反例。
- **与 AEGI 的关联**: assertion_fuser 检测冲突后只标记 `has_conflict=True` 降 confidence 到 0.5，ICEF 提供真正的冲突解决机制。

#### 4. FNBT: Full Negation Belief Transformation for Open-World Fusion
- **作者**: Meishen He et al. | **年份**: 2025 | **arXiv**: [2508.08399](https://arxiv.org/abs/2508.08399)
- **核心贡献**: 异构辨识框架下的证据融合，新类别/假设可动态加入。
- **与 AEGI 的关联**: 多源情报天然异构，不同来源用不同分类体系描述同一事件，FNBT 的框架统一能力至关重要。

#### 5. Uncertainty-Aware Multimodal Fusion through Dirichlet Parameterization
- **作者**: Rémi Grzeczkowicz et al. | **年份**: 2026 | **arXiv**: [2502.06643](https://arxiv.org/abs/2502.06643)
- **核心贡献**: 模型无关、任务无关的 DS+Dirichlet 轻量级融合机制，即插即用。
- **与 AEGI 的关联**: 可融合不同 pipeline stage 输出（claim extraction、hypothesis engine、OSINT collector），与 TMC 一脉相承。

### 开源项目（精选 3 个）

#### 1. dstz — 8 stars (MIT)
- **GitHub**: [ztxtech/dstz](https://github.com/ztxtech/dstz)
- **核心功能**: DS 理论完整实现——mass function、belief、plausibility、Dempster 组合规则、Pignistic 变换。
- **集成建议**: 作为 assertion_fuser 数学后端，SourceClaim confidence+credibility→mass function→组合→Pignistic 输出 confidence。

#### 2. pyevidence — 4 stars
- **GitHub**: [emiruz/pyevidence](https://github.com/emiruz/pyevidence)
- **核心功能**: 高效 bit vector 编码，支持 Yager 和 Dubois-Prade 两种组合规则。
- **集成建议**: 与 dstz 互补，适合批量 OSINT 融合场景。

#### 3. ClusterBBA — 0 stars（有正式论文）
- **GitHub**: [Ma-27/ClusterBBA](https://github.com/Ma-27/ClusterBBA) | **发表**: Mathematics 2025
- **核心功能**: 四阶段融合：证据聚类→簇间散度→动态分配→两阶段加权融合。
- **集成建议**: 最适合"多源冲突解决"——大量冲突 claims 先聚类再融合，簇间散度 D_CC 替代布尔 has_conflict。

### 关键发现与建议

1. **核心短板是"检测冲突但不解决冲突"**：assertion_fuser 检测 4 类冲突后只做二值化降级（0.9→0.5），丢失冲突严重度和来源差异信息。
2. **DS 理论是贝叶斯 ACH 天然互补**：DS 层处理 SourceClaim→Assertion 融合，Bayesian 层处理 Assertion→Judgment 更新，正好对应证据链两个阶段。
3. **contextual discounting 是 source_credibility 升级路径**：从全局标量→按领域向量，扩展 `CredibilityScore` 增加 `domain_scores` 字段。

---

## 方向 7：态势感知与趋势检测

### 搜索过程记录

| 轮次 | 关键词 | 主要收获 |
|------|--------|----------|
| 1 | `situation awareness AI NLP automated` | Endsley 三层模型（感知→理解→预测） |
| 2 | `trend detection event stream change point detection` | ruptures、BOCPD 两个核心方法族 |
| 3 | `anomaly detection event data security geopolitical` | Alibi Detect、Merlion 框架 |
| 4 | `emerging topic detection real-time news stream` | BERTopic dynamic topic modeling + online partial_fit |
| 5 | `crisis detection social media early warning indicator` | CUSUM/EWMA 统计过程控制 |
| 6 | `change point detection time series online algorithms` | Adams & MacKay 2007 BOCPD |
| 7 | `situation awareness visualization automated dashboard` | Matrix Profile 统一框架 |
| 8 | `github trend detection anomaly detection event stream` | River 5.7k★、STUMPY 4.1k★、BERTopic 7.4k★ |

补充：阅读 AEGI 现有代码 `gdelt_monitor.py`、`event_bus.py`、`push_engine.py`、`gdelt_scheduler.py`、`settings.py`。

### 核心论文（精选 5 篇）

#### 1. Bayesian Online Changepoint Detection (BOCPD)
- **作者**: Ryan Prescott Adams, David J.C. MacKay | **年份**: 2007
- **链接**: [0710.3742](https://arxiv.org/abs/0710.3742)
- **核心贡献**: 在线贝叶斯变点检测，维护"运行长度"概率分布，每当新数据到达时更新变点后验概率。模块化设计，可灵活替换先验和似然模型。
- **与 AEGI 的关联**: 替换 `gdelt_anomaly_goldstein_threshold = -7.0` 硬阈值为概率化变点检测。与 EventBus 集成 emit `trend.changepoint_detected` 事件。

#### 2. Selective Review of Offline Change Point Detection Methods
- **作者**: Charles Truong, Laurent Oudre, Nicolas Vayatis | **年份**: 2020 | **发表**: Signal Processing
- **核心贡献**: 系统综述离线变点检测，PELT（Pruned Exact Linear Time）在精确性和效率间最佳平衡。统一代价函数框架（11 种）。
- **与 AEGI 的关联**: 在线用 BOCPD 实时检测，定期用 PELT 离线确认和修正。ruptures 库直接提供实现。

#### 3. BERTopic: Neural Topic Modeling with Class-based TF-IDF
- **作者**: Maarten Grootendorst | **年份**: 2022 | **链接**: [2203.05794](https://arxiv.org/abs/2203.05794)
- **核心贡献**: Transformer embedding→UMAP 降维→HDBSCAN 聚类→c-TF-IDF 主题表示。支持动态主题建模和在线增量学习（`partial_fit`）。
- **与 AEGI 的关联**: GDELT 新文章→embedding（复用 localhost:8001）→BERTopic 增量更新→检测新主题/话题激增→emit `topic.emerging` 事件。

#### 4. An Evaluation of Change Point Detection Algorithms
- **作者**: Gerrit J.J. van den Burg, Christopher K.I. Williams | **年份**: 2020
- **链接**: [2003.06222](https://arxiv.org/abs/2003.06222)
- **核心贡献**: 首个标准化变点检测评估基准，37 条真实时间序列，14 种算法对比。BOCPD 在线最优，PELT 离线最优。
- **与 AEGI 的关联**: 算法选型实证依据，支持"双轨策略"。

#### 5. Matrix Profile I: All Pairs Similarity Joins for Time Series
- **作者**: Chin-Chia Michael Yeh et al. | **年份**: 2016 | **发表**: IEEE ICDM 2016
- **核心贡献**: 统一时序模式发现（motif）、异常检测（discord）、shapelet 发现。精确、无参数、线性空间、支持增量维护。
- **与 AEGI 的关联**: GDELT tone/频率时间序列→STUMPY 计算 Matrix Profile→discord 检测态势突变、motif 发现周期模式、语义分割切分态势阶段。

### 开源项目（精选 3 个）

#### 1. River — 5,700 stars (BSD-3)
- **GitHub**: [online-ml/river](https://github.com/online-ml/river)
- **核心功能**: 在线/流式 ML 库，drift detection（ADWIN、DDM、Page-Hinkley）、anomaly detection、在线统计。
- **集成建议**: `GDELTScheduler` poll 后将 tone/事件数喂入 ADWIN 检测器，检测到漂移 emit `trend.drift_detected`。毫秒级快速检测，与 BOCPD 配合。

#### 2. BERTopic — 7,400 stars (MIT)
- **GitHub**: [MaartenGr/BERTopic](https://github.com/MaartenGr/BERTopic)
- **核心功能**: 神经主题建模，dynamic topic modeling，online partial_fit，模型合并，丰富可视化。
- **集成建议**: 创建 `TopicTracker` 服务，监听 `gdelt.event_detected`，每批新文章 `partial_fit`，检测新兴主题和话题激增。embedding 复用 localhost:8001。

#### 3. STUMPY — 4,100 stars (BSD-3)
- **GitHub**: [TDAmeritrade/stumpy](https://github.com/TDAmeritrade/stumpy)
- **核心功能**: Matrix Profile 实现，模式发现、异常检测、语义分割、流式分析、GPU 加速。
- **集成建议**: 创建 `TimeSeriesAnalyzer` 服务，定期计算 GDELT tone/频率的 Matrix Profile。Discord→态势突变，Motif→周期模式，语义分割→态势阶段划分。

#### 补充项目

| 项目 | Stars | 关键点 |
|------|-------|--------|
| [Merlion](https://github.com/salesforce/Merlion) | 4,500 | Salesforce 端到端时序 ML，AutoML + 异常检测 |
| [ruptures](https://github.com/deepcharles/ruptures) | 2,000 | 离线变点检测，6 种搜索 + 11 种代价函数 |
| [Alibi Detect](https://github.com/SeldonIO/alibi-detect) | 2,500 | 异常+漂移检测，KS/MMD/Chi2 统计检验 |

### 关键发现与建议

1. **硬阈值需升级为概率化检测**：`gdelt_anomaly_goldstein_threshold = -7.0` 是静态阈值，"异常"应是相对基线的偏离。
2. **"双轨检测"是共识**：在线（BOCPD/River ADWIN）实时告警 + 离线（PELT/Matrix Profile）回顾确认。AEGI 的 15 分钟轮询 + EventBus 天然支持。
3. **新兴话题检测是核心缺口**：当前只做关键词匹配，无法发现"未预期的新话题"。BERTopic partial_fit 可填补。
4. **Matrix Profile 统一多种时序分析**：一个 `TimeSeriesAnalyzer` 服务同时服务异常告警、模式报告、态势分段。

---

## 方向 8：人机协作情报分析

### 搜索过程记录

| 轮次 | 关键词 | 主要收获 |
|------|--------|----------|
| 1-8 | human-AI collaboration, analyst-in-the-loop, XAI, visual analytics, trust calibration, cognitive bias | WebSearch 无直接结果 |
| 9 | GitHub topics: intelligence-analysis | 13 个项目，3 个高度相关 |
| 10 | arXiv: human AI collaboration intelligence analysis | 7 篇论文 |
| 11 | arXiv: cognitive bias mitigation AI decision support | 4 篇论文 |
| 12 | arXiv: trust calibration human AI teaming | 1 篇核心论文 |
| 13 | arXiv: LLM knowledge graph interactive exploration | 12 篇论文 |
| 14-17 | 深度抓取核心论文 arXiv 页面 + GitHub 项目 README | 完整摘要和架构细节 |

### 核心论文（精选 5 篇）

#### 1. Who Should I Trust: AI or Myself?
- **作者**: Shuai Ma et al. | **年份**: 2023 | **arXiv**: [2301.05809](https://arxiv.org/abs/2301.05809)
- **核心贡献**: 信任校准需同时建模 AI 置信度和人类正确率。293 人实验证明双向置信度展示优于只展示 AI 置信度。
- **与 AEGI 的关联**: 在 `hypothesis_engine` 输出中增加 `analyst_correctness_likelihood` 字段，让分析师做更理性的采纳决策。

#### 2. Fostering Human Learning is Crucial for Boosting Human-AI Synergy
- **作者**: Julian Berger et al. | **年份**: 2025 | **arXiv**: [2512.13253](https://arxiv.org/abs/2512.13253)
- **核心贡献**: 74 项研究元分析。关键发现：**反馈+解释=正向协同，只有解释没有反馈=负向协同**。
- **与 AEGI 的关联**: 增加 Assertion 反馈机制（同意/不同意/需要更多证据），根据历史反馈调整 `PushEngine` 推送阈值。

#### 3. A Design Space for Intelligent Agents in Mixed-Initiative Visual Analytics
- **作者**: Tobias Stähle et al. | **年份**: 2025 | **arXiv**: [2512.23372](https://arxiv.org/abs/2512.23372)
- **核心贡献**: 90 个系统中 207 个智能代理的六维设计空间框架（感知、环境理解、行动、通信等）。
- **与 AEGI 的关联**: 指导 AEGI 从"人问 AI 答"向混合主动式演进——AI 主动发现异常、理解分析师关注点、建议下一步探索。

#### 4. The Role of Visualization in LLM-Assisted KG Systems
- **作者**: Harry Li et al. | **年份**: 2025 | **arXiv**: [2505.21512](https://arxiv.org/abs/2505.21512)
- **核心贡献**: 14 人实验发现即使 KG 专家也倾向过度信任 LLM 输出，可视化反而增强虚假信任感。
- **与 AEGI 的关联**: 重要警告——AEGI 的 KG 可视化+LLM 聊天需增加查询审计视图，显式标注置信度和证据链完整度。

#### 5. Overcoming Anchoring Bias: The Potential of AI and XAI-based Decision Support
- **作者**: Felix Haag et al. | **年份**: 2024 | **arXiv**: [2405.04972](https://arxiv.org/abs/2405.04972)
- **核心贡献**: N=390 实验证明 AI+XAI 能有效缓解锚定偏差。
- **与 AEGI 的关联**: 假设列表随机化排序避免位置锚定；检测到分析师长时间关注单一假设时主动推荐对立证据。

### 开源项目（精选 3 个）

#### 1. ArkhamMirror — 362 stars
- **GitHub**: [mantisfury/ArkhamMirror](https://github.com/mantisfury/ArkhamMirror)
- **核心功能**: 本地 AI 文档情报分析平台，ACH（含预验尸+魔鬼代言人）、矛盾检测、模式识别、10+ 种图布局。FastAPI+PostgreSQL+React。
- **集成建议**: 借鉴 ACH 预验尸/魔鬼代言人模式增强 `hypothesis_engine`；MOM/POP/MOSES/EVE 可信度框架升级 `source_credibility`；论证图布局参考。

#### 2. VisPile — 6 stars (HICSS 2026)
- **GitHub**: [AdamCoscia/VisPile](https://github.com/AdamCoscia/VisPile)
- **核心功能**: LLM+KG 文档可视分析，"文档堆叠"交互模式，专为情报分析师 sensemaking 设计。
- **集成建议**: "证据堆叠"视图让分析师手动组织 SourceClaim；借鉴 LLM 证据验证 UI 设计。

#### 3. IntellyWeave — 44 stars
- **GitHub**: [vericle/intellyweave](https://github.com/vericle/intellyweave)
- **核心功能**: 多 Agent OSINT 平台（Quartermaster+Case Officer），六阶段管道，GLiNER 零样本 NER，Mapbox 3D 地理可视化。FastAPI+LiteLLM+React。
- **集成建议**: 借鉴角色化 Agent 分工；GLiNER 作为轻量 NER 补充减少 LLM token 消耗；Mapbox 地理可视化参考。

### 关键发现与建议

1. **信任校准是核心瓶颈**：只展示 AI 置信度不够，需同时建模人类判断力；可视化可能增强虚假信任。AEGI 证据链架构是天然信任校准基础设施。
2. **反馈闭环决定协同效果**：74 项研究元分析明确结论——必须让分析师给反馈并看到效果。增加 Assertion 反馈 API。
3. **混合主动式优于问答式**：AI 应主动感知关注点、检测分析缺口、推送反面证据。
4. **认知偏差需系统性设计**：假设排序随机化、证据多样性检查、反向搜索建议、时间衰减提醒。

---

## 综合建议

### 短期可集成（1-2 周）

| # | 建议 | 来源方向 | 工作量 | 依赖 |
|---|------|----------|--------|------|
| 1 | **River ADWIN 替换硬阈值**：`GDELTScheduler` poll 后加 ADWIN 检测，替换 `gdelt_anomaly_goldstein_threshold` | 方向 7 | 1-2 天 | `pip install river` |
| 2 | **dstz DS 融合替换硬编码 confidence**：assertion_fuser 中 SourceClaim→mass function→Dempster 组合→Pignistic 输出 | 方向 6 | 1-2 天 | `pip install dstz` |
| 3 | **导入 DISARM TTP 分类表**：解析为 PostgreSQL 参考表，coordination_detector 输出匹配 TTP | 方向 5 | 2 天 | DISARM Excel 数据 |
| 4 | **Assertion 反馈 API**：新增 AssertionFeedback 模型，分析师标记 agree/disagree/need_more_evidence | 方向 8 | 3 天 | 新增 DB 模型 |
| 5 | **证据链完整度标注**：每个 Assertion 展示证据深度（到 Artifact 层的完整度百分比） | 方向 8 | 2 天 | 现有证据链架构 |
| 6 | **CausalCoT 提示改进**：改进 `_CAUSAL_PROMPT`，明确区分 LLM 因果发现角色和 DoWhy 计算角色 | 方向 3 | 1 天 | 现有 causal_reasoner |
| 7 | **扩展 source_credibility**：从纯域名规则→多信号评分（域名+内容煽情检测+发布频率异常） | 方向 5 | 3 天 | 现有 source_credibility |

### 中期可集成（1-2 月）

| # | 建议 | 来源方向 | 工作量 | 依赖 |
|---|------|----------|--------|------|
| 8 | **BOCPD 变点检测服务**：`ChangePointDetector` 对 tone/频率做在线贝叶斯变点检测，emit 事件到 EventBus | 方向 7 | 3 天 | 短期 #1 |
| 9 | **BERTopic 话题追踪**：`TopicTracker` 服务，增量学习 GDELT 文章主题，检测新兴话题和激增 | 方向 7 | 4 天 | `pip install bertopic` |
| 10 | **ICL-TKG 预测**：从 Neo4j 提取历史事件序列→格式化 prompt→LLM 预测→结果写回图谱 | 方向 4 | 5 天 | 新增 `tkg_forecaster.py` |
| 11 | **ALCM 三阶段因果流水线**：causal-learn PC 发现→LLM BFS 精炼→DoWhy 估计，统一两个因果模块 | 方向 3 | 2 周 | `pip install causal-learn` |
| 12 | **tigramite PCMCI 时序因果**：从 GDELT 时序数据发现滞后因果关系 | 方向 3 | 1 周 | `pip install tigramite`（GPL，独立服务） |
| 13 | **claim_verification pipeline stage**：多 Agent 辩论式声明验证，参考 D2D 5 阶段架构 | 方向 5 | 2 周 | 现有 pipeline_orchestrator |
| 14 | **声明三元组化 + Neo4j 存储**：claim_extractor 后增加三元组分解，为 GraphFC 式交叉验证打基础 | 方向 5 | 1 周 | 现有 Neo4j |
| 15 | **ICEF 冲突解决 + contextual discounting**：迭代信誉加权 + 按领域向量评分 | 方向 6 | 2 周 | 短期 #2 |
| 16 | **ToG 风格图谱推理升级**：chat 模块 KG 推理从 2-hop 邻居升级为迭代 beam search | 方向 4 | 2 周 | 现有 graph_analysis |
| 17 | **检索增强 LLM 预测 MVP**：ReAct 策略实现"检索→推理→预测"循环 | 方向 2 | 1 周 | 现有 LLMClient + SearXNG |
| 18 | **假设排序随机化 + 反向证据推荐**：对抗锚定偏差和确认偏差 | 方向 8 | 1 周 | 现有 hypothesis_engine |

### 长期研究方向

| # | 方向 | 来源 | 关键参考 |
|---|------|------|----------|
| 19 | **EasyTPP 事件时间预测器**：GDELT 事件流→THP/AttNHP 训练→时间预测 | 方向 2 | EasyTPP 库 |
| 20 | **STORM 多视角报告生成**：集成到 report_generator，Co-STORM 人机协作 | 方向 1 | STORM 27.9k★ |
| 21 | **专用 TKG 模型训练**：RE-GCN/HGLS 在 AEGI GDELT 数据上训练 | 方向 4 | RE-Net、HGLS |
| 22 | **Dirichlet 证据参数化**：替代硬编码 confidence，与贝叶斯 ACH 对接 | 方向 6 | TMC (IEEE TPAMI) |
| 23 | **因果知识图谱 CausalKG**：文本抽取+时序发现+专家标注三源汇聚 | 方向 3 | tigramite + causal-learn |
| 24 | **混合主动式推荐**：上下文感知+分析缺口检测+偏差预警 | 方向 8 | Stähle 六维框架 |
| 25 | **STIX2 输出层**：信息操作检测结果标准化输出，与 OpenCTI/MISP 互通 | 方向 5 | DISARM + DISINFOX |
| 26 | **预测聚合层**：多次 LLM 采样 + extremizing 聚合 + 一致性检查 + ACH 结构化聚合 | 方向 2 | Satopaa 理论 |
| 27 | **认知偏差防护层**：证据多样性检查、反向搜索建议、时间衰减提醒 | 方向 8 | Haag 2024 |

### 推荐下载的论文和项目清单

#### 核心论文（建议下载 PDF）

| 论文 | arXiv | 保存名 |
|------|-------|--------|
| Approaching Human-Level Forecasting | 2402.18563 | halawi-forecasting-2024.pdf |
| ForecastBench | 2409.19839 | forecastbench-2024.pdf |
| MArgE 论证树 | 2508.02584 | marge-argumentation-2025.pdf |
| AIA Forecaster | 2511.07678 | aia-forecaster-2025.pdf |
| MIRAI | 2407.01231 | mirai-event-forecast-2024.pdf |
| THP | 2002.09291 | thp-hawkes-2020.pdf |
| ONSEP | 2408.07840 | onsep-neural-symbolic-2024.pdf |
| Kiciman LLM Causal | 2305.00050 | kiciman-llm-causal-2023.pdf |
| ALCM | 2405.01744 | alcm-causal-discovery-2024.pdf |
| CLadder | 2312.04350 | cladder-causal-2023.pdf |
| GenTKG | 2310.07793 | gentkg-2024.pdf |
| Think-on-Graph | 2307.07697 | think-on-graph-2024.pdf |
| RoG | 2310.01061 | rog-reasoning-2024.pdf |
| ICL-TKG | 2305.10613 | icl-tkg-2023.pdf |
| D2D | 2505.18596 | d2d-debate-detect-2025.pdf |
| GraphFC | 2503.07282 | graphfc-2025.pdf |
| Contextual Discounting | 2309.05919 | contextual-discounting-2023.pdf |
| TMC | 2204.11423 | tmc-evidential-fusion-2022.pdf |
| BOCPD | 0710.3742 | bocpd-2007.pdf |
| BERTopic | 2203.05794 | bertopic-2022.pdf |
| Trust Calibration (Ma) | 2301.05809 | trust-calibration-2023.pdf |
| Human-AI Synergy (Berger) | 2512.13253 | human-ai-synergy-2025.pdf |

#### 高价值开源项目（建议克隆）

| 项目 | GitHub | Stars | 优先级 |
|------|--------|-------|--------|
| STORM | stanford-oval/storm | 27,900 | P0 |
| LightRAG | HKUDS/LightRAG | 28,300 | P1 |
| EasyTPP | ant-research/EasyTemporalPointProcess | 333 | P1 |
| BERTopic | MaartenGr/BERTopic | 7,400 | P1 |
| STUMPY | TDAmeritrade/stumpy | 4,100 | P1 |
| River | online-ml/river | 5,700 | P1 |
| tigramite | jakobrunge/tigramite | 1,600 | P1 |
| causal-learn | cmu-phil/causal-learn | 1,600 | P1 |
| RoG | RManLuo/reasoning-on-graphs | 494 | P2 |
| DISARM | DISARMFoundation/DISARMframeworks | 264 | P2 |
| ArkhamMirror | mantisfury/ArkhamMirror | 362 | P2 |
| MIRAI | yecchen/MIRAI | 90 | P2 |
| dstz | ztxtech/dstz | 8 | P2 |
