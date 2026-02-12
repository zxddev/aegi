# AEGI 深度学术调研与开源项目评估（给 Claude Code）

## 任务

对 AEGI 项目进行一次**深度、系统性**的学术论文和开源项目调研。不是简单搜几个关键词就完事，而是要像写综述论文一样，沿着引用链、作者链、会议链深挖。

**目标：** 找到能直接提升 AEGI 分析能力的论文、算法、开源项目，并给出具体的集成建议。

**输出：** 一份完整的调研报告，保存到 `/home/user/workspace/gitcode/aegi/code/docs/review/2026-02-12/deep-research-report.md`

## 工具使用

你已经配置了两个 MCP 搜索工具，**必须充分利用**：

### Sequential Thinking MCP
- 结构化深度思考工具，用于复杂分析和推理
- **每个方向的"关键发现与建议"部分，必须先用 sequential-thinking 进行深度思考**，再写结论
- 用于：
  - 评估某个论文/项目与 AEGI 的契合度时，用 sequential-thinking 逐步分析利弊
  - 对比多个候选方案时，用 sequential-thinking 做结构化对比推理
  - 写"综合建议"时，用 sequential-thinking 梳理优先级和依赖关系
  - 遇到复杂的技术集成问题时，用 sequential-thinking 拆解思考
- 不要跳过这一步直接写结论，深度思考的质量决定了建议的质量

### Tavily MCP
- 深度搜索引擎，专为 AI agent 设计，返回结构化结果
- 用于：学术论文搜索、技术方案调研、项目评估
- 优势：能深入抓取页面内容，返回摘要和关键信息
- 每个方向至少用 Tavily 搜 5-8 次不同查询

### Exa MCP
- 语义搜索引擎，擅长找相似内容和学术资源
- 用于：论文发现、相似项目发现、引用链追踪
- 优势：语义理解强，能找到关键词搜不到的相关内容
- 每个方向至少用 Exa 搜 5-8 次不同查询

### 搜索策略
- **交替使用 Tavily 和 Exa**，两者互补：Tavily 擅长精确搜索，Exa 擅长语义发现
- 先用 Tavily 搜关键词，从结果中提取新术语，再用 Exa 做语义扩展
- 找到核心论文后，用 Exa 搜 "similar to" 找相关工作
- 找到核心项目后，用 Tavily 搜项目名 + "alternatives" / "comparison"

### 其他工具
- 用 `curl` 或 `wget` 下载论文 PDF（走代理：`export https_proxy=http://127.0.0.1:7890`）
- 用 `git clone` 克隆开源项目（走代理）
- 用本地 SearXNG（http://127.0.0.1:8888）做补充搜索

## 调研方法（必须严格遵循）

### 1. 搜索策略 — 不能只搜一轮

每个方向至少执行以下搜索路径：

**路径 A：关键词搜索（至少 3 轮，每轮换关键词，Tavily + Exa 交替）**
- 第 1 轮：直接关键词（如 "intelligence analysis AI"）→ Tavily
- 第 2 轮：从第 1 轮结果中提取的专业术语再搜（如 "structured analytic techniques automation"）→ Exa
- 第 3 轮：结合具体技术搜（如 "bayesian ACH LLM evidence assessment"）→ Tavily
- 第 4 轮：用 Exa 的语义搜索找 "similar to" 第 1-3 轮的核心结果

**路径 B：引用链追踪**
- 找到一篇高质量论文后，用 Exa 搜论文标题找引用关系
- 用 Tavily 搜 "papers citing [论文标题]" 或 Semantic Scholar API
- 重点关注 2024-2026 年的新引用

**路径 C：作者链追踪**
- 找到关键作者后，用 Exa 搜作者名找其他论文
- 特别关注：Philip Tetlock 团队、IARPA 项目相关研究者、CMU/MIT/Stanford 的情报分析研究组

**路径 D：会议/期刊追踪**
- 用 Tavily 搜 "[会议名] 2025 2026 intelligence analysis" 等
- 重点会议：AAAI, NeurIPS, ICML, ACL, EMNLP, KDD, WWW, CIKM
- 重点期刊：Intelligence and National Security, International Journal of Intelligence, Studies in Intelligence
- 重点 workshop：NLP4IF (NLP for Internet Freedom), FEVER (Fact Extraction and VERification)

**路径 E：GitHub 深度搜索**
- 用 Tavily 搜 "github [关键词] intelligence analysis"
- 用 Exa 搜 "open source [功能描述] project"
- 看 star 趋势、最近更新时间、issue 活跃度
- 重点关注有论文支撑的项目（不是纯工程项目）

### 2. 每个方向的搜索量要求

每个调研方向至少：
- 搜索 10+ 个不同的查询词组合
- 阅读 20+ 篇论文的摘要
- 深入阅读 5+ 篇核心论文
- 评估 5+ 个开源项目
- 最终精选 3-5 个最有价值的推荐

## 调研方向（8 个）

### 方向 1：LLM + 情报分析（核心方向）

搜索关键词起点：
- "LLM intelligence analysis", "AI-assisted intelligence", "automated analytic tradecraft"
- "LLM structured analytic techniques", "AI hypothesis generation"
- "large language model geopolitical analysis", "LLM forecasting geopolitics"
- "IARPA AI", "IC (intelligence community) AI tools"
- "analytic confidence assessment AI", "cognitive bias detection AI"

重点关注：
- 美国情报界（IC）的 AI 项目和论文（IARPA 资助的研究）
- LLM 在结构化分析技术（SAT）中的应用
- LLM 做情报评估的可靠性研究
- 多 agent 协作做情报分析的框架

### 方向 2：事件预测与预判

搜索关键词起点：
- "event forecasting machine learning", "geopolitical event prediction"
- "temporal point process event prediction", "GDELT event forecasting"
- "conflict prediction AI", "crisis early warning system"
- "superforecasting algorithm", "prediction market aggregation"
- "ICEWS prediction", "CAMEO event coding automation"

重点关注：
- 基于 GDELT/ICEWS 的事件预测模型
- 超级预测者方法论的算法化实现
- 时序事件模型（Hawkes process, Neural Hawkes, THP）
- 预测市场聚合算法（Metaculus, Polymarket 的技术）

### 方向 3：因果推断在情报分析中的应用

搜索关键词起点：
- "causal inference intelligence analysis", "causal discovery event data"
- "DoWhy applications", "causal inference observational data geopolitics"
- "counterfactual reasoning AI", "causal inference text data"
- "causal inference knowledge graph", "causal relation extraction NLP"

重点关注：
- 从文本中提取因果关系的方法
- 在事件数据（GDELT/ICEWS）上做因果发现
- 因果推断 + LLM 的结合
- 反事实推理在情报分析中的应用

### 方向 4：知识图谱推理与时序推理

搜索关键词起点：
- "temporal knowledge graph reasoning", "TKG completion"
- "knowledge graph event prediction", "dynamic knowledge graph"
- "knowledge graph link prediction geopolitical"
- "graph neural network event forecasting"
- "knowledge graph question answering intelligence"

重点关注：
- 时序知识图谱（TKG）的最新模型
- 在政治/安全领域的 KG 应用
- KG + LLM 的结合（GraphRAG 之外的方法）
- 动态图上的推理

### 方向 5：虚假信息检测与信息战分析

搜索关键词起点：
- "misinformation detection", "disinformation campaign detection"
- "propaganda detection NLP", "information warfare AI"
- "fake news detection knowledge graph", "claim verification"
- "coordinated inauthentic behavior detection", "bot detection"
- "narrative analysis NLP", "framing detection"

重点关注：
- 多源交叉验证的自动化方法
- 信息战/影响力操作的检测
- 叙事分析和框架检测
- 与 AEGI 现有的 coordination_detector、narrative_builder 的结合点

### 方向 6：多源情报融合

搜索关键词起点：
- "multi-source intelligence fusion", "data fusion intelligence"
- "evidence fusion Dempster-Shafer", "belief function theory"
- "information fusion uncertainty", "conflicting evidence aggregation"
- "multi-modal intelligence analysis", "OSINT fusion framework"

重点关注：
- Dempster-Shafer 证据理论（与贝叶斯 ACH 互补）
- 多源冲突证据的融合方法
- 不确定性量化和传播
- 与 AEGI 现有的 assertion_fuser 的结合点

### 方向 7：态势感知与趋势检测

搜索关键词起点：
- "situation awareness AI", "situational awareness NLP"
- "trend detection event stream", "change point detection"
- "anomaly detection event data", "emerging topic detection"
- "crisis detection social media", "early warning indicator"

重点关注：
- 从事件流中检测趋势变化和转折点
- 异常检测在安全事件中的应用
- 态势图自动生成
- 与 GDELT 异常检测的结合

### 方向 8：人机协作情报分析

搜索关键词起点：
- "human-AI collaboration intelligence analysis", "analyst-in-the-loop"
- "explainable AI intelligence", "XAI national security"
- "interactive hypothesis exploration", "visual analytics intelligence"
- "calibration AI confidence", "AI-assisted decision making"

重点关注：
- 如何让 AI 分析结果对人类分析师有用（不是替代，是增强）
- 可解释性在情报分析中的重要性
- 人机协作的交互模式
- 分析师信任校准

## 输出格式

报告结构：

```markdown
# AEGI 深度学术调研报告
> 日期：2026-02-12
> 调研范围：8 个方向，XX 篇论文，XX 个开源项目

## 执行摘要
（500 字以内，最重要的发现和建议）

## 方向 1：LLM + 情报分析
### 搜索过程记录
（记录每轮搜索用了什么关键词，找到了什么）
### 核心论文（精选 3-5 篇）
每篇包含：
- 标题、作者、年份、会议/期刊
- 核心贡献（3-5 句话）
- 与 AEGI 的关联（具体到哪个模块可以借鉴什么）
- 论文链接 / arXiv ID
### 开源项目（精选 2-3 个）
每个包含：
- 名称、GitHub 链接、star 数、最近更新
- 核心功能
- 与 AEGI 的集成可行性评估
- 具体集成建议
### 关键发现与建议

（每个方向重复以上结构）

## 综合建议
### 短期可集成（1-2 周）
### 中期可集成（1-2 月）
### 长期研究方向
### 推荐下载的论文和项目清单
```

## 关键约束

- **深度优先**：宁可少覆盖几个方向，也要把每个方向搜透。不要蜻蜓点水。
- **记录搜索过程**：每个方向记录你搜了什么、找到了什么、为什么选择深入某些结果。这样主人可以判断调研质量。
- **2024-2026 优先**：重点关注最近 2 年的工作，但经典论文也要覆盖。
- **实用导向**：不是写学术综述，是为 AEGI 找可用的东西。每个推荐都要说清楚"AEGI 怎么用"。
- **下载论文**：找到的核心论文如果有 PDF 链接（arXiv 等），下载到 `/home/user/workspace/gitcode/aegi/references/papers/`，命名格式 `{简短名}-{年份}.pdf`。
- **克隆项目**：评估为高价值的开源项目，克隆到 `/home/user/workspace/gitcode/aegi/references/opensource/`。注意走代理：`git clone` 前设置 `export https_proxy=http://127.0.0.1:7890`。
- **不要编造**：如果某个方向确实没找到好的结果，如实说明，不要凑数。
- **耐心执行**：这个任务预计需要 2-4 小时。不要急，每个方向都认真搜。
