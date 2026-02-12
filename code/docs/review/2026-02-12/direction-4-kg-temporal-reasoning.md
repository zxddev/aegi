<!-- Author: msq -->

# 方向 4：知识图谱推理与时序推理

> 日期：2026-02-12
> 调研范围：时序知识图谱（TKG）模型、KG+LLM 推理方法、动态图推理、政治/安全领域 KG 应用
> 搜索轮次：8 轮 WebSearch + 15+ 次 WebFetch 深度抓取

---

## 搜索过程记录

### 第 1 轮：temporal knowledge graph reasoning completion 2024 2025 2026
- 目标：获取 TKG 补全/推理领域最新进展
- 结果：WebSearch 未返回直接结果，转向 WebFetch 抓取已知资源

### 第 2 轮：dynamic knowledge graph link prediction event forecasting
- 目标：动态图上的链接预测与事件预测
- 结果：同上，转向直接抓取

### 第 3 轮：knowledge graph LLM reasoning beyond GraphRAG
- 目标：KG+LLM 结合方法（GraphRAG 之外）
- 结果：通过后续 WebFetch 获取了 LightRAG、Think-on-Graph、RoG、KG-GPT 等项目/论文

### 第 4 轮：graph neural network event prediction geopolitical
- 目标：GNN 在地缘政治事件预测中的应用
- 结果：转向直接抓取 ICEWS/GDELT 相关项目

### 第 5 轮：temporal knowledge graph embedding TKG model
- 目标：TKG 嵌入模型（TTransE、TA-DistMult、RE-NET 等）
- 结果：通过 GitHub topics 页面获取了大量 TKG 项目列表

### 第 6 轮：knowledge graph question answering intelligence analysis
- 目标：KGQA 在情报分析中的应用
- 结果：获取了 RoG (ICLR 2024) 等 KGQA 框架

### 第 7 轮：knowledge graph reasoning political security domain
- 目标：政治/安全领域的 KG 推理应用
- 结果：未找到专门针对政治安全领域的 KG 论文，该领域多用通用 TKG 方法 + ICEWS/GDELT 数据集

### 第 8 轮：github temporal knowledge graph open source
- 目标：开源 TKG 项目
- 结果：通过 GitHub topics 获取了完整的 TKG 项目列表

### 补充抓取
- 抓取了 stmrdus/tkger 仓库：获取 2024-2025 年 TKG 论文完整列表（100+ 篇），含数据集统计
- 抓取了 Cantoria/dynamic-graph-papers：获取动态图论文列表，含 LLM+TKG 最新方向
- 抓取了 LIANGKE23/Awesome-Knowledge-Graph-Reasoning（1.4k star）：KG 推理综合资源
- 深度抓取了 RE-Net、RE-GCN、HGLS、TFLEX、EvoKG、xERTE、ChronoKGE、TimeLlama 等项目
- 深度抓取了 LightRAG、Think-on-Graph、RoG、KG-GPT 等 KG+LLM 论文/项目
- 抓取了 GenTKG、ICL-TKG 等 LLM 做 TKG 预测的最新论文
- 抓取了 PyKEEN 项目详情，评估其时序扩展可行性

---

## 核心论文（精选 5 篇）

### 论文 1：GenTKG — 用 LLM 做时序知识图谱预测

- **标题**：GenTKG: Generative Forecasting on Temporal Knowledge Graph with Large Language Models
- **作者**：Ruotong Liao, Xu Jia, Yangzhe Li, Yunpu Ma, Volker Tresp
- **年份**：2024
- **会议**：Findings of NAACL 2024 + Spotlight on TGL@NeurIPS 2023
- **链接**：https://arxiv.org/abs/2310.07793
- **核心贡献**：
  提出检索增强生成框架，将 TKG 预测转化为生成式任务。核心创新是"时序逻辑规则检索策略"——从历史事件中检索相关时序模式作为 few-shot 示例，配合参数高效微调（LoRA），仅需 16 个样本即可达到强性能。支持跨域零样本泛化，在未见过的数据集上无需重训练。
- **与 AEGI 的关联**：
  AEGI 已有 GDELT 数据摄入和 Neo4j 图谱，GenTKG 的方法可直接应用于 AEGI 的事件预测场景。具体来说：(1) 时序逻辑规则检索可复用 AEGI 现有的 Neo4j 子图查询能力；(2) 生成式预测天然支持自然语言输出，与 AEGI 的 LLM pipeline 无缝衔接；(3) few-shot 特性意味着不需要大量标注数据，适合 AEGI 的冷启动场景。建议在 `services/` 下新增 `tkg_forecaster.py`，封装 GenTKG 的检索-生成流程。

### 论文 2：Think-on-Graph — LLM 在知识图谱上的深度推理

- **标题**：Think-on-Graph: Deep and Responsible Reasoning of Large Language Model on Knowledge Graph
- **作者**：Jiashuo Sun, Chengjin Xu, Lumingyuan Tang, Saizhuo Wang 等
- **年份**：2024
- **会议**：ICLR 2024
- **链接**：https://arxiv.org/abs/2307.07697
- **核心贡献**：
  提出 LLM⊗KG 范式，LLM 作为 agent 在 KG 上执行迭代 beam search 探索推理路径。无需训练，即插即用，兼容任意 LLM 和 KG。关键发现：小模型 + ToG 可在部分场景超越 GPT-4 单独推理。提供知识可追溯性和可纠正性——推理路径可被专家审查和修正。
- **与 AEGI 的关联**：
  ToG 与 AEGI 的架构高度契合：(1) AEGI 已有 Neo4j 图谱 + LLM 后端，ToG 的 beam search 可直接在 Neo4j 上执行；(2) 推理路径的可追溯性完美匹配 AEGI 的证据链红线（Judgment → Assertion → SourceClaim）；(3) 无需训练的特性意味着可快速集成。建议在 `chat/` 模块的 KG 推理路径中引入 ToG 的迭代探索策略，替代当前的 2-hop 邻居 + 路径发现方案。

### 论文 3：Reasoning on Graphs (RoG) — 忠实可解释的 LLM+KG 推理

- **标题**：Reasoning on Graphs: Faithful and Interpretable Large Language Model Reasoning
- **作者**：Linhao Luo, Yuan-Fang Li, Gholamreza Haffari, Shirui Pan
- **年份**：2024
- **会议**：ICLR 2024
- **链接**：https://arxiv.org/abs/2310.01061
- **核心贡献**：
  提出 Planning-Retrieval-Reasoning 三阶段框架：(1) Planning 阶段由 LLM 生成基于 KG 关系的推理路径规划；(2) Retrieval 阶段从 KG 中提取有效推理路径；(3) Reasoning 阶段 LLM 基于检索到的路径生成答案。训练时将 KG 结构知识蒸馏到 LLM 中，推理时兼容任意 LLM（GPT-3.5、Llama2 等）。在 KGQA 基准上达到 SOTA。
- **与 AEGI 的关联**：
  RoG 的三阶段框架可直接映射到 AEGI 的 pipeline 架构：Planning 对应 query_planner，Retrieval 对应 Neo4j 子图查询，Reasoning 对应 LLM 推理。具体集成点：(1) 在 `services/graph_analysis.py` 中增加关系路径规划能力；(2) 利用 RoG 的 KG 蒸馏方法提升 AEGI 的 LLM 对图谱结构的理解；(3) RoG 的可解释推理路径可直接作为 AEGI 报告中的证据链展示。

### 论文 4：TKG Forecasting Without Knowledge Using In-Context Learning

- **标题**：Temporal Knowledge Graph Forecasting Without Knowledge Using In-Context Learning
- **作者**：Dong-Ho Lee, Kian Ahrabian, Woojeong Jin, Fred Morstatter, Jay Pujara
- **年份**：2023
- **会议**：EMNLP 2023 (Main Conference)
- **链接**：https://arxiv.org/abs/2305.10613
- **核心贡献**：
  证明 LLM 仅通过 in-context learning（无需微调或专用模块）即可达到与 SOTA TKG 模型相当的预测性能。关键发现：(1) 语义信息不是必需的——用数字索引替代实体/关系名称仅影响 ±0.4% Hit@1；(2) LLM 能捕获超越简单频率/时近性的不规则模式；(3) 历史事实转化为 prompt 后，通过 token 概率生成排序预测。
- **与 AEGI 的关联**：
  该论文为 AEGI 提供了一条低成本的 TKG 预测路径：无需训练专用模型，直接利用现有 LLM 后端。具体方案：(1) 从 Neo4j 中提取目标实体的历史事件序列；(2) 格式化为 prompt 送入 AEGI 的 LLM pipeline；(3) 通过 token 概率排序预测未来事件。这与 AEGI 现有的 `invoke_structured()` 调用模式完全兼容，实现成本极低。

### 论文 5：TKGC 综述 — 时序知识图谱补全的分类体系

- **标题**：A Survey on Temporal Knowledge Graph Completion: Taxonomy, Progress, and Prospects
- **作者**：Jiapu Wang, Boyue Wang, Meikang Qiu, Shirui Pan 等
- **年份**：2023
- **链接**：https://arxiv.org/abs/2308.02457
- **核心贡献**：
  对 TKGC 领域的全面分类综述，将方法分为两大类：(1) 插值（interpolation）——利用已有信息预测缺失元素，包括基于翻译、分解、神经网络的方法；(2) 外推（extrapolation）——预测未来事件，包括基于 RNN、GNN、注意力机制的方法。覆盖了损失函数、数据集（ICEWS14/18、GDELT、YAGO15k 等）、评估协议的完整体系。
- **与 AEGI 的关联**：
  作为技术选型的参考指南。AEGI 的需求同时涉及插值（补全图谱中的缺失关系）和外推（预测未来事件）。综述中的分类体系帮助明确：(1) 对于图谱补全，AEGI 可在 PyKEEN 基础上增加时序维度（如 TComplEx、TNTComplEx）；(2) 对于事件预测，RE-GCN 和 RE-Net 类方法更适合 AEGI 的 GDELT 数据流。

---

## 开源项目（精选 3 个）

### 项目 1：RE-Net — 时序知识图谱事件预测

- **名称**：RE-Net (Recurrent Event Network)
- **GitHub**：https://github.com/INK-USC/RE-Net
- **Star 数**：457
- **核心功能**：
  将事件建模为以历史序列为条件的概率分布，结合循环事件编码器和邻域聚合器预测未来事实。支持 ICEWS14/18、GDELT、WIKI、YAGO 五个数据集。实现了多步推理（预测多个未来时间步），包含 TA-TransE、TA-DistMult、TTransE 等基线实现。
- **集成可行性**：高
  - 技术栈：PyTorch，与 AEGI 的 Python 生态兼容
  - 数据格式：支持 GDELT，AEGI 已有 GDELT 数据摄入管道
  - 模型架构：RGCN 聚合器可复用 AEGI 现有的图结构
  - 局限：仓库维护不活跃（研究代码），需要工程化封装
- **集成建议**：
  1. 将 RE-Net 的核心模型代码提取为独立模块，放入 `services/tkg_predictor.py`
  2. 编写 GDELT → RE-Net 输入格式的转换器，复用 `services/gdelt_monitor.py` 的数据
  3. 预测结果写入 Neo4j 作为"预测边"（带置信度和时间戳），与现有图谱融合
  4. 在 pipeline 中增加 `tkg_predict` 阶段，在 GDELT 数据摄入后自动触发预测

### 项目 2：Reasoning on Graphs (RoG) — LLM+KG 忠实推理

- **名称**：RoG (Reasoning on Graphs)
- **GitHub**：https://github.com/RManLuo/reasoning-on-graphs
- **Star 数**：494
- **核心功能**：
  ICLR 2024 论文的官方实现。Planning-Retrieval-Reasoning 三阶段 LLM+KG 推理框架。支持 GPT-3.5、Llama2、Alpaca、Flan-T5 等多种 LLM。提供预训练权重（HuggingFace）。推理仅需 12GB GPU 显存。支持 WebQSP 和 CWQ 两个 KGQA 数据集。
- **集成可行性**：中高
  - 优势：框架设计与 AEGI 的 pipeline 架构天然匹配
  - 优势：即插即用，兼容 AEGI 现有的 LLM 后端
  - 挑战：需要将 RoG 的 KG 接口适配到 Neo4j（原实现基于 Freebase）
  - 挑战：关系路径规划需要预定义关系类型，AEGI 的图谱关系类型需要梳理
- **集成建议**：
  1. 提取 RoG 的 Planning 模块逻辑，集成到 `services/graph_analysis.py` 的路径发现功能中
  2. 编写 Neo4j → RoG 关系路径格式的适配层
  3. 在 `chat/` 模块中，当检测到需要多跳推理的问题时，切换到 RoG 的 Planning-Retrieval-Reasoning 流程
  4. 利用 RoG 的推理路径作为 AEGI 报告中的证据链可视化数据

### 项目 3：LightRAG — 图增强的检索增强生成

- **名称**：LightRAG
- **GitHub**：https://github.com/HKUDS/LightRAG
- **Star 数**：28,300
- **核心功能**：
  将知识图谱结构融入 RAG 的索引和检索过程。双层检索机制：低层（实体聚焦）+ 高层（关系聚焦）。支持 PostgreSQL、MongoDB、Neo4j 等多种存储后端。增量更新算法支持新数据实时融入。支持文档删除后自动重建图谱。引用溯源功能。
- **集成可行性**：高
  - 优势：直接支持 Neo4j 和 PostgreSQL，与 AEGI 基础设施完全匹配
  - 优势：社区活跃（28k+ star），维护有保障
  - 优势：增量更新特性适合 AEGI 的实时数据流场景
  - 挑战：需要 32B+ 参数模型 + 64KB 上下文窗口做实体关系抽取
  - 挑战：与 AEGI 现有的 Qdrant 向量检索需要协调
- **集成建议**：
  1. 作为 AEGI 现有 GraphRAG 能力的升级方案，替代或补充当前的 chat KG 推理
  2. 利用 LightRAG 的双层检索增强 `services/query_planner.py` 的图谱查询能力
  3. 将 LightRAG 的实体关系抽取流程集成到 `services/claim_extractor.py`，自动构建结构化知识
  4. 增量更新能力对接 GDELT/OSINT 数据流，实现图谱的实时演化

---

## 补充值得关注的项目和论文

| 名称 | 类型 | Star/会议 | 核心价值 | 链接 |
|------|------|-----------|----------|------|
| RE-GCN | 项目 | 160 star | SIGIR 2021，关系演化 GCN，支持 ICEWS/GDELT | https://github.com/Lee-zix/RE-GCN |
| TFLEX | 项目 | 38 star | NeurIPS 2023，时序复杂查询嵌入，支持 40+ 查询模式 | https://github.com/LinXueyuanStdio/TFLEX |
| TimeLlama | 项目 | 43 star | 指令微调 Llama2 做时序推理，F1 88.4% vs ChatGPT 43.5% | https://github.com/chenhan97/TimeLlama |
| xERTE | 项目 | 51 star | ICLR 2021，可解释子图推理，支持 ICEWS/YAGO | https://github.com/TemporalKGTeam/xERTE |
| HGLS | 项目 | 37 star | WWW 2023，长短期双表示学习，支持 ICEWS/GDELT | https://github.com/CRIPAC-DIG/HGLS |
| EvoKG | 项目 | 57 star | WSDM 2022，联合建模事件时间和网络结构 | https://github.com/NamyongPark/EvoKG |
| KG-GPT | 论文 | EMNLP 2023 | 三步框架（分割-检索-推理）做 KG 推理 | https://arxiv.org/abs/2310.11220 |
| Unifying LLMs and KGs | 论文 | IEEE TKDE 2024 | LLM+KG 统一路线图，三大框架分类 | https://arxiv.org/abs/2306.08302 |
| PyKEEN | 项目 | 1,900 star | 40 个 KGE 模型，AEGI 已在使用 | https://github.com/pykeen/pykeen |
| tkger | 资源 | — | 2024-2025 TKG 论文最全列表（100+ 篇） | https://github.com/stmrdus/tkger |

---

## 关键数据集参考

AEGI 的 GDELT 数据可直接用于以下 TKG 基准评估：

| 数据集 | 实体数 | 关系数 | 时间戳数 | 三元组数 | 时间类型 |
|--------|--------|--------|----------|----------|----------|
| ICEWS14 | 7,128 | 230 | 365 | 90,730 | 时间点 |
| ICEWS05-15 | 10,488 | 251 | 4,017 | 479,329 | 时间点 |
| ICEWS18 | 23,033 | 256 | 304 | 468,558 | 时间点 |
| GDELT | 500 | 20 | 366 | 3,419,607 | 时间点 |
| YAGO15k | 15,403 | 32 | 169 | 138,048 | 时间区间 |

---

## 关键发现与建议

### 发现 1：LLM 正在颠覆 TKG 推理范式

2023-2024 年出现了明显的范式转移：从专用 TKG 嵌入模型（TTransE、RE-NET 等）转向 LLM 驱动的方法。GenTKG 和 ICL-TKG 两篇论文证明，LLM 仅通过 in-context learning 就能达到与专用模型相当的性能，且具备跨域泛化能力。这对 AEGI 意味着：不必从零训练 TKG 模型，可以直接利用现有 LLM 后端做时序预测。

### 发现 2：KG+LLM 的最佳实践是"结构化引导"而非"暴力注入"

Think-on-Graph 和 RoG 代表了 KG+LLM 结合的最新方向：不是把整个子图塞进 prompt（GraphRAG 的做法），而是让 LLM 在 KG 上做结构化探索（beam search / relation path planning）。这种方法更高效、更可解释、更可控。AEGI 当前的 chat KG 推理（2-hop 邻居 + 路径发现）可以升级为 ToG 风格的迭代探索。

### 发现 3：AEGI 的 GDELT 数据是天然的 TKG 训练/评估资源

GDELT 是 TKG 领域最常用的基准数据集之一（RE-Net、HGLS、TFLEX 等都支持）。AEGI 已有完整的 GDELT 摄入管道，这意味着可以直接将学术界的 TKG 模型应用于 AEGI 的真实数据，无需额外的数据准备工作。

### 发现 4：可解释性是 KG 推理在情报分析中的核心优势

xERTE（可解释子图推理）、RoG（忠实推理路径）、ToG（可追溯推理）都强调可解释性。这与 AEGI 的证据链红线（Evidence-first + SourceClaim-first）高度一致。KG 推理的每一步都可以映射到证据链路径，这是纯 LLM 推理无法提供的。

### 建议：分阶段集成路线

**短期（1-2 周）— ICL-TKG 预测**：
- 实现基于 in-context learning 的 TKG 预测，复用现有 LLM 后端
- 从 Neo4j 提取历史事件序列 → 格式化为 prompt → LLM 预测 → 结果写回图谱
- 参考 ICL-TKG 论文的 prompt 设计，零训练成本
- 改动范围：新增 `services/tkg_forecaster.py`，修改 pipeline 增加 `tkg_predict` 阶段

**中期（1-2 月）— ToG 风格的图谱推理升级**：
- 将 chat 模块的 KG 推理从"2-hop 邻居"升级为 ToG 的迭代 beam search
- 集成 LightRAG 的双层检索替代当前的简单向量检索
- 推理路径可视化，对接 KG viz API
- 改动范围：重构 `chat/` 的 KG 推理逻辑，增强 `services/graph_analysis.py`

**长期（3-6 月）— 专用 TKG 模型训练**：
- 基于 AEGI 的 GDELT 数据训练 RE-GCN 或 HGLS 模型
- 将预测结果作为"预测边"融入 Neo4j 图谱
- 与 LLM 预测结果做集成（ensemble），提升预测可靠性
- 评估 TimeLlama 的指令微调方案，用 AEGI 的领域数据微调时序推理能力
