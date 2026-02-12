<!-- Author: msq -->
# 方向 5：虚假信息检测与信息战分析

> 调研日期：2026-02-12
> 调研范围：8 轮搜索，40+ 篇论文摘要，20+ 开源项目评估
> 精选：5 篇核心论文 + 3 个开源项目

---

## 搜索过程记录

### 第 1 轮：misinformation detection NLP deep learning 2024-2026
- 来源：arXiv 搜索
- 发现 5 篇论文，涵盖图卷积+Transformer 混合架构（TRGCN 2026）、视频多模态检测（Fact-R1 2025, ViMGuard 2024）、网络结构融合（CleanNews 2025）、健康领域混合模型（2024）
- 关键收获：多模态（文本+视频+音频）检测是 2025-2026 的主流趋势；图结构信息对传播模式建模至关重要

### 第 2 轮：disinformation campaign detection coordinated inauthentic behavior
- 来源：arXiv 搜索
- 发现 9 篇论文，这是与 AEGI coordination_detector 最直接相关的方向
- 核心发现：
  - ACCD（2026）：因果推断做协调检测，F1=87.3%，比最强基线提升 15.2%
  - 密度感知随机游走（2025）：图嵌入+神经网络，二分类准确率提升 12%
  - 跨平台 CIB 检测（Cinus/Luceri 2024）：75% 的协调网络在平台封禁后仍活跃
  - BLOC 语言（2022）：通用社交媒体行为建模语言，可检测机器人和协调行为

### 第 3 轮：propaganda detection NLP information warfare AI
- 来源：arXiv 搜索
- 发现 LLM 做宣传技术检测的论文（Sprenkamp 2023），GPT-4 在 SemEval-2020 Task 11 的 14 种宣传技术分类上达到 SOTA 水平
- Whataboutism 检测（Phi 2024, ACL Findings）：注意力权重做负样本挖掘，比先前方法提升 4-10%

### 第 4 轮：fake news detection knowledge graph claim verification
- 来源：arXiv 搜索 + GitHub topics
- 发现 GraphFC（2025）：基于声明图三元组的事实核查框架，三个数据集上 SOTA
- TrumorGPT（2025）：GraphRAG + 健康知识图谱做事实核查

### 第 5 轮：narrative analysis framing detection NLP computational
- 来源：arXiv 搜索
- 结果较少，仅找到 Whataboutism 检测一篇直接相关论文
- 叙事框架检测仍是相对小众的研究方向

### 第 6 轮：bot detection social media coordinated behavior network analysis
- 来源：GitHub topics + arXiv
- 发现 BLOC 行为语言是该领域的代表性工作
- GitHub 上该方向的开源工具较少且分散

### 第 7 轮：LLM fact checking misinformation multi-modal
- 来源：arXiv 搜索
- **最丰富的一轮**，发现 44 篇论文（2024-2026）
- 核心趋势：
  - 多 Agent 辩论式事实核查（D2D 2025, Multi-Agent Debate 2025）
  - 图结构事实核查（GraphFC 2025, TrumorGPT 2025）
  - 多语言/多模态基准（VeriTaS 2026, MMM-Fact 2025）
  - Agent 工具链式核查（Veracity 2025, Multi-Tool Agent 2025）
  - 对抗攻击（Fact2Fiction 2025：针对 Agent 事实核查系统的投毒攻击）

### 第 8 轮：GitHub misinformation detection disinformation open source tools
- 来源：GitHub topics (misinformation-detection, disinformation)
- 发现 40+ 个项目，精选评估：
  - DISARM Framework（264 stars）：MITRE ATT&CK 风格的虚假信息 TTP 框架
  - DISINFOX（50 stars）：基于 STIX2 的虚假信息威胁情报平台
  - MassMove/AttackVectors（402 stars）：国家级信息操作监控
  - FactAgent（10 stars）：多 Agent 事实核查系统
  - FailSafe（6 stars）：结构化论证图 + 多层事实核查

---

## 核心论文（精选 5 篇）

### 论文 1：Adaptive Causal Coordination Detection for Social Media (ACCD)

- **作者**：Weng Ding, Yi Han, Mu-Jiang-Shan Wang
- **年份**：2026
- **核心贡献**：提出自适应因果协调检测方法，将因果推断引入协调传播检测。不再仅依赖时间窗口+相似度的启发式规则，而是通过因果关系判断行为是否真正"协调"而非自然传播。F1=87.3%，比最强基线提升 15.2%。
- **与 AEGI 的关联**：AEGI 现有 `coordination_detector.py` 使用 `(similarity + burst) / 2` 的简单平均作为 confidence，无法区分自然传播和协调行为。ACCD 的因果推断方法可以直接替换 `detect_coordination()` 中的置信度计算逻辑，显著降低误报率。具体来说，可以在 `_time_burst_score` 和 `_pairwise_similarity` 之上增加因果检验层，判断相似度和时间爆发之间是否存在因果关系而非仅仅相关。
- **链接**：arXiv 2026（具体 ID 待确认，搜索结果未提供完整 arXiv ID）

### 论文 2：Debate-to-Detect (D2D) — Multi-Agent Debate for Misinformation Detection

- **作者**：Chen Han, Wenzhen Zheng, Xijin Tang
- **年份**：2025
- **会议**：EMNLP 2025
- **核心贡献**：将虚假信息检测重新定义为结构化对抗辩论。多个 Agent 分别扮演不同角色，经过 5 个阶段（开场陈述→反驳→自由辩论→总结→裁决）进行结构化辩论。评估维度从二分类扩展到 5 维：事实性、来源可靠性、推理质量、清晰度、伦理性。GPT-4o 上显著优于基线方法。
- **与 AEGI 的关联**：AEGI 的 `claim_extractor` 提取声明后，目前缺少系统性的声明验证环节。D2D 的多 Agent 辩论架构可以作为 claim verification pipeline stage 集成到 `pipeline_orchestrator` 中。5 维评估框架与 AEGI 的 `assertion → judgment` 证据链天然契合——每个维度的辩论结论可以生成对应的 Assertion，最终汇聚为 Judgment。
- **链接**：arXiv:2505.18596

### 论文 3：GraphFC — A Graph-based Verification Framework for Fact-Checking

- **作者**：Yani Huang, Richong Zhang, Zhijie Nie, Junfan Chen, Xuefeng Zhang
- **年份**：2025
- **核心贡献**：提出基于声明图（claim graph）的事实核查框架。将声明分解为三元组（主语-谓语-宾语），构建声明图和证据图，通过图引导的规划确定验证顺序，再逐三元组在两个图之间交叉验证。解决了现有方法"分解不充分"和"指代歧义"两大问题，三个数据集上达到 SOTA。
- **与 AEGI 的关联**：AEGI 已有 Neo4j 知识图谱（`neo4j_store` 6 个方法）和图分析服务（`graph_analysis`）。GraphFC 的三元组分解方法可以直接复用 AEGI 的 KG 基础设施：将 `claim_extractor` 提取的 SourceClaim 分解为三元组存入 Neo4j，然后利用现有的子图查询和路径发现能力做交叉验证。这比纯文本匹配的验证方式更结构化、更可解释。
- **链接**：arXiv:2503.07282

### 论文 4：Exposing Cross-Platform Coordinated Inauthentic Activity

- **作者**：Federico Cinus, Marco Minici, Luca Luceri, Emilio Ferrara
- **年份**：2024
- **核心贡献**：首次系统性研究跨平台协调不真实行为。发现俄罗斯关联媒体在 Telegram 和 X（Twitter）上被系统性推广，且超过 75% 的协调网络在平台封禁后仍然活跃（转移到其他平台继续运作）。提出跨平台协调检测方法，通过跨平台行为关联识别同一操作的不同平台分身。
- **与 AEGI 的关联**：AEGI 的 OSINT 收集器（`osint_collector.py`）已支持多源采集，但 `coordination_detector` 目前只在单一数据集内检测协调行为。该论文的跨平台关联方法可以扩展 `detect_coordination()` 的输入，增加 `platform` 字段到 `SourceClaimV1`，在聚类时考虑跨平台的时间-内容-行为模式匹配。75% 的封禁后存活率也说明 AEGI 需要持续追踪能力，而非一次性检测。
- **链接**：arXiv 2024（Cinus et al.）

### 论文 5：Toward Verifiable Misinformation Detection — A Multi-Tool LLM Agent Framework

- **作者**：Zikun Cui, Tianyi Huang, Chia-En Chiang, Cuiqianhe Du
- **年份**：2025
- **核心贡献**：提出可验证的虚假信息检测 Agent 架构，配备三个核心工具：网络搜索、来源可信度评估、数值声明验证。Agent 在检测过程中维护证据日志并生成透明推理链。在 FakeNewsNet 数据集上，检测准确率、推理透明度、对内容改写的鲁棒性三方面均优于基线。关键创新在于"可验证"——每个判断都有可追溯的证据链。
- **与 AEGI 的关联**：这篇论文的架构与 AEGI 的设计理念高度契合——Evidence-first 红线要求"断言/判断必须绑定 SourceClaim，再回溯证据链到 Artifact 快照"。该 Agent 的三个工具可以直接映射到 AEGI 现有组件：网络搜索 → `osint_collector` + `aegi-mcp-gateway`；来源可信度 → `source_credibility.py`（需从规则升级为 Agent 工具）；数值验证 → 新增工具。证据日志机制与 AEGI 的 `ActionV1` + `ToolTraceV1` 审计链天然对齐。
- **链接**：arXiv:2508.03092

---

## 开源项目（精选 3 个）

### 项目 1：DISARM Framework

- **GitHub**：https://github.com/DISARMFoundation/DISARMframeworks
- **Stars**：264 | Forks：46 | License：CC-BY-SA-4.0
- **核心功能**：MITRE ATT&CK 风格的虚假信息战术/技术/程序（TTP）框架。将信息操作分解为阶段（Phase）→ 战术（Tactic）→ 技术（Technique）→ 任务（Task），并提供对应的反制措施（Counter）。包含 Red Framework（攻击方 TTP）和 Blue Framework（防御方对策）。数据以 STIX2 格式输出，可与 TAXII 协议集成。
- **集成可行性**：高。DISARM 的 TTP 分类体系可以作为 AEGI 信息操作检测的"知识库"。主数据在 Excel + CSV 中，可直接导入 PostgreSQL 作为参考表。
- **集成建议**：
  1. 将 DISARM 的 TTP 分类导入 AEGI 数据库，作为 `information_operation_technique` 参考表
  2. 在 `coordination_detector` 检测到协调行为后，自动匹配 DISARM TTP 分类，输出"该协调行为疑似使用了哪些信息操作技术"
  3. 在 `narrative_builder` 构建叙事时，标注叙事是否匹配已知的信息操作模式（如 astroturfing、sockpuppet 等）
  4. STIX2 输出格式可与 AEGI 的事件总线（`event_bus`）集成，将检测到的信息操作事件以标准化格式推送

### 项目 2：FailSafe — AI-Powered Fact-Checking System

- **GitHub**：https://github.com/Amin7410/FailSafe-AI-Powered-Fact-Checking-System
- **Stars**：6 | License：开源
- **核心功能**：四层流水线式事实核查系统。Layer 0 筛选（来源可信度+煽情检测）→ Layer 1 分解（结构化论证图 SAG，将复杂文本分解为原子可验证声明）→ Layer 2-3 检索验证（ChromaDB 向量缓存 + Serper 实时搜索，多源共识判定）→ Layer 4 综合报告。支持 Gemini/GPT-4/Claude 多 LLM 后端。科学声明准确率 89%。
- **集成可行性**：中高。虽然 star 数低，但架构设计与 AEGI 的 pipeline 模式高度一致。
- **集成建议**：
  1. FailSafe 的结构化论证图（SAG）概念可以增强 AEGI 的 `claim_extractor`——当前 claim_extractor 只提取扁平的声明列表，SAG 可以捕获声明之间的论证关系（支持/反驳/前提）
  2. Layer 0 的煽情检测（sensationalist pattern detection）可以作为 `source_credibility.py` 的补充——当前只有域名规则，缺少内容层面的可信度信号
  3. 多源共识判定逻辑（"仅当高可信来源达成共识时才标记为 Supported"）可以集成到 AEGI 的 assertion → judgment 流程中
  4. 不建议直接依赖该项目代码（star 数低、维护不确定），而是借鉴其架构思路在 AEGI 内部实现

### 项目 3：DISINFOX — Disinformation Threat Intelligence Platform

- **GitHub**：https://github.com/CyberDataLab/disinfox
- **Stars**：50 | License：开源
- **核心功能**：将网络安全威胁情报方法论应用于虚假信息事件。使用 STIX2 标准结构化虚假信息数据，支持事件管理、威胁行为者画像、STIX2 图可视化、多格式导出（PDF/Word/JSON）。实现了 DISARM 框架，可与 OpenCTI 等 CTI 平台集成。
- **集成可行性**：中。DISINFOX 本身是一个独立平台，直接集成成本较高，但其数据模型和 STIX2 输出格式有参考价值。
- **集成建议**：
  1. 借鉴 DISINFOX 的事件数据模型（incident → campaign → threat_actor → TTP），在 AEGI 中建立类似的信息操作事件模型
  2. STIX2 格式作为 AEGI 信息操作检测结果的标准输出格式，便于与外部 CTI 平台（OpenCTI、MISP）交换数据
  3. 威胁行为者画像功能可以扩展 AEGI 的 `source_credibility`——从"域名信誉"升级为"行为者画像"，追踪特定信息操作行为者的历史行为模式
  4. 不建议直接部署 DISINFOX，而是将其数据模型和 STIX2 集成能力作为 AEGI 的输出层

---

## 关键发现与建议

### 发现 1：AEGI 现有组件与学术前沿的差距分析

AEGI 的 `coordination_detector` 和 `narrative_builder` 在架构上是合理的，但与 2024-2026 的学术前沿相比存在三个明确差距：

1. **协调检测缺乏因果推断**：当前 `detect_coordination()` 用 `(similarity + burst) / 2` 做置信度，本质是相关性检测而非因果性检测。ACCD（2026）证明因果推断可以将 F1 提升 15.2%。自然传播（如热点新闻被多家媒体同时报道）会产生大量误报，因果检验可以有效过滤。
2. **声明验证环节缺失**：`claim_extractor` 提取声明后，直接进入 `narrative_builder` 聚类，中间没有声明验证步骤。D2D 和 Multi-Tool Agent 论文都表明，多 Agent 辩论式验证或工具链式验证可以显著提升声明可信度评估的准确性。
3. **来源可信度过于简单**：`source_credibility.py` 仅有 13 个高可信域名 + 3 个低可信域名 + TLD 规则，无法应对真实世界的复杂性。学术界已经发展出多维度来源评估（内容分析、历史行为、网络结构、交叉引用）。

### 发现 2：多 Agent 辩论是 2025 年事实核查的主流范式

从搜索结果看，2025 年事实核查领域最显著的趋势是"多 Agent 辩论"：
- D2D（EMNLP 2025）：5 阶段结构化辩论
- Multi-Agent Debate（2025）：协议分数预测 + 多 Agent 辩论
- FactAgent（2025）：4 种推理策略（CoT/Direct/Folk/SASE）的多 Agent 协作
- Veracity（2025）：LLM + Web 检索 Agent 协作

这与 AEGI 的 pipeline 架构天然契合——可以在 `pipeline_orchestrator` 中增加一个 `claim_verification` stage，内部实现多 Agent 辩论逻辑。

### 发现 3：知识图谱在事实核查中的价值被低估

GraphFC 和 TrumorGPT 证明，将声明分解为三元组并在知识图谱上做结构化验证，比纯文本匹配更准确、更可解释。AEGI 已有完整的 Neo4j 基础设施（6 个查询方法 + 图分析服务），这是一个被低估的优势。将 `claim_extractor` 的输出三元组化并存入 Neo4j，可以同时服务于：
- 事实核查（GraphFC 方法）
- 叙事追踪（现有 `narrative_builder`）
- 协调检测（跨声明的图结构模式）
- 知识图谱推理（现有 `graph_analysis`）

### 发现 4：DISARM 框架是信息操作分类的事实标准

DISARM（264 stars，MITRE ATT&CK 风格）已成为虚假信息领域的 TTP 分类标准，被 DISINFOX、OpenCTI 等平台采用。AEGI 如果要做信息操作检测，应该直接采用 DISARM 分类体系而非自建，这样可以：
- 与国际情报社区的分类标准对齐
- 利用 STIX2 格式与外部 CTI 平台互通
- 复用 DISARM 社区积累的真实案例数据

### 发现 5：对抗攻击是必须考虑的威胁

Fact2Fiction（2025）论文揭示了一个重要威胁：针对 Agent 事实核查系统的投毒攻击，攻击成功率比基线高 8.9-21.2%。RAGuard（2025）发现所有 RAG 系统在面对误导性检索结果时表现甚至不如零样本基线。这意味着 AEGI 在集成任何自动化事实核查能力时，必须同时考虑对抗鲁棒性——不能盲目信任检索结果或 LLM 判断。

---

## 集成优先级建议

### 短期（1-2 周）
1. **导入 DISARM TTP 分类表**：下载 DISARM_FRAMEWORKS_MASTER.xlsx，解析为 PostgreSQL 参考表，在 `coordination_detector` 输出中增加 TTP 匹配字段
2. **扩展 `source_credibility.py`**：从纯域名规则扩展为多信号评分（域名 + 内容煽情检测 + 发布频率异常），参考 FailSafe Layer 0

### 中期（1-2 月）
3. **声明三元组化 + Neo4j 存储**：在 `claim_extractor` 后增加三元组分解步骤，将 (主语, 谓语, 宾语) 存入 Neo4j，为 GraphFC 式交叉验证打基础
4. **claim_verification pipeline stage**：实现多 Agent 辩论式声明验证，作为 `pipeline_orchestrator` 的新 stage，参考 D2D 的 5 阶段架构
5. **跨平台协调检测**：扩展 `coordination_detector` 支持跨数据源的协调行为关联

### 长期（3+ 月）
6. **因果协调检测**：参考 ACCD 论文，在 `coordination_detector` 中引入因果推断层，替换简单的相关性置信度计算
7. **STIX2 输出层**：将信息操作检测结果以 STIX2 格式输出，支持与 OpenCTI/MISP 等外部 CTI 平台集成
8. **对抗鲁棒性测试**：参考 Fact2Fiction 和 RAGuard，建立事实核查系统的对抗测试基准
