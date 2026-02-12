<!-- Author: msq -->
# 方向 3：因果推断在情报分析中的应用

> 日期：2026-02-12
> 调研范围：8 轮搜索，30+ 篇论文摘要，10+ 开源项目评估

## 搜索过程记录

### 第 1 轮：因果推断 + 情报分析 + 地缘政治
- 查询："causal inference intelligence analysis geopolitical events 2024 2025 2026"
- 结果：WebSearch 未返回直接结果，转向直接获取已知核心论文

### 第 2 轮：因果发现 + 事件数据（GDELT/ICEWS）
- 查询："causal discovery event data GDELT ICEWS machine learning"
- 结果：WebSearch 未返回直接结果，通过 WebFetch 直接获取 tigramite/PCMCI 项目信息

### 第 3 轮：DoWhy 应用与生态
- 查询："DoWhy Microsoft causal inference Python library tutorial"
- 直接获取 DoWhy GitHub（8000+ stars）、PyWhy 生态（DoWhy + EconML + causal-learn）
- 发现 PyWhy 已形成完整因果推断生态系统

### 第 4 轮：因果关系抽取 NLP
- 查询："causal relation extraction NLP text mining 2024 2025"
- 获取 DAPrompt（arXiv:2307.09813）— 事件因果识别的 prompt learning 方法
- 获取 "Event Causality Is Key to Computational Story Understanding"（arXiv:2311.09648）

### 第 5 轮：反事实推理 + AI
- 查询："counterfactual reasoning AI intelligence analysis"
- 获取 CLadder 基准（arXiv:2312.04350）— NeurIPS 2023，LLM 因果推理评估

### 第 6 轮：因果推断 + 知识图谱
- 查询："causal inference knowledge graph reasoning"
- 获取 pywhy-graphs（64 stars）— NetworkX 扩展的因果图表示库

### 第 7 轮：LLM + 因果推理
- 查询："LLM causal reasoning causal inference large language model"
- 核心发现：
  - Kiciman et al. (2023) "Causal Reasoning and Large Language Models"（TMLR）— LLM 因果推理能力的开创性评估
  - Jin et al. (2024) "Corr2Cause"（ICLR 2024）— 发现 LLM 在纯因果推理上接近随机
  - Jiralerspong et al. (2024) "Efficient Causal Graph Discovery Using LLMs"（Bengio 团队）— BFS 方法线性查询复杂度
  - Khatibi et al. (2024) "ALCM: Autonomous LLM-Augmented Causal Discovery"— 数据驱动 + LLM 混合框架

### 第 8 轮：开源因果推断工具
- 查询："github causal discovery causal inference open source tools"
- 系统评估了 10+ 个开源项目：
  - gCastle（华为，1.1k stars）— 20+ 因果发现算法
  - causal-learn（CMU，1.6k stars）— Tetrad 的 Python 移植
  - CausalDiscoveryToolbox（1.2k stars）— 图结构恢复
  - tigramite（1.6k stars）— 时序因果发现 PCMCI
  - CausalNex（McKinsey，2.4k stars）— 贝叶斯网络因果推理
  - EconML（Microsoft，4.5k stars）— 异质处理效应估计
  - CausalAI（Salesforce，314 stars，已归档）
  - NOTEARS（667 stars）— 连续优化 DAG 结构学习
  - awesome-causality-algorithms — 综合索引

### 补充轮：NLP 因果推断综述
- 获取 Feder et al. "Causal Inference in NLP"（TACL）— NLP 因果推断的系统综述
- 获取 Kaddour et al. "Causal Machine Learning: A Survey"（191 页综合综述）

## 核心论文（精选 5 篇）

### 论文 1：Causal Reasoning and Large Language Models: Opening a New Frontier for Causality

- **作者**：Emre Kiciman, Robert Ness, Amit Sharma, Chenhao Tan
- **年份**：2023
- **发表**：Transactions on Machine Learning Research (TMLR)
- **链接**：https://arxiv.org/abs/2305.00050

**核心贡献**：
首次系统评估 LLM 在因果推理任务上的表现。GPT-4 在成对因果发现上达到 97% 准确率（比现有方法提升 13 个百分点），反事实推理 92%（提升 20 个百分点），事件因果任务 86%。关键发现是 LLM 能泛化到训练截止日期之后的新数据集，说明能力不仅仅是记忆。但模型存在不可预测的失败模式。论文建议将 LLM 与现有因果技术结合使用。

**与 AEGI 的关联**：
AEGI 的 `causal_reasoner.py` 已经用 LLM 做反事实评分和混淆因素检测（`aanalyze_causal_links`），这篇论文验证了这个方向的可行性。但论文也指出 LLM 有不可预测的失败模式，AEGI 当前的 fallback 到规则版本的设计（`analyze_causal_links` 作为 baseline）是正确的防御策略。可以借鉴论文中的 prompt 设计模式，改进 `_CAUSAL_PROMPT` 的结构。

### 论文 2：Efficient Causal Graph Discovery Using Large Language Models

- **作者**：Thomas Jiralerspong, Xiaoyin Chen, Yash More, Vedant Shah, Yoshua Bengio
- **年份**：2024
- **发表**：arXiv:2402.01207（Bengio 团队）
- **链接**：https://arxiv.org/abs/2402.01207

**核心贡献**：
提出基于 BFS 的 LLM 因果图发现框架，将查询复杂度从 O(n²) 降到 O(n)。传统方法对每对变量做成对查询，该方法用广度优先搜索策略，每次让 LLM 判断一个节点的所有邻居，大幅减少 API 调用次数。可结合观测数据进一步提升性能，在真实因果图上达到 SOTA。

**与 AEGI 的关联**：
AEGI 的 `causal_inference.py` 中 `build_causal_graph` 从 Neo4j 子图构建因果 DAG，但完全依赖图结构（边的存在性），没有利用 LLM 判断因果方向。可以引入该论文的 BFS 方法：从 Neo4j 提取实体后，用 LLM 判断因果方向，生成更准确的因果 DAG，再传给 DoWhy 做效应估计。线性查询复杂度使得这在实际系统中可行。

### 论文 3：ALCM: Autonomous LLM-Augmented Causal Discovery Framework

- **作者**：Elahe Khatibi, Mahyar Abbasian, Zhongqi Yang, Iman Azimi, Amir M. Rahmani
- **年份**：2024
- **发表**：arXiv:2405.01744
- **链接**：https://arxiv.org/abs/2405.01744

**核心贡献**：
提出数据驱动因果发现 + LLM 的自主混合框架。三个核心组件：(1) 因果结构学习（从观测数据学习初始图），(2) 因果包装器（统一接口），(3) LLM 驱动的因果精炼器（利用 LLM 知识库改进图结构）。在 7 个数据集上超越了纯 LLM 方法和纯数据驱动方法。关键创新是让 LLM 不是从零构建因果图，而是精炼数据驱动方法的输出。

**与 AEGI 的关联**：
这是 AEGI 因果推断模块最直接可借鉴的架构。当前 AEGI 的 `CausalInferenceEngine` 纯粹依赖图结构 + DoWhy，而 `causal_reasoner.py` 纯粹依赖 LLM。ALCM 的混合架构提供了一个将两者统一的蓝图：先用 PCMCI/NOTEARS 从 GDELT 时序数据学习初始因果结构，再用 LLM 精炼（添加领域知识、修正方向），最后用 DoWhy 做效应估计和反驳检验。

### 论文 4：CLadder: Assessing Causal Reasoning in Language Models

- **作者**：Zhijing Jin, Yuen Chen, Felix Leeb 等（Bernhard Scholkopf 团队）
- **年份**：2023
- **发表**：NeurIPS 2023
- **链接**：https://arxiv.org/abs/2312.04350
- **数据集**：https://huggingface.co/datasets/causalNLP/cladder

**核心贡献**：
构建了 10K 样本的因果推理基准 CLadder，基于 Pearl 因果推断框架的三个层次：关联（observational）、干预（interventional）、反事实（counterfactual）。发现 LLM 在形式化因果推理上表现很差。提出 CausalCoT（因果思维链）提示策略来改善性能。关键洞察：LLM 的"因果推理"更多是模式匹配而非真正的因果理解。

**与 AEGI 的关联**：
这篇论文对 AEGI 的设计哲学有重要启示。AEGI 的 `causal_reasoner.py` 让 LLM 做反事实评分，但 CLadder 表明 LLM 在形式化反事实推理上不可靠。建议：(1) LLM 负责因果关系的"发现"和"表述"（它擅长的），(2) 形式化的因果推断（效应估计、反事实计算）交给 DoWhy，(3) 用 CausalCoT 提示策略改进 `_CAUSAL_PROMPT`。

### 论文 5：Causal Inference in Natural Language Processing: Estimation, Prediction, Interpretation and Beyond

- **作者**：Amir Feder, Katherine Keith, Reid Pryzant, Jacob Eisenstein 等
- **年份**：2022
- **发表**：Transactions of the Association for Computational Linguistics (TACL)
- **链接**：https://arxiv.org/abs/2109.00725

**核心贡献**：
NLP 因果推断的系统综述，覆盖三大应用场景：(1) 文本作为结果变量（treatment → text），(2) 文本作为处理变量（text → outcome），(3) 文本作为混淆变量。建立了统一的定义框架，梳理了文本数据做因果推断的特殊挑战（高维、非结构化、语义歧义）。

**与 AEGI 的关联**：
AEGI 的核心场景正是"从文本中做因果推断"。论文的框架可以指导 AEGI 的因果模块设计：(1) 从新闻文本（GDELT）中提取因果声明（text as treatment），(2) 评估事件对态势的因果影响（text as outcome），(3) 处理新闻来源偏见作为混淆变量。特别是论文讨论的"text as confounder"场景，与 AEGI 的多源情报融合直接相关。

## 开源项目（精选 3 个）

### 项目 1：tigramite — 时序因果发现（PCMCI）

- **GitHub**：https://github.com/jakobrunge/tigramite
- **Stars**：1,600+
- **许可证**：GPL-3.0
- **最近更新**：活跃维护中
- **依赖**：Python ≥3.10, NumPy, SciPy, Numba

**核心功能**：
专为时序数据设计的因果发现库。核心算法 PCMCI 及其变体（PCMCIplus, LPCMCI, RPCMCI, J-PCMCI+）能从高维非线性时序数据中发现因果关系。支持多种条件独立性检验（ParCorr 线性、CMIknn 非线性、GPDC 高斯过程等），处理缺失值，提供因果效应估计和中介分析。

**与 AEGI 的集成可行性**：高。AEGI 已有 GDELT 时序事件数据（`gdelt_monitor.py`、`gdelt_scheduler.py`），这些数据天然适合 PCMCI 分析。tigramite 的输入格式是时序矩阵，与 `CausalInferenceEngine._graph_to_dataframe` 的输出格式兼容。

**集成建议**：
1. 在 `causal_inference.py` 中新增 `discover_temporal_causes` 方法，用 PCMCI 从 GDELT 事件时序中发现因果结构
2. PCMCI 输出的因果图可以直接替代当前 `build_causal_graph` 中从 Neo4j 拓扑推断的因果方向
3. 具体流程：GDELT 事件 → 按实体/事件类型聚合为时序 → PCMCI 发现因果滞后关系 → 构建 DAG → DoWhy 估计效应
4. 注意 GPL-3.0 许可证，如果 AEGI 需要闭源发布，需要将 tigramite 作为独立服务调用而非直接嵌入

### 项目 2：gCastle — 因果结构学习工具链

- **GitHub**：https://github.com/huawei-noah/trustworthyAI/tree/master/gcastle
- **Stars**：1,100+
- **许可证**：Apache-2.0
- **最近版本**：1.0.4（2025 年 3 月）
- **依赖**：Python 3.6-3.9, NumPy, SciPy, PyTorch, scikit-learn, NetworkX

**核心功能**：
华为诺亚方舟实验室开发的因果结构学习工具链，包含 20+ 算法：
- 约束类：PC
- 函数类：ANM, DirectLiNGAM, ICALiNGAM, PNL, TTPM
- 评分类：GES
- 梯度类（核心优势）：NOTEARS, NOTEARS-MLP, NOTEARS-SOB, DAG-GNN, GOLEM, GraNDAG, MCSL, GAE, RL, CORL
- 提供数据生成、预处理（先验注入、变量选择）和评估指标（F1, SHD, FDR, TPR）

**与 AEGI 的集成可行性**：中高。gCastle 的梯度类算法（特别是 NOTEARS 系列）适合从 AEGI 的观测数据中学习因果结构。Apache-2.0 许可证友好。但 Python 版本要求（3.6-3.9）与 AEGI 的 Python 3.12 可能存在兼容性问题，需要测试。

**集成建议**：
1. 优先集成 NOTEARS（连续优化 DAG 学习），它将组合优化问题转化为连续优化，适合大规模数据
2. 用 gCastle 的评估指标（SHD, F1）来评估 AEGI 因果图的质量
3. 先验注入功能可以将 Neo4j 中已知的实体关系作为先验约束，提升因果发现准确率
4. 如果 Python 版本不兼容，可以直接使用 NOTEARS 的原始实现（https://github.com/xunzheng/notears, 667 stars, Python 3.6+）

### 项目 3：causal-learn — CMU 因果发现算法库

- **GitHub**：https://github.com/cmu-phil/causal-learn
- **Stars**：1,600+
- **许可证**：MIT
- **最近版本**：0.1.4.4（2025 年 12 月）
- **依赖**：标准 Python 科学计算栈

**核心功能**：
CMU 开发的因果发现算法 Python 实现，是经典 Java 框架 Tetrad 的 Python 移植和扩展。覆盖：
- 约束类和评分类因果发现方法
- 受约束的函数因果模型
- 隐因果表示学习
- 基于排列的发现方法
- Granger 因果分析
- 独立性检验、评分函数、图操作工具

**与 AEGI 的集成可行性**：高。MIT 许可证无限制，活跃维护（44 贡献者，638 commits），API 设计直观。作为 PyWhy 生态的一部分，与 AEGI 已使用的 DoWhy 天然兼容。

**集成建议**：
1. 用 causal-learn 的 PC 算法做初始因果结构发现，输出 CPDAG
2. 结合 LLM 判断（参考 ALCM 论文）将 CPDAG 中的无向边定向
3. 将定向后的 DAG 传给 DoWhy 做效应估计
4. causal-learn 的 Granger 因果分析可以直接应用于 GDELT 时序数据，作为 PCMCI 的轻量替代

## 补充评估的开源项目

| 项目 | Stars | 许可证 | 核心定位 | 与 AEGI 适配度 | 备注 |
|------|-------|--------|----------|---------------|------|
| DoWhy (py-why) | 8,000+ | MIT | 端到端因果推断 | **已集成** | AEGI 已用于效应估计 |
| EconML (py-why) | 4,500+ | MIT | 异质处理效应 | 中 | CATE 估计可用于分析不同地区/群体的差异化因果效应 |
| CausalNex (McKinsey) | 2,400+ | Apache-2.0 | 贝叶斯网络因果推理 | 中 | Do-calculus 干预分析，与 AEGI 贝叶斯 ACH 互补 |
| CausalDiscoveryToolbox | 1,200+ | MIT | 图结构恢复 | 中 | 算法全面但依赖 R，部署复杂 |
| NOTEARS (原始实现) | 667 | Apache-2.0 | 连续优化 DAG 学习 | 高 | 60 行核心实现，轻量可嵌入 |
| pywhy-graphs | 64 | MIT | 因果图表示 | 低 | 太底层，AEGI 已用 NetworkX |
| CausalAI (Salesforce) | 314 | BSD-3 | 因果分析平台 | 低 | 2025 年 5 月已归档，不推荐 |

## 关键发现与建议

### 发现 1：AEGI 当前因果模块的架构缺口

分析 AEGI 现有代码后发现两个独立的因果模块：

1. **`causal_inference.py`**（DoWhy 路径）：从 Neo4j 子图构建 DAG → DoWhy 效应估计 → 反驳检验。问题是因果图完全依赖 Neo4j 的边结构，没有因果发现过程，边的存在不等于因果关系。

2. **`causal_reasoner.py`**（LLM 路径）：基于 assertion 时序做规则因果链 + LLM 增强反事实评分。问题是 LLM 做形式化因果推理不可靠（CLadder 论文证实），且两个模块完全独立，没有信息流通。

**建议**：参考 ALCM 框架，将两个模块统一为三阶段流水线：
```
阶段 1（因果发现）：PCMCI/NOTEARS 从时序数据学习初始因果结构
阶段 2（LLM 精炼）：LLM 利用领域知识修正因果方向、补充遗漏边
阶段 3（效应估计）：DoWhy 做因果效应估计 + 反驳检验
```

### 发现 2：LLM 因果推理的能力边界已明确

两篇关键论文给出了互补的结论：
- Kiciman et al.：LLM 在常识因果判断上很强（97% 成对因果发现）
- Jin et al. (Corr2Cause + CLadder)：LLM 在形式化因果推理上接近随机

**结论**：LLM 适合做因果关系的"发现"和"表述"（哪些变量之间可能有因果关系），不适合做"计算"（效应大小、反事实值）。AEGI 应该让 LLM 负责因果图的构建和精炼，把数值计算交给 DoWhy/tigramite。

### 发现 3：时序因果发现是 AEGI 最大的增量价值点

AEGI 已有 GDELT 时序事件数据，但当前没有利用时序信息做因果发现。tigramite 的 PCMCI 算法专为此设计：
- 输入：多变量时序（GDELT 事件按实体/类型聚合）
- 输出：带滞后的因果图（"A 国制裁 → 3 天后 → B 国军事调动"）
- 优势：能发现时间滞后的因果关系，这是纯图结构方法做不到的

### 发现 4：从文本直接抽取因果关系是可行的补充路径

DAPrompt 和 "Event Causality Is Key" 两篇论文表明，从文本中识别事件因果关系已有成熟方法。AEGI 的 `claim_extractor` 目前提取的是一般性声明，可以扩展为同时提取因果声明（"X 导致了 Y"），构建因果知识图谱。

### 发现 5：PyWhy 生态是最佳技术栈选择

AEGI 已使用 DoWhy，而 PyWhy 生态（DoWhy + EconML + causal-learn + pywhy-graphs）提供了从因果发现到效应估计的完整链路，且全部 MIT 许可证、活跃维护、API 兼容。建议 AEGI 的因果模块全面拥抱 PyWhy 生态，而非引入多个独立库。

## 集成优先级建议

### 短期（1-2 周）
1. 改进 `_CAUSAL_PROMPT`，引入 CausalCoT 提示策略，明确区分 LLM 的因果发现角色和 DoWhy 的因果计算角色
2. 在 `claim_extractor` 中增加因果关系抽取模板（"X 导致 Y"、"X 引发 Y"），输出 `CausalClaim` 类型

### 中期（1-2 月）
1. 集成 causal-learn 的 PC 算法，为 `build_causal_graph` 增加数据驱动的因果发现能力
2. 集成 tigramite PCMCI，从 GDELT 时序数据发现时间滞后因果关系
3. 实现 ALCM 式的三阶段流水线：数据驱动发现 → LLM 精炼 → DoWhy 估计

### 长期研究方向
1. 构建 AEGI 专属的因果知识图谱（CausalKG），从文本抽取 + 时序发现 + 专家标注三个来源汇聚
2. 探索 EconML 的异质处理效应（CATE）估计，分析同一事件在不同地区/群体的差异化因果效应
3. 基于 CLadder 基准评估 AEGI 因果推理模块的准确性，建立持续评估机制
