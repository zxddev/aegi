# 方向 8：人机协作情报分析

> 日期：2026-02-12
> 调研范围：8 轮搜索 + 深度页面抓取，覆盖 arXiv、GitHub、Google Scholar

## 搜索过程记录

| 轮次 | 查询 | 来源 | 结果 |
|------|------|------|------|
| 1 | "human-AI collaboration intelligence analysis 2024 2025 2026" | WebSearch | 无直接结果 |
| 2 | "analyst-in-the-loop AI assisted decision making" | WebSearch | 无直接结果 |
| 3 | "explainable AI XAI national security intelligence" | WebSearch | 无直接结果 |
| 4 | "interactive hypothesis exploration visual analytics intelligence" | WebSearch | 无直接结果 |
| 5 | "AI confidence calibration trust human-AI teaming" | WebSearch | 无直接结果 |
| 6 | "visual analytics intelligence analysis sensemaking" | WebSearch | 无直接结果 |
| 7 | "cognitive bias mitigation AI decision support" | WebSearch | 无直接结果 |
| 8 | "github human-AI collaboration intelligence analysis tools" | WebSearch | 无直接结果 |
| 9 | GitHub topics: intelligence-analysis | WebFetch | 13 个项目，3 个高度相关 |
| 10 | arXiv: human AI collaboration intelligence analysis | WebFetch | 7 篇论文，5 篇高度相关 |
| 11 | arXiv: cognitive bias mitigation AI decision support | WebFetch | 4 篇论文，2 篇高度相关 |
| 12 | arXiv: trust calibration human AI teaming confidence | WebFetch | 1 篇核心论文 |
| 13 | arXiv: LLM knowledge graph interactive exploration | WebFetch | 12 篇论文，3 篇高度相关 |
| 14 | GitHub topics: osint-tool (按 star 排序) | WebFetch | 17 个项目，参考价值 |
| 15 | GitHub topics: visual-analytics (按 star 排序) | WebFetch | 20 个项目，参考价值 |
| 16 | 深度抓取 6 篇核心论文的 arXiv 页面 | WebFetch | 获取完整摘要和贡献 |
| 17 | 深度抓取 3 个核心 GitHub 项目 README | WebFetch | 获取架构和功能细节 |

## 核心论文（精选 5 篇）

### 论文 1：Who Should I Trust: AI or Myself?

- **标题**: Who Should I Trust: AI or Myself? Leveraging Human and AI Correctness Likelihood to Promote Appropriate Trust in AI-Assisted Decision-Making
- **作者**: Shuai Ma, Ying Lei, Xinru Wang, Chengbo Zheng, Chuhan Shi, Ming Yin, Xiaojuan Ma
- **年份**: 2023
- **会议/期刊**: arXiv:2301.05809 (cs.HC, cs.AI, cs.LG)
- **核心贡献**:
  提出了一个关键洞察：信任校准不能只看 AI 置信度，还必须建模人类自身的"正确率"。作者构建了一个近似人类决策模型来估计人类在特定任务上的正确概率，然后设计了三种策略来同时展示人类和 AI 的正确率，帮助用户判断"该信 AI 还是信自己"。293 人实验证明，同时考虑双方正确率比只展示 AI 置信度更能促进恰当信任。
- **与 AEGI 的关联**:
  AEGI 的假设分析和判断模块（Judgment → Assertion → SourceClaim）天然需要信任校准。当前 AEGI 展示 AI 分析结果时缺乏"分析师自身判断力"的建模。可以在假设评估界面中引入双向置信度展示：AI 对假设的支持度 + 分析师历史判断准确率，让分析师做出更理性的采纳决策。具体可集成到 `hypothesis_engine` 的输出中，增加 `analyst_correctness_likelihood` 字段。
- **链接**: https://arxiv.org/abs/2301.05809

### 论文 2：Fostering Human Learning is Crucial for Boosting Human-AI Synergy

- **标题**: Fostering Human Learning is Crucial for Boosting Human-AI Synergy
- **作者**: Julian Berger, Jason W. Burton, Ralph Hertwig 等 12 人
- **年份**: 2025
- **会议/期刊**: arXiv:2512.13253
- **核心贡献**:
  对 74 项人机协作研究的元分析，推翻了"人+AI 不如单独 AI"的悲观结论。关键发现：当实验设计中包含逐次反馈（trial-by-trial feedback）时，人机协作表现显著提升；当反馈与 AI 解释配对时，正向协同效应最强；而没有反馈只有 AI 解释时，反而产生负向协同。这说明人类需要学习机制来校准对 AI 的信任。

- **与 AEGI 的关联**:
  AEGI 当前的流式管道（SSE streaming）和报告生成已经能展示 AI 分析过程，但缺乏"反馈闭环"。建议在 pipeline 结果展示中增加分析师反馈机制：分析师对每个 Assertion 标记"同意/不同意/需要更多证据"，系统记录这些反馈并在后续分析中调整权重。这直接对应 `PushEngine` 的规则匹配逻辑——可以根据分析师历史反馈调整推送阈值。
- **链接**: https://arxiv.org/abs/2512.13253

### 论文 3：A Design Space for Intelligent Agents in Mixed-Initiative Visual Analytics

- **标题**: A Design Space for Intelligent Agents in Mixed-Initiative Visual Analytics
- **作者**: Tobias Stähle, Matthijs Jansen op de Haar, Sophia Boyer, Rita Sevastjanova, Arpit Narechania, Mennatallah El-Assady
- **年份**: 2025
- **会议/期刊**: arXiv:2512.23372
- **核心贡献**:
  对 90 个混合主动式可视分析系统中的 207 个智能代理进行系统综述，提出六维设计空间框架：感知（Perception）、环境理解（Environmental Understanding）、行动能力（Action Capability）、通信策略（Communication Strategies）等。这是目前最全面的人-AI 协作可视分析设计框架，为设计"人机协作分析界面"提供了结构化的设计选择空间。
- **与 AEGI 的关联**:
  AEGI 的 KG 可视化（`kg_viz.py` 7 个端点）和聊天界面目前是"人问 AI 答"的单向模式。该论文的六维框架可以指导 AEGI 向混合主动式演进：AI 主动发现异常模式并高亮（感知维度）、理解分析师当前关注的实体子图（环境理解维度）、主动建议下一步探索方向（行动维度）、用自然语言+可视化双通道沟通（通信维度）。具体可在 `chat` 模块中增加 proactive suggestion 机制。
- **链接**: https://arxiv.org/abs/2512.23372

### 论文 4：The Role of Visualization in LLM-Assisted Knowledge Graph Systems

- **标题**: The Role of Visualization in LLM-Assisted Knowledge Graph Systems: Effects on User Trust, Exploration, and Workflows
- **作者**: Harry Li, Gabriel Appleby, Kenneth Alperin, Steven R Gomez, Ashley Suh
- **年份**: 2025
- **会议/期刊**: arXiv:2505.21512 (cs.LG, cs.HC)

- **核心贡献**:
  基于 LinkQ 系统（LLM 将自然语言转为结构化 KG 查询）的 14 人定性实验，设计了 5 种可视化机制（状态图、查询编辑器、实体关系表、查询结构图、交互式可视化）来帮助用户验证 LLM 输出。关键发现令人警醒：即使是 KG 专家，也倾向于过度信任 LLM 输出——可视化反而增强了这种虚假信任感（"helpful visualizations" 让用户放松了警惕）。不同经验水平的用户工作流差异显著，说明"一刀切"的界面设计行不通。
- **与 AEGI 的关联**:
  这篇论文对 AEGI 是一个重要警告。AEGI 的 KG 可视化 + LLM 聊天组合恰好是 LinkQ 的同类系统。当前 AEGI 的 `chat` 模块通过 LLM 做 KG 推理（2-hop neighbors、path discovery），如果分析师过度信任这些结果，可能导致错误判断。建议：(1) 在 KG 查询结果中显式标注 LLM 置信度和证据链完整度；(2) 对 LLM 生成的 KG 查询增加"查询审计"视图，让分析师能看到并修改底层查询逻辑；(3) 根据用户经验水平提供不同的默认界面复杂度。
- **链接**: https://arxiv.org/abs/2505.21512
- **前序工作**: A Preliminary Roadmap for LLMs as Assistants in Exploring, Analyzing, and Visualizing Knowledge Graphs (arXiv:2404.01425, 同一作者组, 2024)。该前序工作通过 20 人访谈发现：专业用户希望 LLM 通过"联合查询构建"辅助 KG 数据检索，偏好嵌入现有工作流的聊天组件，并要求"带注释的可视化 + 摘要文本"的双通道输出。

### 论文 5：Overcoming Anchoring Bias: The Potential of AI and XAI-based Decision Support

- **标题**: Overcoming Anchoring Bias: The Potential of AI and XAI-based Decision Support
- **作者**: Felix Haag, Carlo Stingl, Katrin Zerfass, Konstantin Hopf, Thorsten Staake
- **年份**: 2024
- **会议/期刊**: arXiv:2405.04972 (cs.CY, cs.AI, cs.HC)
- **核心贡献**:
  通过两个在线实验（N=390）证明 AI 和 XAI 能有效缓解锚定偏差（anchoring bias）。锚定偏差是情报分析中最常见的认知偏差之一——分析师容易被最先接触到的信息"锚定"，后续判断偏向初始信息。实验表明"AI 单独使用"和"AI + XAI 组合"都能显著减轻锚定效应，但 XAI 的额外增益在统计上不总是显著。
- **与 AEGI 的关联**:
  AEGI 的贝叶斯 ACH（Analysis of Competing Hypotheses）模块天然面临锚定偏差问题：分析师可能被第一个看到的假设锚定。建议：(1) 在假设列表展示时随机化排序或按证据强度排序，避免位置锚定；(2) 在 `hypothesis_engine` 输出中增加"反锚定提示"——当检测到分析师长时间关注单一假设时，主动推荐对立假设的证据；(3) 利用 XAI 解释每个假设的支持/反对证据来源，帮助分析师跳出锚定框架。
- **链接**: https://arxiv.org/abs/2405.04972

### 补充论文（值得关注但未精选）

| 标题 | 作者 | 年份 | 核心观点 | arXiv |
|------|------|------|----------|-------|
| AI as Cognitive Amplifier: Rethinking Human Judgment in the Age of Generative AI | Tao An | 2025 | 提出三层 AI 参与模型：被动接受→迭代协作→认知引导。基于 500+ 专业人员培训观察，论证输出质量根本取决于用户专业能力 | 2512.10961 |
| HybridQuestion: Human-AI Collaboration for Identifying High-Impact Research Questions | Keyu Zhao 等 | 2026 | 人机混合方案识别高影响力研究问题，AI 做规模化数据处理，人类做价值判断 | 2602.03849 |
| Human-AI Collaborative Inductive Thematic Analysis | Matthew Nyaaba 等 | 2026 | 在主题分析中保持"人类解释权威"，AI 作为"程序性脚手架"结构化分析流程 | 2601.11850 |
| Alleviating Choice Supportive Bias in LLM with Reasoning Dependency Generation | Nan Zhuang 等 | 2025 | 通过生成平衡推理数据来微调模型，缓解 LLM 的选择支持偏差，改善率 81-94% | 2512.03082 |

## 开源项目（精选 3 个）

### 项目 1：ArkhamMirror

- **名称**: ArkhamMirror
- **GitHub**: https://github.com/mantisfury/ArkhamMirror
- **Star 数**: 362
- **核心功能**:
  本地优先的 AI 文档情报分析平台，专为调查性研究设计。架构采用"Voltron"模式——不可变核心框架（ArkhamFrame，17 个服务）+ 26 个可插拔模块（Shard）。核心分析能力包括：竞争假设分析（ACH）含预验尸和魔鬼代言人模式、矛盾检测（跨文档严重性评分）、模式识别（行为/时序/相关性）、异常检测、可信度评估（MOM/POP/MOSES/EVE 框架）、溯源追踪。可视化支持 10+ 种图布局（力导向、层次、桑基、因果、论证、链接分析、时序等）。技术栈：Python 3.10+ / FastAPI / PostgreSQL+pgvector / React 18 / TypeScript。

- **集成可行性**: 高。技术栈与 AEGI 高度重合（FastAPI + PostgreSQL + React）。模块化架构意味着可以单独借鉴特定 Shard 的设计，而非整体迁移。
- **集成建议**:
  1. **ACH 模块借鉴**：ArkhamMirror 的 ACH 实现包含预验尸（premortem）和魔鬼代言人（devil's advocate）模式，这是 AEGI 贝叶斯 ACH 缺少的交互模式。建议在 AEGI 的 `hypothesis_engine` 中增加"反向论证"功能——系统自动为每个假设生成反面论据。
  2. **可信度评估框架**：MOM/POP/MOSES/EVE 是成熟的情报分析可信度评估清单，可以集成到 AEGI 的 `source_credibility` 评分逻辑中，从当前的规则化域名信誉评分升级为多维度结构化评估。
  3. **可视化布局**：AEGI 当前 KG 可视化主要是力导向图，ArkhamMirror 的因果图、论证图、链接分析图布局可以直接参考，特别是"论证图"（argumentative layout）与 AEGI 的证据链路径（Judgment → Assertion → SourceClaim → Evidence）天然契合。

### 项目 2：VisPile

- **名称**: VisPile
- **GitHub**: https://github.com/AdamCoscia/VisPile
- **Star 数**: 6（学术项目，HICSS 2026 论文配套）
- **核心功能**:
  LLM + 知识图谱驱动的文档可视分析系统，专为情报分析师的 sensemaking 流程设计。核心交互模式是"文档堆叠"（piling）——分析师将文档分组成堆，对每个堆执行摘要、关系映射等分析任务，然后验证 LLM 和 KG 生成的证据。技术栈：Vue 3 前端 + Python Flask 后端 + OpenAI API。
- **集成可行性**: 中。Star 数低但学术价值高（HICSS 2026 发表）。前端用 Vue 3 而 AEGI 未指定前端框架，后端用 Flask 而非 FastAPI，需要适配。核心价值在于交互设计理念而非代码复用。
- **集成建议**:
  1. **"文档堆叠"交互模式**：这是一个非常适合情报分析的交互隐喻。AEGI 的 OSINT 收集模块（`osint_collect`）产生大量文档，当前缺乏让分析师手动组织和分组的界面。可以在 AEGI 前端引入类似的"证据堆叠"视图，让分析师将相关 SourceClaim 拖拽分组。
  2. **LLM 证据验证机制**：VisPile 强调"验证 LLM 生成的证据"，这与 AEGI 的 Evidence-first 红线高度一致。可以借鉴其验证 UI 设计，在 AEGI 的报告展示中为每个 AI 生成的断言提供"查看证据链"和"质疑此断言"的交互入口。

### 项目 3：IntellyWeave

- **名称**: IntellyWeave
- **GitHub**: https://github.com/vericle/intellyweave
- **Star 数**: 44
- **核心功能**:
  AI 驱动的 OSINT 情报分析平台，采用多 Agent 架构（基于 Weaviate Elysia 框架）。核心 Agent 包括：Quartermaster（信息地图绘制、档案馆识别）和 Case Officer（假设检验、证据综合）。六阶段自动化管道：实体提取 → 关系映射 → 地理空间分析 → 网络分析 → 模式检测 → 综合摘要。支持 GLiNER 零样本实体识别（7 种实体类型）、Mapbox GL 3D 地理可视化、vis-network 力导向图。技术栈：Python 3.12 / FastAPI / Weaviate / DSPy / LiteLLM / Next.js 15 / React 18。

- **集成可行性**: 中高。技术栈非常接近 AEGI（FastAPI + LiteLLM + React），Python 3.12 版本一致。多 Agent 架构和六阶段管道与 AEGI 的 pipeline 设计理念相似。主要差异在向量库（Weaviate vs Qdrant）和前端框架（Next.js vs AEGI 未定）。
- **集成建议**:
  1. **多 Agent 角色设计**：Quartermaster + Case Officer 的角色分工值得借鉴。AEGI 当前的 pipeline 是线性阶段式的，可以考虑在 `pipeline_orchestrator` 中引入角色化 Agent——"信息收集 Agent"负责 OSINT 和 GDELT 数据采集，"分析 Agent"负责假设评估和因果推断，"质疑 Agent"负责反向论证和偏差检测。
  2. **GLiNER 零样本实体识别**：AEGI 当前的实体提取依赖 LLM，GLiNER 作为轻量级零样本 NER 模型可以作为补充——在 LLM 调用前先用 GLiNER 做快速实体预提取，减少 LLM token 消耗。
  3. **地理空间分析**：AEGI 目前缺乏地理可视化能力，IntellyWeave 的 Mapbox GL 集成可以作为参考，特别是对 GDELT 事件数据的地理分布展示。

## 关键发现与建议

### 发现 1：信任校准是人机协作的核心瓶颈

Ma et al. (2023) 和 Li et al. (2025) 的研究从两个方向揭示了同一个问题：

- Ma 发现只展示 AI 置信度不够，必须同时建模人类的判断能力才能实现恰当信任
- Li 发现即使提供了可视化验证工具，用户（包括专家）仍然倾向于过度信任 LLM 输出

**对 AEGI 的启示**：AEGI 的证据链架构（Judgment → Assertion → SourceClaim → Evidence → Artifact）是天然的信任校准基础设施。建议在每个 Assertion 展示时增加三个维度的信任信号：
1. **证据完整度**：该断言的证据链是否完整到 Artifact 层
2. **AI 置信度**：LLM 生成该断言时的 logprob 或自评分数
3. **历史准确率**：该类型断言在历史反馈中的准确率

### 发现 2：反馈闭环决定协同效果

Berger et al. (2025) 的 74 项研究元分析给出了明确结论：**反馈 + 解释 = 正向协同，只有解释没有反馈 = 负向协同**。这意味着仅仅做好 XAI（可解释性）是不够的，必须让分析师能够给出反馈并看到反馈的效果。

**对 AEGI 的启示**：当前 AEGI 的 `PushEngine` 和 `Subscription` 机制已经有了事件推送能力，但缺少反馈回路。建议增加：
1. **Assertion 反馈 API**：分析师对每个 Assertion 标记 agree/disagree/need_more_evidence
2. **反馈驱动的权重调整**：在 `hypothesis_engine` 中根据历史反馈调整证据权重
3. **反馈统计仪表盘**：展示分析师与 AI 的一致率、分歧点分布、随时间的校准趋势

### 发现 3：混合主动式交互优于问答式交互

Stähle et al. (2025) 的六维设计空间框架表明，最有效的人-AI 协作不是"人问 AI 答"，而是双方都能主动发起交互。AI 应该能主动感知分析师的关注点、理解当前分析上下文、主动建议下一步行动。

**对 AEGI 的启示**：AEGI 当前的交互模式主要是：
- 分析师发起 chat → AI 回答
- 分析师触发 pipeline → AI 执行并推送结果
- 分析师订阅事件 → AI 推送匹配事件

建议演进为混合主动式：
1. **上下文感知推荐**：当分析师在 KG 可视化中浏览某个实体时，AI 主动推荐相关的未读 SourceClaim 和待验证假设
2. **分析缺口检测**：AI 定期扫描当前活跃假设的证据覆盖度，主动提示"假设 X 缺少 Y 类型的证据"
3. **偏差预警**：当检测到分析师长时间只关注支持某一假设的证据时，主动推送反面证据

### 发现 4：认知偏差缓解需要系统性设计

Haag et al. (2024) 证明 AI+XAI 能缓解锚定偏差，但这只是众多认知偏差中的一种。情报分析中常见的偏差还包括：确认偏差、可得性偏差、群体思维、镜像偏差等。

**对 AEGI 的建议**：构建系统性的"认知偏差防护层"：
1. **假设排序随机化**：避免位置锚定
2. **证据多样性检查**：当某假设的支持证据全部来自同一来源类型时发出警告（对抗确认偏差）
3. **反向搜索建议**：在 OSINT 收集时，自动建议搜索与当前假设相反的关键词（对抗确认偏差）
4. **时间衰减提醒**：对长时间未更新的判断标记"可能过时"（对抗锚定偏差）

### 优先级建议

| 优先级 | 建议 | 工作量 | 依赖 |
|--------|------|--------|------|
| P0 | Assertion 反馈 API + 反馈存储 | 1 周 | 新增 AssertionFeedback 模型 |
| P0 | 证据链完整度标注（每个 Assertion 展示证据深度） | 3 天 | 现有证据链架构 |
| P1 | 假设排序随机化 + 反向证据推荐 | 1 周 | hypothesis_engine |
| P1 | KG 查询审计视图（展示 LLM 生成的查询逻辑） | 1 周 | kg_viz + chat |
| P2 | 混合主动式推荐（上下文感知 + 缺口检测） | 2-3 周 | PushEngine + EventBus |
| P2 | 认知偏差防护层（证据多样性检查 + 反向搜索） | 2 周 | osint_collect + hypothesis_engine |
| P3 | 双向置信度展示（AI 置信度 + 分析师历史准确率） | 3-4 周 | 需要积累反馈数据 |
| P3 | ArkhamMirror 式论证图布局 | 2 周 | kg_viz 前端 |
