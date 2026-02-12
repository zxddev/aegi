<!-- Author: msq -->
# 方向 6：多源情报融合

## 搜索过程记录

共执行 8 轮 WebSearch + 15 次 WebFetch 深度抓取：

| 轮次 | 查询关键词 | 主要收获 |
|------|-----------|---------|
| 1 | multi-source intelligence fusion data fusion 2024-2026 | 综述性结果，定位到 Information Fusion 期刊方向 |
| 2 | Dempster-Shafer evidence theory applications intelligence | arXiv 23 篇相关论文，覆盖 2003-2026 |
| 3 | belief function theory evidence aggregation conflicting sources | 定位到冲突证据管理的核心论文 |
| 4 | information fusion uncertainty quantification propagation | GitHub uncertainty-quantification topic，20+ 项目 |
| 5 | conflicting evidence aggregation multi-source reliability | 定位到 ICEF、PCR、LNS-CR 等组合规则 |
| 6 | OSINT fusion framework open source intelligence integration | arXiv 无直接结果，转向 GitHub topics |
| 7 | Bayesian evidence fusion multi-modal intelligence | 与贝叶斯 ACH 互补的 Dirichlet-DS 融合方向 |
| 8 | github evidence fusion Dempster-Shafer belief function tools | dstz、pyevidence、ClusterBBA 等项目 |

补充抓取：arXiv evidential deep learning + DS fusion、GitHub topics (dempster-shafer / evidence-theory / information-fusion / uncertainty-quantification)、contextual discounting 论文、组合规则综述。

同时阅读了 AEGI 现有代码：`assertion_fuser.py`（规则+LLM 冲突检测）、`bayesian_ach.py`（贝叶斯 ACH 引擎）、`source_credibility.py`（域名信誉评分）。

---

## 核心论文（精选 5 篇）

### 论文 1：Deep Evidential Fusion with Uncertainty Quantification and Contextual Discounting

- **作者**：Ling Huang, Su Ruan, Pierre Decazes, Thierry Denoeux
- **年份**：2023 (v1) / 2024 (v2)
- **会议/期刊**：arXiv:2309.05919，扩展自 MICCAI 2022
- **核心贡献**：
  - 提出 contextual discounting（上下文折扣）机制：为每个信息源分配一个折扣率向量，反映该源在不同判断任务上的可靠性差异
  - 折扣后的证据通过 Dempster 规则组合，输出包含不确定性量化的最终决策
  - 关键创新：可靠性不是全局标量，而是按任务/上下文变化的向量
- **与 AEGI 的关联**：
  - AEGI 当前 `source_credibility.py` 只输出全局标量分数（0.0-1.0），无法表达"某来源在军事领域可信但在经济领域不可信"
  - contextual discounting 可直接升级 assertion_fuser：将 source credibility score 从标量扩展为按 claim 主题/领域的向量，融合时按上下文折扣
  - 与 Bayesian ACH 的 likelihood 映射天然互补：credibility discount 作用于 P(E|H) 之前
- **链接**：https://arxiv.org/abs/2309.05919

### 论文 2：Trusted Multi-View Classification with Dynamic Evidential Fusion (TMC)

- **作者**：Zongbo Han, Changqing Zhang, Huazhu Fu, Joey Tianyi Zhou
- **年份**：2022 (v1) / 2024 (IEEE TPAMI)
- **会议/期刊**：IEEE Transactions on Pattern Analysis and Machine Intelligence
- **核心贡献**：
  - 用 Dirichlet 分布参数化每个"视图"（信息源）的类别概率分布，参数即为"证据量"
  - 通过 Dempster-Shafer 组合规则在证据层面动态融合多视图
  - 输出不仅有分类结果，还有校准的不确定性估计（区分 aleatoric 和 epistemic uncertainty）
  - 对噪声、损坏、OOD 数据具有鲁棒性
- **与 AEGI 的关联**：
  - AEGI 的 assertion_fuser 当前用硬编码 confidence（冲突=0.5，无冲突=0.9），缺乏理论基础
  - TMC 的 Dirichlet 参数化方案可替代硬编码：每个 SourceClaim 产生一个 Dirichlet 证据向量，融合后自然得到 confidence + uncertainty
  - 与 Bayesian ACH 的概率更新框架一致：Dirichlet 是 Categorical 分布的共轭先验
- **链接**：https://arxiv.org/abs/2204.11423

### 论文 3：Guaranteeing Consistency in Evidence Fusion — A Novel Perspective on Credibility (ICEF)

- **作者**：Chaoxiong Ma, Yan Liang, Huixia Zhang, Hao Sun
- **年份**：2025
- **核心贡献**：
  - 提出迭代可信证据融合（ICEF）：用 plausibility-belief 算术-几何散度度量证据间冲突
  - 解决经典 Dempster 规则在高冲突场景下的反直觉结果（Zadeh 反例）
  - 迭代式信誉评估：每轮融合后重新计算各源可信度权重，收敛后输出最终结果
  - 保证融合一致性：即使输入高度冲突，输出也不会出现 Zadeh 悖论
- **与 AEGI 的关联**：
  - AEGI 的 assertion_fuser 已检测 4 类冲突（value/modality/temporal/geographic + LLM semantic），但检测到冲突后只是标记 `has_conflict=True` 并降低 confidence 到 0.5，没有冲突解决机制
  - ICEF 的迭代信誉加权可直接用于冲突解决：冲突 claims 不是简单降权，而是根据与其他证据的一致性动态调整权重
  - plausibility-belief 散度可作为 assertion_fuser 的冲突严重度量化指标（替代当前的布尔 has_conflict）
- **链接**：arXiv 2025（搜索结果中标注为 April 2025）

### 论文 4：FNBT: Full Negation Belief Transformation for Open-World Information Fusion

- **作者**：Meishen He, Wenjun Ma, Jiao Wang, Huijun Yue, Xiaoma Fan
- **年份**：2025
- **核心贡献**：
  - 解决异构辨识框架（heterogeneous frame of discernment）下的证据融合问题
  - 经典 DS 理论要求所有证据在同一辨识框架下，FNBT 通过全否定信念变换将不同框架的证据统一
  - 保持 mass function 不变性，解决 Zadeh 反例
  - 适用于开放世界场景：新类别/新假设可以动态加入
- **与 AEGI 的关联**：
  - AEGI 的多源情报天然是异构的：不同来源可能用不同的分类体系描述同一事件
  - assertion_fuser 当前按 `attributed_to` 分组，隐含假设所有 claims 在同一语义框架下
  - FNBT 的框架统一能力对 AEGI 的跨来源融合至关重要：不同媒体对同一事件的分类/标签体系不同
- **链接**：arXiv:2508.08399（August 2025）

### 论文 5：Uncertainty-Aware Multimodal Emotion Recognition through Dirichlet Parameterization

- **作者**：Rémi Grzeczkowicz, Eric Soriano, Ali Janati 等
- **年份**：2026
- **核心贡献**：
  - 提出模型无关、任务无关的融合机制：基于 DS 理论和 Dirichlet 证据的轻量级多模态融合
  - 不需要额外训练即可融合不同模态的输出
  - 关键特性：融合机制与上游模型解耦，可即插即用
- **与 AEGI 的关联**：
  - "模型无关、任务无关"的设计理念与 AEGI 的需求高度匹配：AEGI 需要融合来自不同 pipeline stage 的输出（claim extraction、hypothesis engine、OSINT collector）
  - 轻量级特性适合 AEGI 的实时分析场景
  - Dirichlet 参数化与论文 2 (TMC) 一脉相承，可统一实现
- **链接**：arXiv:2502.06643（February 2026）

---

## 开源项目（精选 3 个）

### 项目 1：dstz — Evidence Theory Python Package

- **GitHub**：https://github.com/ztxtech/dstz
- **Star 数**：8
- **许可证**：MIT
- **核心功能**：
  - Dempster-Shafer 理论完整实现：mass function、belief、plausibility 计算
  - 冲突证据融合（Dempster 组合规则）
  - Pignistic 概率变换（belief → 概率，用于决策）
  - Random Permutation Set 操作
  - 信息熵和维度计算
- **集成可行性**：高
  - 纯 Python，MIT 许可，pip install dstz 即可
  - Python >= 3.7，与 AEGI 的 Python 3.12 兼容
  - API 设计清晰：Core (Atom, Distribution) → Element (Combination) → Evpiece (Dual, Single)
  - 有 ReadTheDocs 文档
- **集成建议**：
  - 作为 assertion_fuser 的数学后端：将 SourceClaim 的 confidence + credibility 转换为 mass function，用 dstz 的组合规则融合
  - 替代当前硬编码的 confidence 赋值（0.5/0.9）：通过 Dempster 组合规则计算融合后的 belief/plausibility 区间
  - Pignistic 变换输出最终 confidence 值，供 Bayesian ACH 使用

### 项目 2：pyevidence — Efficient Evidence Theory for Python

- **GitHub**：https://github.com/emiruz/pyevidence
- **Star 数**：4
- **许可证**：未标注（需确认）
- **核心功能**：
  - 高效 bit vector 编码 focal set，O(1) 集合操作
  - 支持 Yager 规则和 Dubois-Prade 规则（两种主流冲突处理策略）
  - Binary coarsening 实现高效 belief/plausibility 计算
  - Monte Carlo 估计器用于大规模问题
  - 多维 Cartesian product 子集表示
- **集成可行性**：中
  - 纯 Python，pip 安装
  - 关键优势：同时支持 Yager 和 Dubois-Prade 两种组合规则，适合对比实验
  - Yager 规则：冲突质量分配给全集（保守策略）
  - Dubois-Prade 规则：冲突质量分配给析取（折中策略）
  - 限制：只支持 Cartesian product 子集，不支持任意集合操作
- **集成建议**：
  - 与 dstz 互补使用：dstz 做通用 DS 计算，pyevidence 做高效大规模融合
  - 特别适合 AEGI 的批量 OSINT 融合场景：大量 claims 需要快速组合
  - Yager vs Dubois-Prade 的选择可作为 assertion_fuser 的配置项

### 项目 3：ClusterBBA — Cluster-Level Information Fusion for D-S Evidence Theory

- **GitHub**：https://github.com/Ma-27/ClusterBBA
- **Star 数**：0（新项目，但有正式发表论文）
- **许可证**：MIT
- **发表**：Mathematics 2025, 13(19), 3144 (DOI: 10.3390/math13193144)
- **核心功能**：
  - 四阶段融合框架：
    1. 证据聚类 + 质心构建（Deng 熵分形算子）
    2. 簇间散度度量（D_CC，捕获置信强度差异和结构支持广度）
    3. 动态证据分配（贪心分配规则，最大化簇间分离度）
    4. 两阶段加权融合（基于簇大小、证据-簇一致性、簇分离度的信誉权重）
  - 解决经典 DS 规则在高冲突场景下的反直觉结果
  - 支持贝叶斯优化自动调参
- **集成可行性**：中高
  - 纯 Python，MIT 许可
  - 四阶段框架与 AEGI 的 pipeline 架构天然契合
  - 有正式发表论文支撑理论基础
- **集成建议**：
  - 最适合 AEGI 的"多源冲突解决"场景：当 assertion_fuser 检测到大量冲突 claims 时，用 ClusterBBA 先聚类再融合
  - 聚类阶段可利用 AEGI 已有的 source_credibility 分数作为先验
  - 簇间散度 D_CC 可作为冲突严重度的量化指标（替代当前的布尔 has_conflict）
  - 两阶段加权融合的 α 参数可暴露为 API 配置项，让分析师调整专家偏置

---

## 补充工具：不确定性量化

| 项目 | Stars | 与 AEGI 关联 |
|------|-------|-------------|
| [uncertainty-toolbox](https://github.com/uncertainty-toolbox/uncertainty-toolbox) | 2k | 校准度量 + 可视化，可用于评估 assertion_fuser 输出的 confidence 是否校准 |
| [UQ360](https://github.com/IBM/UQ360) | 268 | IBM 出品，提供预测区间评估，可用于 Bayesian ACH 的不确定性评估 |
| [torch-uncertainty](https://github.com/torch-uncertainty/torch-uncertainty) | 478 | Evidential Deep Learning 实现，含 Dirichlet 参数化，与论文 2/5 的方法对应 |

---

## 关键发现与建议

### 发现 1：AEGI 当前融合层的核心短板是"检测冲突但不解决冲突"

`assertion_fuser.py` 能检测 4 类规则冲突 + 1 类 LLM 语义冲突，但检测到冲突后只做两件事：标记 `has_conflict=True`、将 confidence 从 0.9 降到 0.5。这是一个二值化的降级处理，丢失了冲突的严重程度、来源可信度差异、证据支持结构等关键信息。

### 发现 2：Dempster-Shafer 理论是 Bayesian ACH 的天然互补

AEGI 的 Bayesian ACH 处理的是"证据→假设"的似然度更新，本质是概率框架。DS 理论处理的是"证据→证据"的融合和冲突量化，本质是信念函数框架。两者不冲突：

- DS 层：多源 SourceClaims → 融合为 Assertion（带 belief/plausibility 区间）
- Bayesian 层：Assertion → 更新 Hypothesis 后验概率

这正好对应 AEGI 证据链的两个阶段：`SourceClaim → Assertion`（DS 融合）和 `Assertion → Judgment`（贝叶斯更新）。

### 发现 3：contextual discounting 是 source_credibility 的理论升级路径

当前 `source_credibility.py` 输出全局标量分数。contextual discounting（论文 1）将其升级为按主题/领域的向量。实现路径：

1. 扩展 `CredibilityScore` 数据类，增加 `domain_scores: dict[str, float]` 字段（如 `{"military": 0.9, "economy": 0.5}`）
2. 在 assertion_fuser 中，根据 claim 的主题选择对应的 discount rate
3. 折扣后的 mass function 再通过 DS 组合规则融合

### 建议实施路径

**P0（立即可做，1-2 天）**：引入 dstz 作为依赖，在 assertion_fuser 中实现基础 DS 融合：
- 将 SourceClaim 的 confidence + credibility 转换为 mass function
- 用 Dempster 组合规则替代当前的硬编码 confidence 赋值
- Pignistic 变换输出 confidence 值
- 输出 belief/plausibility 区间（替代单一 confidence 标量）

**P1（1 周）**：实现冲突量化和解决：
- 引入 ClusterBBA 的簇间散度 D_CC 作为冲突严重度指标
- 实现 ICEF 的迭代信誉加权：冲突 claims 根据与其他证据的一致性动态调整权重
- 将 has_conflict 从布尔值升级为连续的冲突度量

**P2（2 周）**：contextual discounting + Dirichlet 参数化：
- 扩展 source_credibility 为按领域的向量评分
- 实现 Dirichlet 证据参数化（论文 2/5），替代硬编码 confidence
- 与 Bayesian ACH 的 likelihood 映射对接：DS 融合输出的 belief 区间 → Bayesian 更新的似然度

**依赖关系**：P0 → P1 → P2，每步都可独立交付价值。
