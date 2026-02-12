<!-- Author: msq -->

# ADR-002: 质量优先的分析能力演进路线

> 状态：草案
> 日期：2026-02-12
> 决策者：msq

## 背景

当前代码已完成 6 个实现阶段（基础设施 → 报告 → KG增强 → OSINT采集 → 流式传输 → 事件驱动），
加上近期的本体升级（RelationFact/实体版本化/反馈服务）和 InvestigationAgent（自动调研循环）。

原规划的后续路线是：
- P3：交叉关联引擎 + 分析记忆（模式学习）
- P4：概率校准 + 多Agent辩论 + DISARM框架 + 时序因果

经代码审计和 2025-2026 最新研究对照，发现原路线存在三个问题：

1. **底座质量未解决就加功能**：pipeline 的 LLM 调用全部串行、无一致性校验、无校准层
2. **冷启动依赖过重**：交叉关联和分析记忆都需要大量标注数据才能产生价值
3. **优先级错位**：校准层被放在 P4（最后），但它对所有概率输出的可信度是基础性的

本 ADR 提出调整后的路线：先修底座质量，再加分析能力。

长期演进方向：AEGI 从"辅助分析师的工具"逐步升级为"能超越人类分析师团队的策略参谋实体"，
人类专家的角色从使用者演进为认知模型的校准者和行动边界的定义者（详见 P-next-6.3）。

---

## 现状验证

### 已实现且验证正确的部分

| 模块 | 关键文件 | 验证结论 |
|------|---------|---------|
| graphrag fuzzy_match 丢弃未匹配关系 | graphrag_pipeline.py:208-217 | `continue` 跳过，确认存在 |
| 本体 domain/range 约束 | ontology_versioning.py:785-830 | 校验完整，graphrag 调用链已接入 |
| RelationFact 证据溯源+时效+冲突 | relation_fact.py, relation_fact_service.py | 三个维度字段齐全，冲突自动检测 |
| 实体 merge/split 可回滚 | entity_identity_service.py:133-148 | rollback 改状态为 rolled_back |
| InvestigationAgent 自动调研循环 | investigation_agent.py | LLM生成query→SearXNG+GDELT搜索→证据链入库→贝叶斯更新→多轮迭代 |
| 贝叶斯 ACH 事件驱动更新 | bayesian_ach.py + event_bus.py | claim.extracted→likelihood评估→Bayes更新→hypothesis.updated |
| 推送通知 | push_engine.py | 规则匹配+语义匹配+节流+投递，链路完整 |

### 已实现但与原规划能力边界有差距的部分

| 模块 | 原规划描述 | 实际状态 |
|------|-----------|---------|
| CrossCorrelationEngine | "发现人类注意不到的组合信号" | 引擎已存在，但显著性评分主要是启发式公式，缺 NPMI/G-test/Bayesian surprise 等统计显著性层 |
| 分析记忆系统 | "系统越用越准，历史模式匹配" | 记忆检索已存在，但更偏“检索增强”，尚未形成系统化的在线学习/策略自优化闭环 |

### pipeline 底座问题（代码审计发现）

1. **LLM 调用串行深度过高**：当前主链路可近似为 `1 + N*(1+3)` 的等待深度
   （生成 + 每假设分析 + 每假设三角色对抗），并行化不足。典型 pipeline 延迟 30-60s。

2. **LLM 输出无一致性校验**：同一条 assertion 对互斥假设 A 和 B 都判断为 support，系统不会发现这个逻辑矛盾。

3. **概率输出无校准**：LLM 说"70% 可能"时实际发生率可能只有 50%。所有后验概率、置信度评分都是未校准的原始值。

4. **grounding 未强制执行**：grounding_gate 计算了 grounding_level，但服务层可以忽略它，高置信度输出不要求有证据支撑。

---

## 研究依据

以下结论来自 2025-2026 年公开论文和开源项目调研：

### 直接影响架构决策的发现

| 来源 | 发现 | 对 AEGI 的影响 |
|------|------|---------------|
| EvolveCast (arXiv:2509.23936) | LLM 收到新证据时不会正确更新信念，更新"不一致或过度保守" | AEGI 的事件驱动显式更新（EventBus + Bayes）是正确架构，但 LLM 的 likelihood 判断是薄弱环节 |
| 采样置信度基准 (arXiv:2602.00279) | 跨 20 个 LLM 测试：跑 N 次推理数频率 > 问 LLM "你多有信心" | AEGI 应对关键判断用采样置信度替代单次推理 |
| AIA Forecaster (arXiv:2511.07678) | 首个匹配人类超级预测者的系统：agentic search + supervisor + 统计校准 | 验证了 AEGI 的 InvestigationAgent 方向，但缺校准层 |
| ACH-Grounding (GitHub, 2025.12) | "LLM 在组合复杂问题上的幻觉不可避免"，LLM 只负责生成，矩阵分析用确定性代码 | AEGI 已遵循此原则（DoWhy/DS融合），方向正确 |
| TruthTensor (arXiv:2601.13545) | 准确率相似的模型校准度可能差异巨大 | 单看准确率不够，必须独立测量校准度 |
| PRISM/Shapley (arXiv:2601.09151) | 用 Shapley 值分解预测为每个输入因素的边际贡献 | 可将 assertion 置信度分解为每个 source 的贡献，比单一数字更有用 |
| AutoPrunedRetriever (2026.02) | 持久化最小推理子图，token 消耗降低 100 倍 | graphrag_pipeline 应实现子图剪枝 |
| Tool-MAD (2026.01) | 给不同 agent 不同工具访问权限比相同工具更有效 | 辩论机制中正方/反方应有不同证据访问权限 |

### 竞品与生态位

| 项目 | 与 AEGI 重叠 | 缺什么 |
|------|-------------|--------|
| OpenCTI (8.2k stars) | KG 情报平台，STIX2，连接器生态 | 只做网络威胁，无 LLM 分析，无预测 |
| LightRAG (28.3k stars) | KG+向量混合检索，Neo4j+Qdrant | 无情报领域，无证据链 |
| Cognee (12.3k stars) | KG 记忆，Neo4j | 无 OSINT，无结构化分析 |
| SpiderFoot (16.6k stars) | OSINT 自动化 | 无 LLM，无 KG，无分析 |
| ACH-Grounding (1 star) | ACH + LLM + RAG | 玩具项目，无 KG，无事件驱动 |

结论：AEGI 在地缘政治情报分析领域没有直接开源竞品。证据链 + KG + 事件驱动 + LLM 分析的组合是独特的。

---

## 决策：调整后的演进路线

### 原路线 vs 调整后路线

```
原路线（功能驱动）：
  P1 本体升级 → P2 调研Agent → P3 交叉关联+分析记忆 → P4 校准+辩论+DISARM
                                    ↑ 冷启动严重            ↑ 太晚

调整后路线（质量驱动）：
  已完成：本体升级 + 调研Agent
  → P-next-1：底座修复 + 成本控制
  → P-next-2：校准 + 检索 + 关联 + 因果发现
  → P-next-3：辩论 + DISARM + Shapley + 元评估
  → P-next-4：蒸馏 + 数据源扩展
```

核心原则：**分析准确率从 60% 提到 80%，比准确率 60% 但多三个新功能更有价值。**


### P-next-1：底座修复（工程量小，收益大）

目标：不加新功能，让现有 pipeline 输出更准、更快。

#### 1.1 LLM 调用并行化

现状（按调用深度）：
- `generate_hypotheses`：1 次 LLM 调用生成全部假设（不可并行，也不需要并行）
- `analyze_hypothesis_llm`：每个假设 1 次 LLM（假设间可并行）
- `aevaluate_adversarial`：每个假设 3 次 LLM（defense/prosecution/judge）
  - defense 与 prosecution 可并行
  - judge 依赖 defense/prosecution 结果，需串行
- `assess_evidence`（贝叶斯）：一次调用评估所有假设；多条 claim 更新必须串行（后验依赖前序更新）

改动：采用三层并行结构，而不是“5×2”简化模型。

```python
# 目标串行深度（示意）：
# 1) generate_hypotheses（1 层）
# 2) analyze_hypothesis_llm 对 N 个假设并行（1 层）
# 3) aevaluate_adversarial 对 N 个假设并行（1 层，内部 defense/prosecution 并行 + judge 串行）

hypotheses = await generate_hypotheses(...)
analyze_results = await asyncio.gather(
    *[analyze_hypothesis_llm(h, assertions, llm) for h in hypotheses]
)
adversarial_results = await asyncio.gather(
    *[aevaluate_adversarial_parallel(h, assertions, source_claims, llm) for h in analyze_results]
)
```

预期效果：从约 `1 + N*(1+3)` 的串行等待，降到约 `3` 层等待深度
（`generate -> analyze并行 -> adversarial并行`）。对 N>=3 的 case，延迟改善通常优于“60%”。

涉及文件：`pipeline_orchestrator.py`, `stages/builtin.py`, `hypothesis_engine.py`,
`hypothesis_adversarial.py`

#### 1.2 采样置信度（关键判断）

现状：ACH 的 support/contradict/irrelevant 判断跑一次，取单次结果。

改动：对 Tier 1 判断（ACH likelihood 评估）跑 3 次采样，但按“假设粒度”聚合，
不是整批一次投票。

```python
async def sampled_assess_evidence(prompt, n=3):
    runs = await asyncio.gather(
        *[llm.invoke_structured(prompt, EvidenceAssessmentRequest) for _ in range(n)]
    )
    grouped = group_by_hypothesis_uid(runs)  # {hyp_uid: [judgment, judgment, judgment]}
    merged = {}
    for hyp_uid, js in grouped.items():
        merged[hyp_uid] = {
            "relation": majority_vote([j.relation for j in js]),
            "strength": median([j.strength for j in js]),
            "agreement_rate": vote_ratio(js),  # 例如 2/3, 3/3
        }
    return merged
```

成本：LLM 调用量 ×3，但只对 ACH 判断做（约 25 次/pipeline → 75 次）。
结合 1.1 的并行化，总延迟增加有限。

新增要求：将 `agreement_rate` 持久化到 `EvidenceAssessment`，作为 P-next-3
`meta-confidence` 的输入信号之一（低一致率 = 高不确定）。

涉及文件：`bayesian_ach.py`（`assess_evidence` 采样聚合），
`db/models/evidence_assessment.py`（新增 `agreement_rate` 字段）

#### 1.3 ACH 一致性校验

现状：同一条 assertion 对互斥假设都判断为 support，系统不检测。

前提：P-next-1 默认采用 ACH 标准假设——同一组假设互斥（single-winner）。
因此不需要先引入 `mutually_exclusive_with` 字段。
若未来需要“非互斥假设共存”，再扩展 schema。

改动：ACH 矩阵填完后，跑一轮规则校验：

- 互斥假设对同一 assertion 不能同时 strong_support
- 同一 assertion 的 likelihood 之和应在合理范围内
- 违反规则的判断标记为 `needs_review`，不自动丢弃

纯规则，不需要额外 LLM 调用。

涉及文件：`bayesian_ach.py`（新增 `validate_consistency()` 方法）

#### 1.4 grounding 强制执行

现状：`grounding_gate()` 计算了 level 但不阻断。

改动：在 pipeline 内部判断层强制执行 grounding。
当 `ACHResult.grounding_level == HYPOTHESIS` 且 `ACHResult.confidence > 0.7` 时，
自动降级为 `0.5` 并标记 `grounding_capped: true`。

边界约定：
- 该规则作用于 `ACHResult.confidence`（分析链路内部信号）
- `QualityReportV1.confidence_score` 继续作为输出层独立质量分数，不直接覆盖

涉及文件：`hypothesis_engine.py`, `contracts/llm_governance.py`

#### 1.5 LLM 调用统一抽象层（LLMCallManager）

现状：LLM 调用分散在各 service，各自处理并行、重试、预算、日志，重复且容易不一致。

改动：新增统一抽象层 `LLMCallManager`（或等价扩展现有 `LLMClient`），集中处理横切逻辑：

- 并行调度（`gather`）
- 采样调用（N 次调用 + 投票聚合 + `agreement_rate` 计算）
- 调用前预算检查
- 调用后判断日志记录（输入/输出/推理链元数据）
- 失败重试与降级策略（统一）

各业务模块不直接写采样/预算/日志细节，改为调用统一接口：
`invoke_with_sampling(...)`、`invoke_with_budget(...)`。

涉及文件：新增 `infra/llm_call_manager.py`，修改各调用点（`hypothesis_engine.py`,
`hypothesis_adversarial.py`, `bayesian_ach.py`, `pipeline_orchestrator.py`）

#### 1.6 全局 token/cost budget 管理器

现状：每个模块各自控制 LLM 调用量，无全局视角。InvestigationAgent 每次触发 10-15 次 LLM 调用，
加上采样置信度（×3）、辩论（×2），一个 pipeline 可能 50-100 次 LLM 调用，成本不可控。

改动：新增 `TokenBudgetManager`，pipeline 级别的 token/cost 预算管理：

- pipeline 启动时分配 token 预算（可配置，默认 50k tokens/run）
- 每次 LLM 调用前检查剩余预算，不足时降级（跳过采样、跳过辩论、用缓存结果）
- 记录每个 stage 的实际消耗，用于后续优化
- 提供 `GET /admin/token-usage` 查看消耗分布

降级策略（预算不足时按优先级裁剪）：
1. 先砍采样（3 次→1 次）
2. 再砍辩论（跳过）
3. 再砍 narrative_build（跳过）
4. hypothesis_analyze 和 adversarial_evaluate 不砍（核心路径）

涉及文件：新增 `services/token_budget.py`，修改 `pipeline_orchestrator.py`（注入 budget），
修改各 stage（调用前检查 budget）

#### P-next-1 验收标准

- [ ] 并行化改造完成：串行深度从 `1 + N*(1+3)` 降为约 3 层
- [ ] ACH 采样按“假设粒度”投票，`agreement_rate` 持久化可查询
- [ ] ACH 矩阵一致性校验，逻辑矛盾检出率 > 90%
- [ ] `ACHResult.confidence` 的 grounding 强制执行上线
- [ ] `LLMCallManager` 上线，采样/并行/预算/日志逻辑收敛到统一接口
- [ ] 全局 token budget 管理器上线，pipeline 消耗可观测、可降级


### P-next-2：校准层 + 历史检索 + 交叉关联 + 因果发现

目标：让概率输出可信，让历史经验可用，让多信号关联可发现，让因果关系有统计支撑。

#### 2.1 概率校准层

问题：LLM 输出的概率未经校准，"70% 可能"的实际发生率未知。

方案：

a) feedback_service 增加 `outcome` 字段（实际发生/未发生/未知），分析师在事后标注。

b) 自动训练触发：
- 全局样本达到 100+ 时首次训练
- 此后每新增 10 条已解决样本或每周定时重训（取先到条件）

c) 分场景训练策略：
- `scenario_type` 样本数 >= 30：训练该场景专属 Platt 参数
- `scenario_type` 样本数 < 30：回退到全局参数

d) Platt scaling（logistic regression）训练函数：
   `calibrated_prob = sigmoid(a * raw_prob + b)`

e) 校准参数持久化到 `calibration_params` 表，pipeline 启动时加载到内存缓存。

f) 校准函数作为 pipeline 后处理步骤，对所有概率输出做变换，并持续监控
ECE（Expected Calibration Error）。

冷启动期：校准函数训练前，概率输出旁标注"未校准"。诚实比好看重要。

涉及文件：`feedback_service.py`（加 outcome 字段），新增 `services/calibration.py`，
新增 `db/models/calibration_params.py`

#### 2.2 RAG 式历史检索（增强现有分析记忆）

问题：现有分析记忆更偏“检索增强”，缺少稳定的历史案例召回策略与入口规范。

方案：先做可解释、可冷启动的历史检索增强，不先引入重型在线学习。

- 每次 pipeline 完成后，将分析摘要（假设、判断、关键 assertion）存入 Qdrant 专用 collection `analysis_archive`
- 下次 pipeline 运行时，用当前 case 的关键实体+事件类型做语义检索，召回相似历史分析
- 召回结果作为 context 注入 hypothesis_engine，提示"历史上类似场景的分析结论"
- 分析师看到的是"上次遇到类似模式时结论是 X"，自行判断是否适用

优势：
- 第一天就能用（只要有一次历史分析）
- 不需要标注 outcome
- 不需要统计显著性
- 比"80% 导致军事冲突"更诚实——展示历史案例，让人判断

涉及文件：新增 `services/analysis_archive.py`，修改 `pipeline_orchestrator.py`（完成后存档），
修改 `hypothesis_engine.py`（生成前检索历史）

#### 2.3 NPMI 增强的交叉关联（重构现有引擎）

问题：现有 `cross_correlation.py` 已有完整引擎（实体共现、时空邻近、语义模式），
但显著性分数部分仍是启发式硬编码，统计解释性不足。

方案：保留现有引擎架构，用 NPMI / surprise score 重构显著性计算，而不是新建平行引擎。

流程：
1. GDELT monitor 持续产生事件流（已有）
2. 对 `_entity_cooccurrence`：用 NPMI + G-test 替换当前启发式 `significance` 公式
3. 对 `_spatiotemporal_proximity`：用 Bayesian surprise score 替换纯密度阈值
4. `_semantic_pattern` 保持不变（语义相似层面 NPMI 不适用）
5. 仅对统计显著模式触发 LLM 深度解释（本体约束输出）
6. 显著模式写入 EventBus，触发推送

NPMI（Normalized Pointwise Mutual Information）初筛的价值：
- 纯密度阈值只能发现"事件多了"，NPMI 能发现"这两类事件同时出现得异常频繁"
- 例：某地区"外交召回"和"黄金增持"单独看都不算异常，但 NPMI 显著偏高说明共现超出预期
- 用 Bayesian surprise score 作为补充：`S = -log2(P(observed | expected_rate))`，Poisson 模型
- 过滤单事件类型出现 < 10 次的窗口（NPMI 对稀有事件不可靠）

成本控制：只对 NPMI 异常的事件对触发 LLM 分析，不是每个窗口都跑。
正常情况下每天触发 0-5 次，成本可控。

涉及文件：修改 `services/cross_correlation.py`（显著性计算重构），
修改 `gdelt_monitor.py`（窗口聚合）

#### 2.4 时序因果发现（tigramite PCMCI）

从 GDELT 时序数据中自动发现滞后因果关系，与交叉关联互补——
交叉关联发现"这些事件同时出现了"，因果发现回答"它们之间有没有因果关系"。

实现要点：
- 聚合为周级计数（降噪 + 满足采样要求）
- 限制 10-15 个变量（CAMEO root code + goldstein + tone）
- 用 `RobustParCorr` 对 log1p 变换后的计数做检验
- `tau_max` = 4-8 周（地缘政治动态的合理滞后范围）
- 非平稳性处理：差分预处理或 RPCMCI（regime-dependent）
- **定位为假设生成工具，不是因果确认工具**

GDELT → PCMCI 预处理管道（新增明确设计）：
1. 事件去重：同一事件多媒体转载去重
2. CAMEO 聚合：细粒度 code 映射到 root code
3. 地理过滤：按 case 区域或主题子集构建时序
4. 缺失值处理：周级缺失填 0，并记录稀疏度
5. 平稳性处理：先做非平稳性检验，再差分或切换到 RPCMCI

输入/输出格式（示意）：
```json
{
  "case_uid": "xxx",
  "region": "MENA",
  "weekly_series": [
    {"week": "2025-01-06", "cameo_root_14": 12, "cameo_root_19": 3, "goldstein_mean": -2.1, "tone_mean": -4.8}
  ]
}
```

与贝叶斯 ACH 的集成：
- PCMCI 发现的边作为 DoWhy DAG 的初始化输入（替代手动指定）
- 有统计因果关系的证据-假设对，直接用统计置信度作为 likelihood
- 无统计因果关系的 fallback 到 LLM 判断
- 系统跑得越久，因果图越完善，LLM fallback 比例越低

注意事项：
- GDELT 测量媒体报道量，不是事实。媒体注意力混淆无法完全消除
- ParCorr 至少需要 200+ 时间步（周级 = 4 年数据），短期案例用不上
- 没有人发表过 PCMCI 直接应用于 GDELT 的论文，无现成经验

涉及文件：新增 `services/timeseries_preprocess.py`, `services/timeseries_causal.py`，
修改 `bayesian_ach.py`（likelihood 查因果图优先）

#### P-next-2 验收标准

- [ ] 校准层上线，ECE < 0.15（100+ 样本后）
- [ ] 未校准概率输出标注"未校准"
- [ ] 校准训练自动触发（100+ 首训，增量/定时重训）
- [ ] 校准参数持久化（`calibration_params`）并在 pipeline 启动时自动加载
- [ ] 历史分析检索可用，hypothesis_engine 生成时引用历史案例
- [ ] NPMI 异常检测上线，事件对共现显著性可量化
- [ ] 交叉关联在 NPMI 异常时触发 LLM 分析，产出可解释的模式报告
- [ ] tigramite PCMCI 可运行，发现的因果边可注入 DoWhy DAG


### P-next-3：辩论 + DISARM + Shapley 分解 + 元评估

目标：对高争议断言增加对抗验证，对信息操作增加分类检测，对置信度增加可解释分解，对系统能力增加自我评估。

#### 3.1 轻量辩论（替代全量多 Agent）

问题：原规划的 D2D 框架每条 claim 3-5 次 LLM 调用，成本过高。

替代方案：只对高争议 assertion 做 2-agent 辩论。

触发条件：DS 融合后 `belief > 0.8 AND conflict_degree > 0.3`（高置信但有冲突）。
典型 pipeline 中满足条件的 assertion 约 5-15%。

触发位置（明确约束）：
- DS 融合发生在 `assertion_fuse` 阶段
- 新增独立 `assertion_debate` stage，紧跟 `assertion_fuse`，专门处理满足触发条件的 assertion
- 不把辩论逻辑塞回 `assertion_fuse`，避免单阶段职责膨胀
- 需要同步更新 `STAGE_ORDER` 与 playbook 配置

辩论设计（参考 Tool-MAD）：
- 正方 agent：只能访问支持该 assertion 的 SourceClaim
- 反方 agent：只能访问反对该 assertion 的 SourceClaim
- 各自输出论证链（3-5 步），裁判规则（非 LLM）比较论证强度
- 辩论结果更新 assertion 的 confidence 和 conflict_resolution

成本：每个争议 assertion 2 次 LLM 调用，典型 pipeline 增加 2-6 次调用。
相比全量辩论（每条 claim × 5 次）降低 90%+ 成本。

涉及文件：新增 `services/adversarial_debate.py`, `services/stages/assertion_debate.py`，
修改 `assertion_fuser.py`（输出触发候选），`pipeline_orchestrator.py` 与 `deploy/playbooks.yaml`
（插入 `assertion_debate`）

#### 3.2 DISARM 信息操作分类

DISARM 是 MITRE ATT&CK 风格的信息操作分类体系，将信息操作分解为战术/技术/程序。

实现方式：
- 将 DISARM 框架的战术/技术编码为本体层的关系类型（加法，不改现有本体）
- coordination_detector 检测到协同行为时，用规则匹配 DISARM 战术标签
- 标签写入 assertion 的 metadata，分析师可按战术类型过滤

这是分类标签体系，不需要 LLM，实现成本低。

涉及文件：修改 `coordination_detector.py`（加 DISARM 标签），
新增 `infra/disarm_taxonomy.py`（战术/技术编码表）

#### 3.3 Shapley 置信度分解

问题：assertion 的置信度是一个数字（如 0.75），分析师无法判断这个数字靠不靠谱。

方案（参考 PRISM, arXiv:2601.09151）：
- 对每个 assertion，计算每个 SourceClaim 对最终置信度的边际贡献
- 采用真正的 Shapley 值定义（遍历子集），不是 leave-one-out 近似
- 输出示例："置信度 0.75 = 路透社 +0.30 + GDELT +0.20 + 某博客 +0.05 + 先验 +0.20"

分析师看到的不是黑箱数字，而是每个来源的贡献权重。
如果某个低可信度来源贡献了大部分置信度，一眼就能发现问题。

复杂度策略：
- 常见 3-8 source：精确 Shapley（最多 2^8=256 个子集，可接受）
- source > 8：降级到采样近似（Monte Carlo Shapley）

涉及文件：修改 `ds_fusion.py`（加 Shapley 分解），修改 `contracts/schemas.py`（AssertionV1 加 source_contributions 字段）

#### 3.4 场景级自信度元评估（meta-confidence）

问题：校准层解决了"概率数字准不准"，但没解决"系统在什么场景下靠谱"。
系统分析经济制裁影响时准确率 80%，分析政治意图时准确率 50%——分析师需要知道这个差异。

方案：

a) Case 模型加 `scenario_type` 字段（基于 CAMEO root + actor 数量 + 时序趋势的规则分类，
   5-10 个类型：bilateral_conflict、multilateral_negotiation、economic_sanction 等）

b) feedback_service 加 `outcome` 字段（实际发生/未发生/未知），分析师事后标注

c) 按 scenario_type 统计历史准确率：
   `accuracy[scenario] = count(correct) / count(resolved)`

d) pipeline 输出附带 meta_confidence：
   `meta_confidence = base_confidence × scenario_accuracy_factor`

e) meta_confidence 低于阈值时自动标记 `needs_expert_review`

依赖 P-next-2 的校准层和历史检索。与 P-next-1 的采样置信度天然兼容——
采样一致率本身就是 meta-confidence 的一个信号（一致率低 = 系统不确定）。

涉及文件：修改 `confidence_scorer.py`，修改 `feedback_service.py`，
新增 `services/meta_confidence.py`

#### P-next-3 验收标准

- [ ] 高争议 assertion 自动触发辩论，辩论结果更新置信度
- [ ] `assertion_debate` stage 上线并接入 `STAGE_ORDER` / playbook
- [ ] 协同行为检测结果附带 DISARM 战术标签
- [ ] assertion 置信度可分解为每个 source 的边际贡献
- [ ] 分析师可在 API 响应中看到 source_contributions 字段
- [ ] 系统自信度评估可用，低自信场景自动标记 needs_expert_review
- [ ] 场景级历史准确率可查询（GET /admin/accuracy-by-scenario）

---

## 与 single-source-plan.md 的关系

本 ADR 不修改 single-source-plan.md 的 P1/P2/P3 范围定义。
本 ADR 的 P-next-1/2/3 是 single-source-plan P2（ACH + 叙事 + KG）和 P3（预测 + 元认知）
的实现层细化，聚焦于"怎么做"而非"做什么"。

对应关系：
- P-next-1（底座修复+成本控制）→ single-source-plan P2 的质量保障前置条件
- P-next-2（校准+检索+关联+因果）→ single-source-plan P3 的元认知 + 预测基础
- P-next-3（辩论+DISARM+Shapley+元评估）→ single-source-plan P3 的高级推理能力
- P-next-4（蒸馏+数据源）→ 超出 single-source-plan 范围，属于长期演进

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 采样置信度 3 次投票一致率低 | 中 | 说明 LLM 判断本身不稳定，需要更强模型或更好 prompt | 记录一致率指标，低于 60% 时降级为单次+标记"低置信" |
| 校准样本积累慢 | 高 | 校准层长期处于"未校准"状态 | 接受现实，"未校准"标注本身就是价值——诚实比好看重要 |
| LLM 交叉关联产生幻觉关联 | 中 | 假阳性推送干扰分析师 | 本体约束 + NPMI 初筛 + 人工确认门槛 |
| 精确 Shapley 分解计算量随 source 数指数增长 | 中 | 典型 assertion 3-8 个 source 仍可接受，但长尾高 source 会放大计算量 | 3-8 个 source 用精确 2^n；>8 切换 Monte Carlo 近似 |
| PCMCI 在 GDELT 上发现虚假因果 | 高 | 误导分析 | 严格 p-value 门槛 + 定位为假设生成而非确认 + ACLED 交叉验证 |
| 红队测试覆盖不足 | 中 | 对抗性场景遗漏 | 每个 Phase 新增对应对抗场景，持续扩展 |
| trust_level 过早升级 | 中 | 分析师过度依赖系统 | 只允许手动升级，系统只建议不自动执行 |
| 工作流定义与实际使用偏差 | 高 | API 设计不匹配真实需求 | 先定义再实现，上线后根据使用数据迭代 |

---

## 远期演进：突破 LLM 天花板（P-next-4）

P-next-1/2/3 都是在"让 LLM 更准"这条路上优化。这条路有天花板——LLM 是语言模型，不是推理引擎。
P-next-4 突破天花板：让系统逐步减少对 LLM 的依赖，同时扩展数据源覆盖面。

### 4.1 结构化知识蒸馏

**目标**：用 LLM 判断训练轻量分类器，高频场景不再调用 LLM。

**现状**：
- AEGI 每次 pipeline 跑 20-80 次 LLM 调用
- 主要判断类型：ACH support/contradict/irrelevant、冲突检测、证据评估
- 10 case/天 = 200-800 判断/天，30 天积累 6000-24000 条，足够训练

**文献强力支持**：
- Distilling Step-by-Step（Hsieh et al. 2023, arXiv:2305.02301）：
  770M T5 用 80% 数据超过 540B PaLM。关键：提取 LLM 推理链作为额外监督信号
- 典型准确率保留：85-92%，推理速度提升 500-1000×
- 带推理链蒸馏可以超过原始 LLM 准确率（因为聚合了多次判断的知识）

**实现路径**：

a) **数据收集**（P-next-1 阶段就开始，零成本）：
   新增 `LLMJudgmentLog` 表，记录所有 LLM 判断的输入特征 + 输出 + 推理链。
   不改现有逻辑，只加日志。

b) **特征工程**（积累 2000+ 样本后）：
   从输入提取结构化特征：文本长度、实体数量、来源可信度、先验概率、
   assertion 类型、CAMEO code 等。约 20-30 个特征。

c) **分类器训练**：
   - ACH 判断：3 分类（support/contradict/irrelevant），LightGBM 或 DeBERTa-base
   - 冲突检测：二分类，Logistic Regression
   - 证据强度：回归，Gradient Boosting
   - 用 LLM 推理链作为多任务训练的辅助信号（Distilling Step-by-Step 方法）

d) **级联部署**：
   分类器置信度 > 阈值 → 直接用分类器结果
   分类器置信度 < 阈值 → fallback 到 LLM
   初期阈值设高（只替代最确定的判断），逐步放宽

**效果预期**：
- 高频场景（经济数据、常规军事动态）：分类器处理 60-80%，LLM 调用量降一个数量级
- 边界场景（罕见事件、模糊政治意图）：仍由 LLM 处理
- 成本降 5-10×，延迟降 100×+（分类器推理 1-5ms vs LLM 500-2000ms）

涉及文件：新增 `db/models/llm_judgment_log.py`，新增 `services/judgment_distiller.py`，
修改 `bayesian_ach.py` + `assertion_fuser.py`（加级联逻辑）

### 4.2 多维数据源接入

**目标**：扩展 GDELT + SearXNG 之外的结构化数据源，增强因果推断和交叉关联的数据基础。

**候选数据源**（均免费或有免费层）：

| 数据源 | 类型 | 价值 | 接入成本 |
|--------|------|------|---------|
| World Bank API | 经济指标（GDP、贸易、通胀） | 经济制裁影响分析、宏观趋势 | 低（REST API，无认证） |
| ACLED | 冲突事件（精确地理坐标+时间） | 比 GDELT 更准确的冲突数据，无媒体注意力混淆 | 低（API key 免费申请） |
| ICEWS | 政治事件（CAMEO 编码，机器编码） | 与 GDELT 互补验证，降低单源依赖 | 低（公开数据集） |
| UN Comtrade | 国际贸易数据 | 制裁效果验证、经济依赖分析 | 低（REST API） |

**实现方式**：
- 每个数据源一个 gateway tool（遵循红线 #4：工具外联统一走 Gateway）
- 统一转换为 AEGI 的 Evidence → SourceClaim 链路
- source_credibility 模块扩展，针对结构化数据源的可信度评估

**对因果推断的价值**：
- ACLED 提供精确冲突事件，消除 GDELT 的媒体注意力混淆问题
- World Bank 经济指标是连续时序，天然适合 PCMCI
- 多源交叉验证降低虚假因果的风险

涉及文件：`aegi-mcp-gateway` 新增 tool（worldbank/acled/icews），
新增 `infra/worldbank_client.py` 等，修改 `source_credibility.py`

### P-next-4 验收标准

- [ ] LLM 判断日志收集上线（P-next-1 阶段就启动），覆盖所有 LLM 判断调用
- [ ] 分类器在高频场景替代 60%+ LLM 调用，准确率保留 > 85%
- [ ] 至少 2 个新数据源接入（建议 ACLED + World Bank），走 gateway tool
- [ ] 新数据源的 SourceClaim 可参与 DS 融合和贝叶斯更新

### P-next-4 风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 分类器过拟合 LLM 偏见 | 中 | 继承并放大 LLM 错误 | 用人工反馈数据做验证集，不只用 LLM 标签 |
| 蒸馏后分布漂移 | 中 | 分类器在新场景失效 | 监控分类器置信度分布，漂移时自动回退 LLM |
| ACLED API 限流或下线 | 低 | 数据源不可用 | 本地缓存 + 降级到 GDELT only |
| 多数据源融合增加复杂度 | 中 | 调试困难 | 每个数据源独立 contract test，可单独禁用 |

---

## 终极演进：自主分析循环（P-next-5）

P-next-1 到 P-next-4 解决的是"让系统更准"。P-next-5 解决的是一个更根本的问题：
**如何让系统像资深分析师一样，自主发现问题、多维度搜索、不被单一信息蒙蔽、持续修正判断。**

### 问题：确认偏误是自主分析的最大敌人

当前 InvestigationAgent 的工作方式是线性的：检测异常 → 搜索 → 找到一个看起来合理的解释 → 停止。
这和新手分析师犯的错误一模一样——找到第一个说得通的答案就不再深挖。

更糟糕的是，LLM 的 self-correction 在没有外部反馈的情况下效果有限。
一个 agent 自己跟自己辩论，本质上还是同一个"脑子"在自我纠错，认知偏见会在循环中放大。

### 方案：Generate-Debate-Evolve 锦标赛架构

借鉴三个关键研究成果，构建四层自主分析循环：

#### 研究基础

| 论文 | 核心贡献 | 对 AEGI 的价值 |
|------|---------|---------------|
| AI Co-Scientist (arXiv:2502.18864, Google 2025.02) | Generate-Debate-Evolve 锦标赛机制，假设之间竞争淘汰而非自我修正 | 从根本上解决单 agent 确认偏误 |
| BioDisco (arXiv:2508, 2025.08) | 多 agent + dual-mode evidence + 迭代反馈 + 时间评估 | 多视角证据收集 + 假设时间验证 |
| Silent Scholar (arXiv:2512.20884, 2025.12) | Beta-Bernoulli 信念模型 + 遗忘因子 + 信息增益驱动搜索 | 数学化搜索策略 + 证据时间衰减 |
| Tool-MAD (2026.01) | 不同 agent 不同工具访问权限 | 认知框架差异化，思维多样性 |
| Diversity of Thought (2024.10/2025.01) | 多 agent 辩论中思维多样性越高效果越好 | 支持不同认知框架的设计 |
| D2D Debate-to-Detect (2025.05) | 辩论式误信息检测，模拟真实世界事实核查流程 | 辩论机制的事实核查应用验证 |

#### 第一层：多 Agent 独立探索（消除单一视角偏见）

**核心思想**：不是一个 OpenClaw agent 去搜索，而是同时派出 3-5 个 agent，
每个 agent 有不同的"认知框架"（不同的 system prompt + 不同的工具访问权限）。

```
异常事件：黄金涨 3%

Agent-经济：从货币政策、利率、美元指数角度搜索
Agent-地缘：从冲突、制裁、外交角度搜索
Agent-市场：从技术面、资金流、ETF 持仓角度搜索
Agent-供需：从矿产产量、央行购金、工业需求角度搜索
Agent-黑天鹅：专门搜索不常见的解释（系统性风险、监管变化、算法交易异常）
```

关键设计：
- 每个 agent **独立搜索、独立提交证据、独立形成假设**
- 基线策略：agent 之间**不通信**——避免群体思维（参考 BioDisco 的 dual-mode evidence）
  （P-next-5 扩展允许受约束协作，但必须经过证据链回写）
- 每个 agent 的工具权限不同（参考 Tool-MAD）：
  Agent-经济 可访问 World Bank API + 央行数据
  Agent-地缘 可访问 GDELT + ACLED + 外交数据库
  Agent-市场 可访问价格数据 + ETF 持仓 + 技术指标
- 证据隔离采用**内存隔离**：
  - 探索阶段证据保存在各 agent 的内存工作区（不写主库）
  - 进入辩论阶段后，仅将入围假设关联证据批量回写主库
  - 避免为“临时探索证据”引入复杂的数据库物理/逻辑隔离方案

**与 OpenClaw 的集成**：
- 使用 `gateway_client.agent_call()` 并行派发多个 agent
- 每个 agent 的 system prompt 定义其认知框架和搜索偏好
- agent 可自主决定搜索路径（浏览网页、读 PDF、调 API），不受预定义 query 限制
- OpenClaw 的 team agent 已有完整工具链，只需配置不同的 prompt 和权限

涉及文件：修改 `investigation_agent.py`（从单 agent 改为多 agent 派发），
新增 `services/cognitive_frames.py`（认知框架定义 + agent prompt 生成）

#### 第一层扩展：常驻领域专家 Agent 网络（Persistent Expert Network）

上面的 3-5 agent 仍然偏“任务态”。若要把上限从“高效初筛引擎”提升到
“持续运行的分析机构能力”，需要把临时 agent 升级为常驻专家网络：

- 5-8 个常驻 agent（中东/经济/军事/供应链/金融/红队等），各自独立 session
- 每个 agent 通过 OpenClaw 的 `cron + heartbeat + MEMORY.md` 做 7x24 巡检与长期记忆维护
- 不依赖单次异常触发，可主动发现慢变量变化并发起调查
- 常驻 agent 的产出以“结构化证据 + 假设”回流 AEGI，由贝叶斯层统一裁决

该扩展应明确为 P-next-5 的增强项，可在 P-next-5 后半段启动，或作为 P-next-6 首批任务。

**四条硬约束（必须同时落地）**：

1. 记忆审计：每个常驻 agent 定期回顾历史判断与真实 outcome，修正错误记忆（不只是衰减）
2. 协作约束：agent 间协作通过证据链回写主库，不允许“聊天式说服”直接改变结论
3. 调查深度闸门：多步骤调查默认 2-3 步 checkpoint，超深链路需自动验证或人工 gate
4. ROI 评估：按 agent 维度持续跟踪 token 成本、有效证据产出、后验改变量、命中率

OpenClaw 侧注意事项：
- agent-to-agent 通信（`sessions_send`）默认按策略受限，需显式开启并配置 allowlist
- 工具权限受 tool policy/sandbox 约束，不假设“任意工具默认可用”

#### 第二层：锦标赛辩论（假设竞争淘汰）

**核心思想**：假设之间两两竞争，而不是一个假设自我修正。
裁判不是 LLM（避免裁判偏见），而是 AEGI 的贝叶斯 ACH。

```
5 个 agent 各自提出假设：
  H1: 胡塞武装攻击商船（Agent-地缘）
  H2: 美联储鸽派转向（Agent-经济）
  H3: 中国央行增持（Agent-供需）
  H4: 技术性突破阻力位（Agent-市场）
  H5: 瑞士某基金衍生品爆仓（Agent-黑天鹅）

锦标赛第一轮（两两辩论）：
  H1 vs H2：各自提出支持自己、反驳对方的证据
  H3 vs H4：同上
  H5 轮空

裁判机制（AEGI 贝叶斯 ACH）：
  把双方证据都灌入 pipeline
  贝叶斯更新后看后验概率谁高
  纯数学裁决，不依赖 LLM 判断

输家处理（不是淘汰，是改进）：
  H1 输了 → 反馈给 Agent-地缘：
  "你的胡塞武装假设被美联储假设击败，
   因为铜价没涨但美元指数跌了。
   你能找到新证据挽救你的假设吗？"
  → Agent-地缘 带着反馈去搜索更多证据

锦标赛第二轮：改进后的假设再次辩论
  ...

收敛条件：
  - 某假设连续赢两轮，且后验 > 60%
  - 或者达到轮次上限（3-4 轮）
  - 或者 token budget 耗尽
```

**与现有架构的对接**：
- `bayesian_ach.py` 已有贝叶斯更新 → 直接作为裁判
- `hypothesis_adversarial.py` 已有正方/反方/法官框架 → 改造为锦标赛模式
- `get_evidence_gaps()` 已能识别证据缺口 → 生成输家的改进方向
- `TokenBudgetManager`（P-next-1）→ 控制锦标赛总成本

涉及文件：新增 `services/tournament.py`（锦标赛调度 + 配对 + 收敛检测），
修改 `hypothesis_adversarial.py`（从单轮对抗改为多轮锦标赛），
修改 `investigation_agent.py`（接收辩论反馈后定向搜索）

#### 第三层：信息增益驱动的搜索策略

**核心思想**：agent 不应该搜索"最可能找到的信息"，
而应该搜索"信息增益最大的信息"（参考 Silent Scholar 的概率框架）。

用信息论量化每条搜索 query 的预期价值：

```python
def expected_information_gain(query, hypotheses, current_posteriors):
    """计算一条搜索 query 的预期信息增益。
    
    信息增益 = 搜索结果对假设后验分布的预期 KL 散度。
    高信息增益 = 搜索结果能大幅改变假设排名。
    低信息增益 = 不管搜到什么，假设排名都不会变。
    """
    # 1. 预测 query 可能返回的结果类型（支持/反驳/无关）
    # 2. 对每种结果，模拟贝叶斯更新后的后验
    # 3. 计算更新前后后验分布的 KL 散度
    # 4. 按结果概率加权求期望
    return weighted_kl_divergence
```

搜索策略规则：
- 如果 H1 和 H2 后验很接近（45% vs 40%）→ 优先搜索能区分它们的证据
- 如果 H1 已经 80% → 搜索支持 H1 的证据信息增益很低，应搜索能推翻 H1 的证据
- 如果所有假设后验都很低（都 < 30%）→ 可能遗漏了重要假设，搜索全新方向
- 如果某假设的证据全部来自同一类来源 → 搜索不同类型来源的证据

这比"强制 30% 反面证据"精确得多——用数学告诉 agent 该搜什么。

**实现注意**：精确 KL 散度计算有鸡生蛋问题（要算搜索结果对后验的影响，但搜索还没执行）。
首版采用三信号加权的启发式近似，避免只看“最接近假设对”的单一指标：

- 假设区分度：后验最接近假设对的 gap（越小越值得找区分证据）
- 证据覆盖度：关键假设的 evidence gap 数量（缺口越多越值得补）
- 来源多样性：关键假设证据来源集中度（越集中越需要跨源验证）

```python
score = (
    w1 * normalize(disambiguation_gap_inverse)
    + w2 * normalize(evidence_gap_count)
    + w3 * normalize(source_concentration)
)
```

信息增益分数只做排序参考，不完全替代 agent 自主判断；权重由回放评估持续调优。

涉及文件：新增 `services/information_gain.py`（启发式信息增益估算 + query 排序），
修改 `investigation_agent.py`（搜索前计算信息增益，优先执行高增益 query）

#### 第四层：时间衰减 + 概念漂移检测

**核心思想**：证据会过时。昨天的"美联储鸽派发言"可能被今天的"鹰派数据"推翻。
系统应该自动检测证据过期并触发刷新（参考 Silent Scholar 的遗忘因子）。

```python
class TemporalBeliefState:
    """带时间衰减的信念状态。"""
    alpha: float          # 支持证据累积（Beta 分布参数）
    beta: float           # 反对证据累积
    gamma: float = 0.995  # 遗忘因子，半衰期 ≈ 5.8 天（地缘政治证据有效期是天/周级别）
    # 可按证据类型分级：突发事件 gamma=0.99/hour，结构性趋势 gamma=0.999/hour
    last_update: datetime
    
    def decay(self, current_time: datetime):
        """时间衰减：旧证据的影响逐渐减弱。"""
        steps = (current_time - self.last_update).total_seconds() / 3600  # 小时为单位
        decay_factor = self.gamma ** steps
        self.alpha = 1 + decay_factor * (self.alpha - 1)
        self.beta = 1 + decay_factor * (self.beta - 1)
    
    def epistemic_uncertainty(self) -> float:
        """认知不确定性 = Beta 分布的方差。"""
        total = self.alpha + self.beta
        return (self.alpha * self.beta) / (total ** 2 * (total + 1))
    
    def needs_refresh(self, threshold: float = 0.2) -> bool:
        """不确定性超过阈值时需要刷新。"""
        return self.epistemic_uncertainty() > threshold
```

触发机制：
- 定期（每小时）对所有活跃 case 的假设做时间衰减
- 当某假设的不确定性因衰减升高到阈值时，自动触发新一轮搜索
- 不是因为有新事件，而是因为旧证据"过期"了，需要验证是否仍然成立
- 与 GDELT 实时事件流联动：如果相关领域有新事件，加速衰减

与现有贝叶斯 ACH 的集成：
- `bayesian_ach.py` 的后验概率加上时间衰减维度
- `confidence_scorer.py` 的置信度评分考虑证据年龄
- `push_engine.py` 在不确定性升高时推送"证据可能过期"告警

涉及文件：新增 `services/temporal_belief.py`（时间衰减 + 刷新触发），
修改 `bayesian_ach.py`（后验加时间衰减），
修改 `push_engine.py`（不确定性升高告警）

#### 完整自主分析循环

```
异常检测（GDELT / 市场数据 / 任意数据源）
  ↓
多 Agent 独立探索（3-5 个不同认知框架的 OpenClaw agent）
  ↓ 各自独立在内存工作区提交证据和假设
锦标赛辩论（假设两两竞争，AEGI 贝叶斯做裁判）
  ↓ 输家收到反馈，带着反馈定向搜索改进
信息增益驱动的定向搜索（优先搜索 KL 散度最大的方向）
  ↓ 入围证据回写主库，贝叶斯更新
收敛检测（后验稳定 / 轮次上限 / budget 耗尽）
  ↓
推送分析报告（含完整辩论记录 + 证据链 + 不确定性量化）
  ↓
时间衰减持续监控（旧证据过期 → 自动触发刷新循环）
```

**与之前方案的关键区别**：

| 维度 | 之前（线性搜索-质疑循环） | 现在（锦标赛架构） |
|------|------------------------|-------------------|
| 视角 | 单 agent 自我纠错 | 多 agent 独立探索，消除确认偏误 |
| 假设竞争 | 一个假设反复修补 | 假设之间优胜劣汰 |
| 搜索策略 | 规则驱动（"30% 反面证据"） | 信息增益驱动（数学最优） |
| 裁判 | LLM 自我判断 | 贝叶斯 ACH 数学裁决 |
| 时间维度 | 静态分析 | 证据时间衰减 + 自动刷新 |
| 停止条件 | 固定轮次 | 收敛检测（后验稳定） |

#### OpenClaw 在锦标赛架构中的角色

OpenClaw 从"被动执行搜索指令"升级为"多个独立分析 agent 的执行层"：

1. **Agent 派发**：`gateway_client.agent_call()` 并行派发多个 agent，
   每个 agent 有独立的 session、独立的 system prompt、独立的工具权限
2. **自主搜索**：每个 agent 自主决定搜索路径——浏览网页、读 PDF、调 API、
   写脚本处理数据。不受预定义 query 限制
3. **证据隔离**：探索阶段各 agent 的证据仅存在于各自内存工作区，
   不共享数据库视图，避免通过共享数据导致认知趋同
4. **证据回写**：辩论阶段开始后，将入围假设对应证据统一写入证据库
5. **辩论反馈接收**：锦标赛输家收到 AEGI 的反馈后，agent 带着反馈继续搜索
6. **结果推送**：最终分析报告通过 `notify_user` 推送给分析师

AEGI 的角色：
1. **证据库**：统一存储辩论入围后的证据（探索阶段证据不直接入主库）
2. **贝叶斯裁判**：用数学（不是 LLM）裁决假设优劣
3. **信息增益计算器**：告诉 agent 该搜什么方向
4. **时间衰减监控器**：检测证据过期，触发刷新

#### P-next-5 验收标准

- [ ] 多 agent 并行探索可运行，3-5 个不同认知框架的 agent 独立搜索
- [ ] 探索阶段采用内存隔离，辩论阶段只回写入围证据
- [ ] 锦标赛辩论机制可运行，假设两两竞争，贝叶斯裁决
- [ ] 信息增益启发式估算可用，搜索 query 按预期增益排序
- [ ] 时间衰减机制可用，gamma 按证据类型分级，证据过期自动触发刷新
- [ ] agent 部分失败时优雅降级（≥2 存活继续，<2 降级单 agent）
- [ ] H0="以上都不是"假设纳入贝叶斯框架，P(H0) 上升时触发假设发现
- [ ] 孤儿证据追踪可用，占比超阈值时触发假设发现
- [ ] 红队 agent 可用结构化反事实框架注入新假设
- [ ] 常驻专家 agent 试点可运行（至少 2 个领域 agent，具备 cron + memory 持续巡检）
- [ ] 常驻 agent 记忆审计可运行（历史判断对照 outcome 的自动纠错流程）
- [ ] agent 协作遵循证据链约束（跨 agent 协作必须回写结构化证据）
- [ ] 深度调查 checkpoint 上线（2-3 步自动验证闸门）
- [ ] agent 级 ROI 监控可用（成本/产出/后验增量）
- [ ] 锦标赛触发条件可配置（max posterior / cross-correlation / 手动 / trust_level）
- [ ] 端到端测试：给定异常事件，系统自主完成多轮探索-辩论-收敛，输出分析报告
- [ ] 分析报告包含完整辩论记录、证据链、不确定性量化

#### P-next-5 风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 多 agent 成本过高 | 高 | 5 agent × 3 轮辩论 ≈ 43-100 次 LLM 调用/次分析 | TokenBudgetManager 全局控制 + 认知框架数量可配置（2-5） |
| agent 之间假设高度重叠 | 中 | 多样性不足，锦标赛退化为重复 | 认知框架差异化设计 + 重叠检测（语义相似度 > 0.9 时合并） |
| 锦标赛不收敛 | 中 | 假设后验持续震荡 | 硬性轮次上限 + 震荡检测（连续 2 轮变化 < 3% 视为收敛） |
| 时间衰减过快导致频繁刷新 | 低 | 不必要的搜索消耗 | gamma 按证据类型分级 + 刷新冷却期 + 只对活跃 case 衰减 |
| 信息增益计算不准 | 中 | 搜索方向偏差 | 用启发式近似代替精确 KL，信息增益只做排序参考 |
| agent 部分失败 | 中 | LLM 超时导致锦标赛中断 | 最少 2 个 agent 存活即可继续；存活 < 2 时降级为单 agent 模式（等同现有 hypothesis_engine） |
| 内存隔离下 agent 崩溃导致探索证据丢失 | 中 | 单轮探索结果丢失 | 探索阶段周期性 checkpoint（本地临时文件），进入辩论前强制快照 |
| 常驻 agent 错误记忆累积（认知污染） | 中 | 历史错误反复放大，长期偏航 | 周期性记忆审计 + 错误记忆显式修正 + 失效规则回收 |
| agent 自发协作退化为群体思维 | 中 | 互相确认偏见，误判稳定化 | 协作强制经证据链回写 + 贝叶斯裁决唯一化 + 反方红队常驻 |
| 深度调查链路过长导致跑偏 | 中 | 多步推理错误累积，证据质量下降 | 2-3 步 checkpoint + 轨迹审计 + 超深链路人工 gate |
| 常驻网络长期成本超预算 | 中 | ROI 不达标，系统不可持续 | agent 级 ROI 仪表盘 + 动态停机/降频 + Budget Market |

#### P-next-5 依赖

- P-next-1：TokenBudgetManager（成本控制）
- P-next-2：校准层（贝叶斯裁判的概率输出需要校准）、PCMCI（因果图辅助信息增益计算）
- P-next-3：Shapley 分解（辩论结果的可解释性）、meta-confidence（收敛判断）
- P-next-4：蒸馏分类器（降低多 agent 的 LLM 调用成本）、多数据源（agent 工具丰富度）

#### P-next-5+：六个高杠杆智能化优化（建议纳入 ADR）

这六项不是“加功能”，而是把目标从“更快分析”升级为“更优决策”。

1. **Decision Layer（准确率 → 决策收益）**
   - 输出从“哪个假设更可能”升级为“下一步最值得做什么（action + VOI + 风险/收益）”
   - 把系统目标函数从纯准确率扩展到决策效用

2. **Expert Feedback Compiler（专家反馈编译器）**
   - 把专家纠正从 `agree/disagree` 编译成可执行约束（源权重、场景规则、因果边降权）
   - 一次纠正影响未来同类 case，形成反馈飞轮

3. **Active Evidence Acquisition（主动证据采样）**
   - 不确定性高时自动规划“最能降不确定性”的采样任务，而非继续生成叙事
   - 将调研从“检索”升级为“实验设计”

4. **Unified Relation Graph（关联-因果-图谱融合层）**
   - 融合 NPMI 共现、PCMCI 因果边、KG 关系边，输出统一事件关系图
   - 每条边标注类型（共现/因果/结构）和置信度，供下游统一消费

5. **Compute Budget Market（多 agent 预算市场）**
   - 按预期信息增益给 agent 动态分配 token 预算，高增益 agent 优先
   - 解决“多 agent 能力提升与成本失控”的张力

6. **Shadow Mode + Replay（影子评估与历史回放）**
   - 新策略先影子运行，不影响线上结论
   - 用历史回放比较收益与回归风险，避免“看起来更聪明，实际更差”

建议顺序（收益/风险比）：
1) 先做 1+2+6（高杠杆、可控）  
2) 再做 3+4（智能上限明显提升）  
3) 最后做 5（复杂度最高）

#### 假设集完整性保障

锦标赛架构的隐含假设是"正确答案在生成的假设集合里"。如果假设集本身不完整，
锦标赛只会在错误选项中选出"最不错的错误"。需要三层机制保障假设集完整性：

**第一层：异常驱动的假设发现（自下而上）**

现状：`gdelt_monitor.py` 检测到异常后只发告警事件，不触发假设生成。
`cross_correlation.py` 有 `suggested_hypothesis` 字段但是 LLM 随机建议，无系统化框架。

方案：当异常事件无法被现有假设集合中任何一个以 P(E|Hi) > 0.3 解释时，
触发 abductive reasoning（溯因推理）生成新假设。不是每个 event_surge 都触发，
只有"孤儿异常"（对所有现有假设的似然都低）才值得生成新假设。

```python
def should_trigger_hypothesis_discovery(
    anomaly: AnomalyEvent,
    hypotheses: list[Hypothesis],
    posteriors: dict[str, float],
) -> bool:
    """只有当异常无法被现有假设解释时才触发假设发现。"""
    max_likelihood = max(
        assess_likelihood(anomaly, h) for h in hypotheses
    )
    return max_likelihood < 0.3  # 所有假设都无法解释这个异常
```

涉及文件：修改 `services/gdelt_monitor.py`（异常→假设发现触发），
新增 `services/hypothesis_discovery.py`（溯因推理生成新假设）

**第二层：对抗性假设注入（红队 agent）**

现状：`hypothesis_adversarial.py` 的 Prosecution agent 只能质疑现有假设，不能注入新假设。

方案：在锦标赛中加入专职红队 agent，职责不是评估现有假设，而是生成"黑天鹅"假设。
用结构化反事实框架替代开放式"想想意外情况"——明确列出当前假设的关键前提，
逐一否定，检查是否有替代解释能覆盖同样的证据。

注意：LLM 生成真正意外假设的能力有限，倾向于生成常见叙事变体。
反事实框架（"如果前提 X 不成立，什么替代解释能覆盖同样的证据？"）
比开放式 prompt（"想想意外情况"）更有效。

涉及文件：修改 `services/hypothesis_adversarial.py`（新增红队注入模式），
修改 `services/tournament.py`（红队 agent 参与锦标赛）

**第三层：元认知循环（假设集完整性检测）**

现状：`bayesian_ach.py` 的后验之和恒等于 1.0（数学约束），无法直接表示"未解释概率"。
`confidence_scorer.py` 测量分析质量但不检测假设集完整性。

方案：两个机制组合——

a) 在贝叶斯框架中加入显式 H0 = "以上都不是"假设，
   设定 P(E|H0) 为基线值（0.3），让贝叶斯更新自然追踪 H0 的后验。
   如果 P(H0) 持续上升，说明假设集不完整，触发假设发现。

b) 追踪"孤儿证据"——对所有假设 P(E|Hi) 都低的证据项。
   孤儿证据占比超过阈值（如 20%）时触发假设发现。
   孤儿证据本身作为假设发现的输入线索（"这些证据指向什么？"）。

H0 提供全局信号（"假设集可能不完整"），孤儿证据提供具体线索（"哪些证据没被解释"）。

涉及文件：修改 `services/bayesian_ach.py`（加入 H0 + 孤儿证据追踪），
新增 `services/metacognitive_loop.py`（完整性检测 + 触发假设发现）

**锦标赛触发条件**

不是所有分析都需要启动锦标赛。触发条件：
- (a) 常规 ACH 的 max(P(Hi)) < 0.4（没有明确赢家）
- (b) cross_correlation 发现高显著性模式
- (c) 分析师手动触发
- (d) trust_level=3 的 case 自动触发

---

## 远景探索：超越文本分析（P-next-6+）

P-next-1 到 P-next-5 都在优化"如何更好地分析文本信息"。但情报分析的信号远不止文本。
以下方向突破文本分析的边界，让 AEGI 从"文本分析引擎"进化为"全域态势感知与策略参谋系统"。

### P-next-6（优先落地）：智能化上限扩展

在进入“大远景探索”前，建议先完成一个明确的 P-next-6，把系统目标从
“生成更好的分析报告”升级为“做出更优的决策建议”。

| 杠杆 | 目标 | 直接收益 |
|------|------|----------|
| Decision Layer | 准确率目标升级为决策效用（VOI + action） | 输出可执行决策建议，而非仅概率结论 |
| Expert Feedback Compiler | 专家纠正编译为可执行约束 | 反馈形成长期飞轮，不再只影响单次 case |
| Active Evidence Acquisition | 不确定性驱动主动采样 | 调研从检索升级为实验设计 |
| Unified Relation Graph | 共现/因果/KG 统一关系层 | 下游推理共享同一语义底座 |
| Compute Budget Market | agent 预算按信息增益动态分配 | 在成本不变下提升有效探索量 |
| Shadow Mode + Replay | 新策略影子评估 + 历史回放 | 降低升级回归风险，支持持续发布 |

实施优先级：
1. Decision Layer + Feedback Compiler + Shadow Mode（先稳住目标函数与发布安全）
2. Active Evidence Acquisition + Unified Relation Graph（再拉高智能上限）
3. Budget Market（最后优化规模化成本效率）

#### P-next-6.1 图数学优先路径（GNN 后置）

问题：图由节点与边构成（graph/node/edge），邻接矩阵与拉普拉斯确实是图学习基础，
但当前阶段如果直接上 GNN，容易在标注不足和评估闭环未完成时陷入高复杂度低收益。

数学化建议（先后顺序）：

1. **时变有符号异构图（先做）**
   - 将支持/反驳、因果、共现、实体关系统一到一张图
   - 边带时间衰减与可信度权重：`w_e(t) = w_e0 * exp(-lambda * delta_t)`

2. **图扩散 + 谱异常检测（先做）**
   - 用扩散分数做影响传播（比纯文本推理更稳）
   - 用谱残差识别结构突变（比单点阈值更鲁棒）
   - 归一化拉普拉斯：`L_sym = I - D^(-1/2) A D^(-1/2)`

3. **概率图推断替代部分 LLM 判断（先做）**
   - 在证据→假设更新链路引入 factor graph / belief propagation
   - LLM 负责解释与候选生成，确定性推断负责后验更新

4. **SCM/DoWhy 反事实主链（并行推进）**
   - 反事实估计坚持因果模型主链，LLM 不参与核心估计
   - 输出区间与可识别性前提，避免叙事化“伪定量”

5. **GNN 增强（后置）**
   - 条件：标签与回放评估足够稳定后再引入
   - 用于先验打分/候选排序，不直接接管最终裁决

结论：对 AEGI 的更优数学路径是“图论 + 概率图 + 因果推断先行，GNN 后置增强”。

#### P-next-6.2 动态本体治理：专家校验优先（选择性而非全量）

问题：如果允许 AI 动态扩展本体（新实体类型/新关系/新规则/新动作），
不加治理会出现“本体膨胀 + 错误固化 + 长期污染”。

决策：采用“双轨治理”而非“纯自动”或“全量人工审核”。
- 轨道 A：自动门控（高频、低风险变更）
- 轨道 B：专家晋升闸门（低频、高风险变更）

这意味着专家参与是“质量闸门”，不是“替代 AI 进行日常分析”。

**分层本体策略**

| 层级 | 内容 | 维护方式 | 变更策略 |
|------|------|----------|----------|
| Core Ontology（稳定层） | 国家/组织/人物/事件等核心类型与基础关系 | 人工主导 | 慢变更，强审核，强回放 |
| Candidate Ontology（候选层） | AI 新发现的实体子类、关系模式、场景规则、action 策略 | AI 提案 + 自动门控 | 快迭代，未达标不晋升 |

**统一变更单元（Proposal）**

每个 AI 提案必须结构化提交：
- `proposal_type`: `entity_type` / `relation_type` / `logic_rule` / `action_policy`
- `evidence_refs`: 证据链引用（source_claim/assertion/reasoning_trace）
- `support_stats`: 多源支持度、采样一致率、历史出现频次
- `impact_scope`: 影响场景（entity/scenario/global）
- `risk_tier`: L1/L2/L3（系统自动打级）
- `rollback_plan`: 回滚条件与回滚目标版本

**晋升流程（AI 提案 -> 正式生效）**

1. AI 生成提案，先写入 Candidate 区，不直接改 Core。  
2. 自动门控校验：  
   - 多源独立支持（至少 2 个独立来源）  
   - 关键判断采样一致率达标（例如 `agreement_rate >= 0.67`）  
   - Shadow replay 无显著退化（Brier/ECE/误报率不劣化超过阈值）  
   - 预算影响可接受（token/cost 增幅在阈值内）  
3. 按风险分流：  
   - L1（低风险）：自动晋升，纳入抽检  
   - L2（中风险）：自动晋升 + 专家异步复核（可撤销）  
   - L3（高风险）：必须专家审批后晋升  
4. 版本化发布：通过 `ontology_versioning` 生成新版本，保留 diff 与审计记录。  
5. 灰度上线：新版本先 Shadow 运行，通过回放后再切主。  
6. 触发回滚：若线上指标越界，自动回退到上一个稳定版本。  

**高风险（L3）强制专家审批范围**

- 新增/修改核心实体类型或核心关系约束（domain/range）
- 新增高影响推理规则（会显著改变告警或假设排序）
- 新增自动 action 策略（会触发外部通知/升级动作）
- 跨场景全局规则改写（影响多个 scenario_type）

**与现有六大杠杆的衔接**

- Decision Layer：只消费“已晋升”的规则与 action 策略，避免候选规则直接影响决策。  
- Expert Feedback Compiler：把专家纠正编译为新提案或规则降权，不直接热修核心本体。  
- Active Evidence Acquisition：优先为“待晋升提案”补齐关键缺失证据。  
- Unified Relation Graph：Candidate 与 Core 共用图存储，但查询默认只读 Core + 已发布扩展。  
- Compute Budget Market：将“提案验证任务”纳入预算市场，按预期收益分配资源。  
- Shadow Mode + Replay：作为提案晋升前的发布门禁，不通过不得升 Core。  

**治理指标（每周追踪）**

- `promotion_precision`: 晋升后 30 天未回滚比例  
- `rollback_rate`: 新版本回滚率  
- `expert_load_hours`: 专家审核人时（目标持续下降）  
- `quality_delta`: 发布前后 Brier/ECE/误报率变化  
- `cost_delta`: 发布前后单位 case 成本变化  
- `proposal_cycle_time`: 提案从创建到结论的中位时长  

结论：专家校验是合适方案，但必须是“选择性专家校验 + 自动门控 + 版本化回滚”的治理体系，
才能在保证质量的前提下，发挥 AI 动态扩展本体的上限。

#### P-next-6.3 范式升级：从反应式分析到策略式参谋

**1) 范式升级声明**

当前主链路仍以“输入信息 -> 分析 -> 输出判断”为核心，属于反应式系统。
P-next-6.3 的目标是升级为策略式系统：输出不止是“发生了什么”，还包括
“可干预策略空间、预期效果、风险代价与执行后反馈修正”。

**设计哲学基础：AI 超越人类团队的三个结构性优势**

AEGI 的长期目标不是"辅助分析师"，而是成为超越任何人类分析师团队的分析实体。
这个目标基于 AI 相对人类团队的三个结构性优势：

1. **零损耗信息共享**：多个 agent 共享同一证据库、因果图、本体，无翻译损耗。  
   人类团队 5 人的信息融合效率可能只有 30-40%，AI 接近理论最优。  
2. **无限并行 + 即时切换**：agent 真正并行运行，且可在毫秒内跨域切换上下文。  
   人类注意力是排他的，AI 能做到全域同时关注。  
3. **完美记忆 + 无认知疲劳**：持久 memory 不会遗忘、不会疲劳、不受情绪影响。  
   常驻 agent 运行 6 个月后的领域记忆完整度远超任何单个人类分析师。  

这三个优势不是自动获得的，需要刻意设计才能发挥：
- 证据库存完整推理链（不只是结论），支撑零损耗共享  
- 常驻 agent 有领域专长但不被领域限制，支撑跨域即时切换  
- memory 结构化为动态本体（不只是日志），支撑完美记忆的有效利用  

人类专家的角色从"使用工具的分析师"演进为"校准认知模型和定义行动边界的教练"。

目标函数从 `analysis_accuracy` 扩展为 `decision_utility`：
- 正确识别态势（Accuracy）
- 生成可执行策略（Actionability）
- 量化干预效果（Causal Effect）
- 控制策略风险（Risk-aware）

**2) 核心机制**

a) 推理循环（Hypothesis -> Prediction -> Validation -> Revision）
- 假设不直接评分，而是先生成“可观测预测”
- 主动验证预测，利用“不一致证据”驱动假设修正
- 支持识别“应该出现但未出现”的沉默信号

b) 因果骨架（Causal Graph as Backbone）
- 因果图从“分析模块”升级为“系统推理底座”
- 假设生成、证据定位、反事实评估、策略干预统一走因果图
- 每条因果边保留来源（统计/语义/专家）、置信度、适用条件

c) 策略搜索（Intervention Search）
- 在受约束行动空间内做多目标搜索（安全/经济/影响力/成本）
- 每个动作通过干预推断估计下游效果（非 LLM 直觉）
- 输出 Pareto 前沿，而非单一“最优答案”

d) 持续博弈循环（Continuous Strategic Loop）
- 监测 -> 推理 -> 策略 -> 执行追踪 -> 偏差归因 -> 模型修正
- 每轮迭代复用常驻 agent 的长期记忆与新证据

**3) 五个约束闸门（硬性）**

1. `Intent Gate`：意图只允许作为“可证伪假设”，禁止作为事实断言。  
2. `Causal ID Gate`：do-calculus 推断必须输出识别条件状态；不满足条件时强制降级为参考结论。  
3. `Action Space Gate`：策略搜索仅在“合法/合规/伦理/预算”约束动作空间内执行。  
4. `Search Budget Gate`：博弈搜索必须执行 top-k 剪枝 + 深度上限 + 滚动规划，防止组合爆炸。  
5. `Counterfactual Gate`：策略效果评估必须提供反事实基线，禁止仅凭执行后观察值判定有效。  

**4) 与现有路线图的集成（目标函数重定义）**

- P-next-3：从“可解释性增强”升级为“可解释性 + 假设驱动推理循环（高优先级 case 先行）”
  - 新增 `predict_observables` 和 mismatch-driven revision
- P-next-4：从“降本+扩源”升级为“降本+扩源+因果骨架基础设施化”
  - 因果图从阶段能力变为跨模块底座
- P-next-5：从“锦标赛分析”升级为“持续博弈循环”
  - 锦标赛定位为循环中的推理/对抗子机制

**5) 验收标准**

- [ ] 高优先级 case 至少 60% 使用推理循环而非一次性线性分析  
- [ ] 每个意图结论均附可证伪观测项与跟踪窗口  
- [ ] 干预评估结果 100% 标注识别条件状态（满足/不满足/未知）  
- [ ] 策略建议 100% 绑定动作约束与预算约束  
- [ ] 博弈搜索平均分支数与深度受控在预设上限内（可观测）  
- [ ] 策略效果报告 100% 含反事实基线对照  
- [ ] Shadow/Replay 下，新策略相对旧策略的决策效用无显著退化  

**6) 风险矩阵**

| 风险 | 等级 | 影响 | 缓解 |
|------|------|------|------|
| 因果图错误导致策略误导 | 高 | 错误干预建议 | 识别条件门禁 + 专家校验 + 回放验证 |
| 意图推断过度自信 | 高 | 误判对手动机 | 可证伪约束 + 失败自动降权 |
| 策略空间越界（合规/伦理） | 高 | 不可执行或高风险建议 | Action Space Gate + 审批白名单 |
| 博弈搜索组合爆炸 | 中 | 延迟失控、成本飙升 | top-k + 深度限制 + 滚动规划 |
| 执行反馈误归因 | 高 | 错误学习与策略漂移 | 反事实基线 + Shadow/Replay 双校验 |
| 常驻记忆导致路径依赖 | 中 | 认知惯性增强 | 归零对照 + 先验敏感性 + 记忆审计 |

**7) 核心竞争力：AI 团队超越人类专家团队的五个结构性维度**

AEGI 超越人类专家团队的策略不是“在每个维度都比人类强”，
而是在人类团队结构性做不到的维度上建立压倒性优势：

| 维度 | AI 结构性优势 | 人类团队结构性限制 | AEGI 实现路径 |
|------|---------------|--------------------|---------------|
| 跨域穷举扫描 | 系统性扫描跨领域异常关联 | 跨领域发现依赖偶然交流 | NPMI + PCMCI + 隐含关系发现器 |
| 时间连续感知 | 7×24 不间断，无交接损耗 | 轮班交接损失、注意力中断 | 常驻 agent + 持续态势模型 |
| 数学一致性 | 贝叶斯/因果推断保持一致约束 | 判断受顺序/资历/政治因素干扰 | 贝叶斯裁决 + 因果骨架 |
| 完整可验证性 | 结论可追溯并可证伪 | 人类隐性推理常难复盘 | reasoning_trace + 证伪追踪 + 回放 |
| 瞬时知识迁移 | 学习可快速共享到全体 agent | 培训/文档迁移慢且有损耗 | 动态本体 + 方法论迁移层 |

在人类更擅长的维度（隐性知识、创造性假设、情境判断）上，
AEGI 的策略不是“完全替代”，而是通过常驻记忆、专家校准、框架元认知做到“足够强且可验证”。

AI 与人类团队的现实差距，核心不在“理解深度”单点，
而在“知识的时效性与情境性管理能力”。
常驻 agent 解决时效性，动态本体 + 元认知解决情境性。

结论：P-next-6.3 不是“再加一个功能”，而是把 AEGI 的主目标从“分析正确”
升级到“策略有效且可验证”。

#### P-next-6.4 人类优势映射层：把“顶级专家能力”工程化

P-next-6.3 解决“从分析到策略”的主链路，P-next-6.4 解决“如何补齐人类专家团队最强的六种能力”。
目标不是模仿人类，而是把这些能力转译为可度量、可迭代、可审计的系统机制。

**核心映射表**

| 人类专家优势 | AEGI 对应能力 | 核心机制 | 主指标 |
|--------------|---------------|----------|--------|
| 直觉（经验压缩） | 场景识别器 + 模式库 | 长期案例压缩训练 + 新颖性检测（不匹配即深挖） | 已知模式命中率、未知模式检出率 |
| 讲故事（决策叙事） | 受众自适应叙事层 | Truth Engine/Narrative Engine 分层，按受众与时限生成多版本 | 决策理解时长、关键信息保真率 |
| 关系网络（知道问谁） | 专家能力图谱 + 主动咨询 | 分析师领域准确率建模 + 定向咨询路由 | 咨询命中率、反馈有效增益 |
| 跨域类比（结构迁移） | 结构类比引擎 | 因果图部分同构匹配 + 角色模式映射 | 类比命中后预测改善幅度 |
| 质疑前提（框架元认知） | 框架适用性评估 + 自动切换/组合 | 框架-问题匹配模型 + 失配告警 + 框架集成 | 框架失配率、切换后性能提升 |
| 政治敏感度（可行性判断） | 策略可行性过滤器 | 硬约束（法律/伦理/授权）+ 软约束（资源/时机/政治） | 建议采纳率、执行成功率 |

**关键实现原则**

1. 直觉能力不是“再跑一遍大模型”，而是“经验压缩后的快速路由”。  
2. 叙事层不得改写事实层：Narrative 只负责表达，不得修改 Truth Engine 结论。  
3. 结构类比优先“部分同构 + 角色映射”，不采用严格同构硬匹配。  
4. 框架元认知必须可解释：系统需回答“为何当前框架不适配”。  
5. 可行性过滤器必须前置到策略搜索，不是报告末尾的事后备注。  

**与现有模块的衔接**

- 场景识别器复用 P-next-1~5 的历史判断日志、回放数据、失败分类库（F-01~F-08）  
- 叙事层复用探索十九的产品化输出，并新增“时限模板”（T-5m/T-1h/T-1d）  
- 专家能力图谱复用探索十六的网络效应模型，升级为主动咨询路由  
- 结构类比引擎复用 Unified Relation Graph 与因果骨架（P-next-6.1/6.3）  
- 框架元认知与 PiEvo 互补：先判“是否适配”，再做“框架演化”  
- 可行性过滤器接入 Action Space Gate，作为策略搜索硬门禁的一部分  

**验收标准**

- [ ] 高频场景中，场景识别器命中模式后的平均分析延迟下降（相对基线）  
- [ ] 决策者版本叙事可在 30 秒内传达“结论+风险+动作”，且关键事实不失真  
- [ ] 主动咨询路由在高不确定 case 中显著提升反馈有效性  
- [ ] 结构类比命中 case 的预测校准优于纯语义检索基线  
- [ ] 框架失配检测能识别至少一类“ACH 假设不互斥”场景并自动切换  
- [ ] 所有策略建议均通过可行性过滤器并记录拒绝原因码  

**风险与约束**

| 风险 | 影响 | 缓解 |
|------|------|------|
| 场景识别器固化旧模式 | 新型事件误分流 | 新颖性阈值 + 未匹配强制深度分析 |
| 叙事层过度优化表达 | 事实被弱化或误导 | Truth/Narrative 强隔离 + 审计抽样 |
| 专家图谱引入声望偏见 | 反馈加权失真 | 领域分桶评分 + 反从众校正 |
| 类比误匹配 | 错误迁移历史轨迹 | 部分同构置信阈值 + 反例校验 |
| 框架切换震荡 | 系统不稳定 | 切换冷却期 + 多框架集成回退 |
| 可行性过滤过严 | 策略创新受限 | 硬/软约束分层 + 专家可覆写审批 |

结论：P-next-6.4 使 AEGI 不仅“会分析、会规划”，还具备顶级专家团队的关键能力映射，
并以工程化方式保证可解释、可审计、可持续优化。

#### P-next-6.5 自进化与战略协调层：让系统“知道如何变强”

P-next-6.3/6.4 解决“如何更好分析与决策”，P-next-6.5 解决“系统如何持续自我改进并进行战略级资源协调”。

**六个核心能力（7-12）**

| 能力 | 核心问题 | 机制 | 输出 |
|------|----------|------|------|
| 自我进化闭环 | 系统如何主动发现并修补能力短板 | 元分析诊断 -> 原因定位 -> 改进计划 -> Shadow/Replay 验证 -> 晋升 | `improvement_plan` + `improvement_result` |
| 反事实主化 | 如何系统思考“如果不是这样会怎样” | 对关键结论/策略强制附反事实对照与识别条件标注 | `counterfactual_baseline` |
| 战略注意力分配 | 系统级“该看什么”如何决策 | 领域级资源分配器（VOI × 影响 × 紧迫度 / 成本） | `attention_budget_plan` |
| 关注窗口预测 | 什么时候该提高警戒 | 事件日历 + 季节/历史模式 -> 风险窗口预测 -> 监测频率调整 | `attention_windows` |
| 隐含关系发现（KG 暗物质） | 如何发现未显式建模的关键联系 | 扫描“无显式边但高行为相关”实体对，进入候选本体并验证 | `latent_relation_candidates` |
| 认知多样性量化保障 | 多 agent 是否真的多样化 | Jaccard 距离 + 错误相关性双指标，低多样性触发强制异构 | `diversity_report` |

**硬性约束闸门**

1. `Self-Evolution Gate`：任何自我改进不得直接上线，必须通过 Shadow/Replay + 人类闸门。  
2. `Counterfactual Gate+`：反事实结果必须标注识别条件状态；不满足条件仅供参考。  
3. `Attention Objective Gate`：注意力分配必须显式目标函数，禁止黑箱分配。  
4. `Latent Relation Gate`：隐含关系只进候选区，未经验证不得进入核心推理链。  
5. `Diversity Dual-Metric Gate`：多样性需同时满足“输出差异 + 错误低相关”。  

**与现有模块衔接**

- 自我进化闭环复用：探索六（元分析）+ 探索十五（脆弱性）+ Shapley 分解  
- 反事实主化复用：P-next-6.3 因果骨架 + DoWhy 干预推断  
- 战略注意力分配是 Compute Budget Market 的上层调度器（战略层 > 战术层）  
- 关注窗口预测复用：时间尺度分层 + 事件日历 + 历史季节性  
- 隐含关系发现复用：NPMI/PCMCI/Unified Graph，并接入动态本体候选晋升流程  
- 认知多样性保障复用：锦标赛输出、agent 配置空间、红队对抗场景  

**验收标准**

- [ ] 自我进化循环可在无人工触发下生成并完成至少一轮“诊断->改进->验证”  
- [ ] 关键策略建议 100% 附反事实基线与识别条件标签  
- [ ] 领域级注意力分配可解释，且资源调整后不确定性下降可观测  
- [ ] 高风险窗口预测在回放集上优于固定频率监测基线  
- [ ] 每轮隐含关系候选均有验证结论（晋升/驳回/待补证）  
- [ ] 锦标赛多样性报告默认输出，低多样性自动触发配置重采样  

结论：P-next-6.5 让 AEGI 从“会分析的系统”进化为“会自我改进、会战略协调的系统”，
这是走向长期超越人类团队能力的关键层。

#### P-next-6.6 极端不确定性与质量防护层：黑天鹅、偏见、过载

P-next-6.6 处理三个“系统运行一年后必然出现”的现实问题：
黑天鹅冲击、模型系统性偏见、信息过载导致的信噪比崩塌。

**三项核心能力（13-16）**

| 能力 | 核心问题 | 机制 | 输出 |
|------|----------|------|------|
| 黑天鹅应急模式 | 超出历史模式时如何避免系统失真 | 多信号联合异常触发 + 历史权重降级 + 实时证据优先 + 人工紧急闸门 | `black_swan_alert` + `emergency_mode_report` |
| 系统性偏见审计 | LLM 在实体/文化/立场上的方向性偏差 | 对照实验（替换实体名）+ 显著性检验 + 偏见补偿权重 | `bias_audit_report` + `bias_compensation_profile` |
| 信息过载防护 | 实时多源输入下噪声淹没信号 | 入口轻量过滤（信息量/重复度/源质量）+ 召回保护抽检回流 | `ingestion_filter_metrics` + `recall_guard_report` |

**硬性约束闸门**

1. `Black Swan Gate`：进入黑天鹅模式后，不允许“全停历史推理”，必须执行“历史权重降级 + 实时证据优先”。  
2. `Bias Audit Gate`：偏见结论必须基于固定对照集与统计显著性，禁止经验性主观判定。  
3. `Overload Recall Gate`：入口过滤必须启用召回保护（随机抽检回流），避免弱信号被系统性误删。  

**与现有模块衔接**

- 黑天鹅应急复用：探索二十二（时间压力模式）+ 探索六（元分析）+ Shadow/Replay  
- 偏见审计复用：多模型对冲、语言文化补偿、专家反馈编译  
- 过载防护复用：战略注意力分配器（选领域）+ 入口过滤器（选信息）双层协同  

**验收标准**

- [ ] 联合异常触发后，系统可在规定时限内切入应急模式并输出受限策略建议  
- [ ] 偏见审计可稳定复现至少一类实体替换偏差，并输出可执行补偿配置  
- [ ] 入口过滤在降噪的同时保持召回率不低于基线阈值（由回放集验证）  
- [ ] 黑天鹅期间模型输出默认附“低可迁移性”标签与人工复核要求  

结论：P-next-6.6 不是“增加更多能力”，而是保证系统在极端场景中不失控、
不中毒、不被噪声淹没，是迈向长期可信运行的必要层。

#### P-next-6 执行收敛修复：MVP、里程碑拆分与核心数据流

为避免 P-next-6 范围膨胀导致“长期无法收敛”，本 ADR 增加执行收敛约束。
原则：不改 `P-next-6.1~6.6` 编号体系，但按里程碑闸门分段交付。

**1) P-next-6 内部分段（强制）**

| 里程碑 | 范围 | 退出条件（Gate） |
|--------|------|------------------|
| 6A 决策底座 | Decision Layer（基础）、Feedback Compiler（基础）、Shadow/Replay、Unified Relation Graph（最小） | 单领域可稳定输出 `recommended_actions`，且 Shadow 不劣化 |
| 6B 策略推理 | P-next-6.3（推理循环 + 因果骨架 + 策略搜索） | 五个约束闸门全部可观测，反事实基线默认输出 |
| 6C 人类优势映射与自进化 | P-next-6.4 + P-next-6.5 | 形成“诊断 -> 改进 -> 验证”闭环，且多样性报告默认启用 |
| 6D 极端鲁棒性 | P-next-6.6 | 黑天鹅/偏见/过载三防护在回放集验证通过 |

**2) P-next-6 MVP（最小可行策略参谋）**

MVP 仅要求三件事：
- Decision Layer（基础版）：输出 `VOI + 建议动作 + 风险说明`
- Shadow/Replay：所有策略升级必须先走影子验证
- 单领域常驻 agent 验证（建议中东或经济制裁）

MVP 验收：
- 在单领域高优先级 case 上，策略建议相对“仅分析输出”具备可量化效用提升
- Shadow 模式下无显著性能退化
- 每个策略建议均可回溯到证据链与反事实基线

**3) 核心数据流（统一对象与接口）**

```text
Evidence -> Claim -> Assertion -> HypothesisSet -> TournamentResult -> Judgment
                                                            |
                                                            v
                                              StrategyOption -> ActionPlan -> ExecutionOutcome
                                                    ^                                 |
                                                    |                                 v
                                      FeedbackEvent <--------- Expert/Outcome ---------
                                            |
                                            v
                                   MetaDiagnosis -> EvolutionPlan -> Model/Policy Update
```

统一对象（最小集合）：
- `EvidenceItem`
- `Claim`
- `Assertion`
- `HypothesisSet`
- `TournamentResult`
- `Judgment`
- `StrategyOption`
- `ActionPlan`
- `ExecutionOutcome`
- `FeedbackEvent`
- `MetaDiagnosis`

接口约束：
- 任何模块不得绕过 `Judgment` 直接输出策略建议
- 任何自动更新必须由 `MetaDiagnosis` 触发并绑定 `Shadow/Replay` 记录
- agent 间协作通过证据库与事件总线，不允许“私有对话即裁决”

**4) 横切面五与 P-next-6.6 的职责边界（避免重叠）**

- 横切面五：定义鲁棒性接口规范（健康检查、异常信号、降级协议、审计字段）
- P-next-6.6：实现高级鲁棒性能力（黑天鹅检测算法、偏见审计流程、过载防护策略）

落地规则：
- P-next-1 起所有模块必须实现横切面五接口最小集
- P-next-6.6 仅承载“高级能力实现”，不重复定义通用接口规范

**5) 常驻 agent 集中架构约束（避免“定时脚本化”）**

- 通信：agent -> AEGI 事件总线 -> 证据库；agent 间信息交换必须可审计
- 一致性：Core Ontology 全局共享；Candidate Ontology 可局部扩展但不得与 Core 冲突
- 同步：agent 新证据先写主库，再由主库同步回 agent 记忆视图
- 恢复：agent 进程故障后必须可基于 `checkpoint + event offset` 恢复
- 弹性：按领域热度动态伸缩 agent 数量，但受预算闸门限制

### 探索一：预测市场作为校准锚点（推荐最先做，成本极低）

**问题**：校准层（P-next-2）的冷启动需要 100+ 标注样本，积累期可能数月。
在此期间所有概率输出都标注"未校准"，分析师无法判断系统输出的可信度。

**洞察**：预测市场（Polymarket、Metaculus、PredictIt）的价格本身就是经过真金白银校准的概率。
"某国 2026 年发生军事冲突"在 Polymarket 上的价格是 0.35，这个 35% 比任何 LLM 输出都更可信。

**方案**：

a) 接入预测市场 API（Polymarket 有公开 API，Metaculus 有公开数据集），
   作为一个特殊的数据源，提供"市场校准概率"。

b) 三种使用方式：
   - **先验锚定**：用预测市场价格替代默认均匀先验。
     现在 `bayesian_ach.py` 的 `initialize_priors()` 已支持外部 priors dict，
     默认是均匀分布 P(H)=1/N，换成市场价格能提供更合理的起点。
   - **校准基准**：AEGI 的后验 vs 预测市场价格，差异大的地方要么是 AEGI 发现了
     市场还没反映的信息（alpha），要么是 AEGI 错了。这个差异本身就是有价值的信号。
   - **冷启动替代**：在校准层训练完成前，用预测市场价格作为外部校准参考。

c) 长期跟踪 AEGI vs 预测市场的 Brier Score，作为系统能力的客观评估。

**实现成本**：极低。一个 API client + 一个 gateway tool，约 200 行代码。
不需要改现有架构，只是多一个数据源。

**限制**：预测市场只覆盖热门话题，长尾事件没有市场价格。
但热门话题恰好是分析师最关注的。

涉及文件：新增 `infra/prediction_market_client.py`（Polymarket/Metaculus API），
`aegi-mcp-gateway` 新增 tool，修改 `bayesian_ach.py`（先验可选用市场价格）

### 探索二：知识图谱多跳推理辅助假设生成

**问题**：假设生成完全依赖 LLM 的"想象力"。LLM 擅长常见模式，
但不擅长发现隐藏的间接关系（A→B→C→D 的四跳推理）。

**洞察**：Neo4j 里已经存储了大量实体和关系。知识图谱本身可以做推理——
如果 A 制裁了 B，B 是 C 的主要贸易伙伴，C 是 D 的能源供应商，
那 A 的制裁可能间接影响 D 的能源安全。这种多跳推理用图算法比 LLM 更可靠。

**方案**：

a) **路径发现**：给定异常事件涉及的实体，在 Neo4j 中搜索 2-4 跳内的所有路径。
   用 Cypher 查询：
   ```cypher
   MATCH path = (source:Entity {name: $anomaly_entity})-[*2..4]-(target:Entity)
   WHERE target.type IN ['Country', 'Organization', 'Commodity']
   RETURN path, reduce(s = 1.0, r IN relationships(path) | s * r.confidence) AS path_confidence
   ORDER BY path_confidence DESC
   LIMIT 20
   ```

b) **链接预测**：用 PyKEEN（知识图谱嵌入）预测尚不存在但可能存在的关系。
   比如 A 和 D 之间没有直接关系，但嵌入空间中它们很近，
   说明可能存在未被记录的间接影响。

c) **假设生成**：把发现的路径和预测的链接作为假设生成的输入：
   "图谱显示 A→B→C→D 的影响路径，置信度 0.6。
    这是否能解释当前观察到的 D 的异常？"

**与锦标赛架构的集成**：
- 图谱推理的结果作为额外的"认知框架"注入某个 agent
- 或者作为独立的假设来源，直接进入锦标赛

**实现成本**：中低。路径发现用现有 Neo4j 即可——`neo4j_store.py` 已有
`find_multi_hop_paths()`（max_depth 可配置），`graph_analysis.py` 已有 `find_paths()` 封装。
PyKEEN 已在可选依赖中且有 `link_predictor.py` 实现（模型训练+缓存+预测）。
真正缺的只是"图谱发现 → 假设生成"的桥接层。

涉及文件：新增 `services/kg_reasoning.py`（路径发现 + 链接预测），
修改 `services/hypothesis_discovery.py`（图谱推理作为假设来源）

### 探索三：分析师反馈强化学习（Bandit 优化）

**问题**：feedback_service 收集了分析师反馈，但只用来做校准（Platt scaling）。
系统不会根据反馈调整自己的行为——哪种搜索策略更有效、哪种认知框架更有用、
推送什么粒度的信息分析师最满意，系统不知道。

**方案**：用 contextual bandit 算法，把分析师反馈作为奖励信号，
在线优化系统的多个决策点。

a) **认知框架选择**（P-next-5 锦标赛）：
   - 5 个认知框架不是每次都全派，用 Thompson Sampling 选择 3 个
   - 奖励信号：分析师标注"有用"的分析中，哪些认知框架贡献了关键假设
   - 长期效果：系统自动学会"经济类异常多派 Agent-经济和 Agent-供需"

b) **搜索策略优化**：
   - 信息增益计算有多个近似方法，哪个实际效果最好？
   - 用 bandit 在不同策略之间分配搜索预算
   - 奖励信号：搜索结果是否导致后验显著变化

c) **推送粒度优化**：
   - 分析师是喜欢详细报告还是简短摘要？高频推送还是低频汇总？
   - 用 bandit 优化推送策略
   - 奖励信号：分析师是否点开、是否标注有用、是否忽略

```python
class CognitiveBandit:
    """Thompson Sampling 选择认知框架。"""
    def __init__(self, frames: list[str]):
        # 每个框架维护一个 Beta 分布
        self.alphas = {f: 1.0 for f in frames}  # 成功次数
        self.betas = {f: 1.0 for f in frames}   # 失败次数
    
    def select(self, n: int = 3) -> list[str]:
        """采样选择 n 个框架。"""
        samples = {f: np.random.beta(self.alphas[f], self.betas[f]) 
                   for f in self.alphas}
        return sorted(samples, key=samples.get, reverse=True)[:n]
    
    def update(self, frame: str, reward: float):
        """分析师反馈更新。"""
        self.alphas[frame] += reward
        self.betas[frame] += (1 - reward)
```

**实现成本**：中。Thompson Sampling 几十行代码，不需要训练模型。
但 reward signal 定义是前置工作——feedback_service 目前只收集 verdict（agree/disagree/need_more），
没有 outcome ground truth 追踪（反馈是否最终被证实正确）。
需要先在 `AssertionFeedback` 模型加 `outcome_verified` + `outcome_timestamp` 字段，
定义清楚什么算"正确"（分析师标注有用？事后验证准确？），bandit 才有可靠的奖励信号。
关键是 feedback_service 已经有反馈收集基础设施。

涉及文件：新增 `services/adaptive_bandit.py`（bandit 算法），
修改 `services/tournament.py`（认知框架选择用 bandit），
修改 `push_engine.py`（推送策略用 bandit）

### 探索四：多模态信号融合

**问题**：AEGI 目前只处理文本信号（新闻、报告、声明）。
但现实世界最可靠的信号往往不是文本——卫星图像、航运数据、金融时序、
社交媒体图片/视频。这些信号比新闻文本更难伪造、更实时、更客观。

**场景示例**：
黄金涨价，文本分析可能被媒体叙事误导。但如果同时看到：
- AIS 数据显示苏伊士运河通行量下降 40%（航运异常，数值信号）
- 卫星图像显示某国军事基地车辆密度增加（视觉信号）
- 某国央行黄金 ETF 持仓数据突增（金融信号）
这些是硬数据，不是媒体解读。和文本信号交叉验证，可靠性大幅提升。

**架构预留**：

a) Evidence 模型扩展：`contracts/schemas.py` 已有 `Modality` 枚举（TEXT/IMAGE/VIDEO/AUDIO）
   和 `SourceClaimV1.modality` 字段（含 `segment_ref`、`media_time_range`，目前未被使用）。
   扩展现有枚举而非新增字段：
   ```python
   class Modality(str, Enum):
       TEXT = "text"
       IMAGE = "image"
       VIDEO = "video"
       AUDIO = "audio"
       NUMERIC = "numeric"        # 新增：数值信号（价格、计数、比率）
       TIMESERIES = "timeseries"  # 新增：时序数据引用

   # SourceClaimV1 补充数值字段（与现有 modality 字段配合）
   numeric_value: float | None = None       # 数值（价格、计数、比率）
   numeric_context: str | None = None       # 数值含义（"苏伊士运河日通行量"）
   timeseries_ref: str | None = None        # 时序数据引用
   ```

b) DS 融合和贝叶斯更新不关心证据是文本还是数据，只关心 likelihood。
   不同类型的证据用不同的 likelihood 评估方法：
   - 文本：LLM 评估（现有）
   - 数值：统计检验（z-score、异常检测）
   - 时序：趋势分析 + Granger 因果

c) 候选数据源（均有公开 API）：

| 数据源 | 类型 | 信号 | API |
|--------|------|------|-----|
| MarineTraffic / AIS | 航运 | 船舶移动、港口拥堵 | 付费，有免费层 |
| Sentinel Hub | 卫星图像 | 军事活动、基础设施变化 | ESA 免费 |
| Yahoo Finance | 金融 | 商品价格、汇率、指数 | 免费 |
| FRED (美联储) | 经济 | 利率、通胀、就业 | 免费 |
| Flightradar24 | 航空 | 军机活动、航线变化 | 有限免费 |

**实现路径**：
- 短期（P-next-4）：先接入纯数值数据源（Yahoo Finance、FRED），成本低
- 中期：接入 AIS 航运数据，和 GDELT 交叉验证
- 长期：接入卫星图像，用视觉模型提取结构化信息

涉及文件：修改 `contracts/schemas.py`（SourceClaim 扩展），
新增 `services/numeric_evidence.py`（数值证据的 likelihood 评估），
各数据源 client 按需新增

### 探索五：对抗性模拟（War Gaming）

**问题**：锦标赛架构里所有 agent 都在"分析过去发生了什么"。
但情报分析最有价值的是"预测接下来会发生什么"。

**洞察**：美国情报界的 Red Team 分析方法——让分析师扮演对手，
从对手的视角推演下一步行动。这个方法可以用 LLM agent 自动化。

**方案**：

a) **行为体建模**：给定当前态势，为每个关键行为体创建一个 agent，
   注入该行为体的已知目标、约束、历史行为模式：
   ```
   Agent-某国政府：
     目标：维护政权稳定、扩大地区影响力
     约束：经济制裁压力、国内民意
     历史模式：倾向于渐进式升级，避免直接军事对抗
     当前态势：[注入最新情报]
     问题：你下一步最可能做什么？为什么？
   ```

b) **多方推演**：多个行为体 agent 同时推演，看它们的行动是否会产生连锁反应：
   - 某国政府 agent："我会增加军事演习频率"
   - 某国军方 agent："对方增加演习，我需要提高战备等级"
   - 某国央行 agent："地区紧张升级，我会增持黄金"
   → 系统发现：这个推演链条和当前观察到的信号（黄金涨价）吻合

c) **推演验证**：把推演结果作为假设注入锦标赛，和数据驱动的假设竞争。
   如果推演假设在贝叶斯更新后后验升高，说明推演有预测价值。

d) **预测生成**：推演不只解释过去，还预测未来。
   "如果当前趋势持续，3 周内最可能发生什么？"
   预测结果作为监测目标——如果预测的事件真的发生了，系统的可信度提升。

**与锦标赛架构的集成**：
- 推演结果作为一种特殊的"假设来源"进入锦标赛
- 推演 agent 和分析 agent 使用不同的 prompt 和工具
- 推演的预测作为 push_engine 的监测目标

**风险**：LLM 扮演行为体的准确性未经验证。
缓解：推演结果标记为"模拟推演"，不直接作为分析结论，
只作为假设来源和监测方向。

涉及文件：新增 `services/war_gaming.py`（行为体建模 + 多方推演），
修改 `services/tournament.py`（推演假设参与锦标赛），
修改 `push_engine.py`（推演预测作为监测目标）

### 探索六：分析的分析（Meta-Analysis of Analysis）

**问题**：当前系统擅长“分析事件”，但缺少“分析系统自身表现”的机制。
无法系统回答：为什么某阶段准确率下降？哪些场景存在过度自信？哪些数据源在持续误导？

**方案**：

a) 建立周期性“方法论审计任务”（日/周批处理）：
- 按 `scenario_type` 统计 Brier/ECE/误报率/漏报率/过度自信率
- 按认知框架统计边际贡献（与 Shapley/反馈对齐）
- 按数据源统计误导率与时效退化模式

b) 输出 `SystemHealthReportV1`（面向系统管理员，不面向业务分析师）：
- 能力看板：哪里稳定、哪里退化、退化幅度与置信区间
- 风险看板：高风险策略、失效规则、异常漂移
- 建议清单：参数调整候选（阈值、权重、预算分配）

c) 自动参数调整采用“受控自适应”：
- 仅允许在安全范围内小步调参（如阈值 ±5%）
- 任何超范围调整必须走 `Shadow Mode + Replay + 专家闸门`

**与 Shadow/Replay 的关系**：
- Meta-analysis 负责发现“应该改什么”
- Shadow/Replay 负责验证“改了是否真的更好”

涉及文件：新增 `services/meta_analysis.py`，新增 `contracts/schemas.py::SystemHealthReportV1`，
修改调度器（周级审计任务）

### 探索七：时间尺度分层引擎（Multi-Tempo Analysis）

**问题**：当前 pipeline 默认单时间尺度，难以同时满足“分钟级响应”和“月级结构性判断”。

**方案**：显式建立多时间尺度并行子引擎（不是同一 pipeline 改参数）：
- `T0 分钟级`：规则 + 轻量分类器，目标是低延迟告警
- `T1 天级`：事件追踪与证据补全
- `T2 周级`：NPMI/PCMCI 驱动趋势与因果信号
- `T3 月/季级`：KG 多跳 + 反事实 + 结构性评估

跨尺度信息流：
- 下行：月级结构假设为分钟级提供解释先验
- 上行：分钟级突发异常触发周/月级重评估
- 侧向：同尺度内部共享证据与不确定性

每层独立定义：
- 触发条件
- 分析方法
- 输出格式
- 预算上限

涉及文件：新增 `services/multi_tempo_orchestrator.py`，修改 `pipeline_orchestrator.py`
（支持多时间尺度并行编排与跨尺度消息）

### 探索八：情景推演树（Branching Futures）

**问题**：单点预测（一个概率）不足以支撑决策准备，决策者需要“分支未来”。

**方案**：将现有假设竞争扩展为“情景树”：
- 根节点：当前态势
- 第一层：主要情景（A/B/C）
- 后续层：条件分支（A1/A2，B1/B2...）

每个节点包含：
- `p(node)`：当前分支概率
- `drivers`：关键驱动因素
- `watch_signals`：监测指标（用于在线判别走向）
- `time_window`：预期时间窗

在线更新机制：
- 新证据到来后做贝叶斯更新，重排分支概率
- 输出“当前最可能路径 + 备选路径”

约束机制（防分支爆炸）：
- `top-k` 扩展（例如每层最多 3 个子分支）
- 最小概率剪枝（如 `< 0.1` 直接裁剪）
- 最大深度限制（如 2-3 层）

涉及文件：新增 `services/scenario_tree.py`，修改 `forecasting.py` 与 `contracts/schemas.py`
（分支化预测输出）

### 探索九：信息不对称建模（Opponent Information Set）

**问题**：当前分析几乎都从“我们知道什么”出发，缺少“对手知道什么”的结构化建模。

**方案**：建立“行为体信息集合模型”：
- `public_info`：公开信息（新闻/声明）
- `semi_public_info`：圈层可得信息（行业报告/泄露材料）
- `inferred_info`：由行为反推“对手可能已知”的信息

实现策略（分阶段）：
1. 先做一阶信念：`What they likely know`
2. 暂不做高阶无限递归信念（`I know that they know...`）
3. 将信息集合输入行为体策略推演，作为 war-gaming 的先验约束

输出用途：
- 提升行为预测一致性
- 识别“误判源于信息不对称”而非推理错误

涉及文件：新增 `services/opponent_modeling.py`，修改 `services/war_gaming.py`
（注入行为体信息集）

### 探索十：叙事竞争分析（Narrative Competition）

**问题**：系统目前偏事实链分析，缺少“叙事层”的竞争态势理解。

**方案**：建立叙事图谱与叙事-行动一致性分析：
- 识别各方叙事（防御/威慑/受害者/合法性等）
- 跟踪叙事演化（过去 7/30 天框架漂移）
- 建模叙事竞争关系（互斥/替代/包容）
- 计算叙事-行动一致性指数（言行一致/背离）

与 DISARM 的分工：
- DISARM：战术层（如何操纵信息）
- Narrative：战略层（想让谁相信什么）

定位：优先使用 LLM 进行语义框架识别，但关键结论必须回写证据链并与行为数据交叉验证。

涉及文件：新增 `services/narrative_competition.py`，
修改 `services/disarm_classifier.py`（增加叙事标签联动）

### 探索十一：知识半衰期建模（Knowledge Half-life）

**问题**：当前时间衰减虽已分级，但仍偏“证据类型驱动”，尚未升级为“知识类型驱动”。

**方案**：为不同知识类别定义独立半衰期与刷新策略：
- 军事部署：天级
- 制裁状态：月级
- 联盟关系：年级（带突变监测）
- 地理资源约束：多年级
- 领导人个人特质：任期级

从统一 gamma 升级为分层衰减：
- `freshness = exp(-ln(2) * delta_t / half_life(type, scenario))`
- 支持按场景动态校正半衰期参数

直接收益：
- 更精准的信息刷新调度
- 更稳定的长期推理前提管理
- 更可解释的不确定性来源标注

涉及文件：新增 `services/knowledge_half_life.py`，修改 `services/time_decay.py`
（接入知识类型半衰期）

### 探索十二：信息源主动培育（Source Portfolio Optimization）

**问题**：当前系统以“被动消费外部信息源”为主，缺少对信息源组合的主动优化。

**方案**：
- 建立主题级“覆盖率/冗余度/成本”三指标：
  - 覆盖率：某主题关键实体/关系被有效观测的比例
  - 冗余度：同质来源过度集中程度
  - 成本：单位有效证据的 token/API 成本
- 当覆盖率不足或冗余过高时，自动生成“信息源补盲任务”
- 对新来源做灰度接入与可信度冷启动评估（不直接进入核心证据链）

与 Active Evidence Acquisition 的分工：
- Active Evidence Acquisition：面向“单个 case”的主动采样
- Source Portfolio：面向“全局源组合”的长期优化

涉及文件：新增 `services/source_portfolio_optimizer.py`，
修改 `services/source_credibility.py`（接入来源组合质量指标）

### 探索十三：语言与文化偏见补偿（Language/Culture Bias Compensation）

**问题**：信息源语言分布失衡会引入系统性视角偏差，影响分析质量而不仅是“多语言功能”。

**方案**：
- 为每次分析记录语言分布与地区分布
- 定义偏见风险规则：
  - 如某单一语言来源占比 > 80%，触发 `language_bias_risk`
- 自动触发非主导语言补偿采样（按场景匹配语言池）
- 在报告中显式披露“语言覆盖与偏置风险”

涉及文件：新增 `services/language_bias_monitor.py`，
修改 `services/investigation_agent.py`（补偿采样策略）

### 探索十四：沉默信号检测（Silence/Absence Signals）

**问题**：系统主要捕捉“发生了什么”，但“没有发生什么”在情报场景常是关键信号。

**方案**：
- 为实体/关系建立行为基线：
  - 发言频率、数据发布时间、双边互动频率、事件量节奏
- 监测“显著缺失/异常沉默”并量化强度：
  - `silence_score = deviation_from_baseline * duration_weight`
- 区分沉默与采集故障：
  - 数据源健康检测失败时不触发沉默结论

涉及文件：新增 `services/silence_detector.py`，
修改 `services/gdelt_monitor.py` 与采集健康检查模块

### 探索十五：因果链脆弱性分析（Causal Fragility Analysis）

**问题**：Shapley 解释来源贡献，但不能回答“哪个链路断裂会导致结论坍塌”。

**方案**：
- 对关键结论抽取因果依赖链并做脆弱性扫描：
  - 最长关键链
  - 单点薄弱环节（低置信/单来源/未验证）
- 做“关键环节移除”敏感性分析：
  - 移除后重新计算结论置信度降幅
- 输出 `fragility_report`：
  - `critical_link`
  - `confidence_drop_if_removed`
  - `recommended_verification_action`

涉及文件：新增 `services/causal_fragility.py`，
修改 `services/bayesian_ach.py`（支持链路级敏感性重算）

### 探索十六：分析师网络效应（Analyst Collective Intelligence）

**问题**：当前反馈机制主要按单分析师处理，未利用多分析师群体行为信号。

**方案**：
- 引入群体反馈聚合：
  - 一致性、分歧度、跨分析师独立支持度
- 分析师信誉加权：
  - 按历史命中率/校准质量动态调整反馈权重
- 反从众约束：
  - 多数意见不自动覆盖少数高质量反例

涉及文件：新增 `services/analyst_network_model.py`，
修改 `services/feedback_service.py`（群体反馈聚合）

### 探索十七：主动预期管理（Reliability Disclosure）

**问题**：仅输出置信度不足以建立长期信任，系统需主动声明“何时不可靠、为何不可靠”。

**方案**：
- 输出“可靠性声明卡”（Reliability Card）：
  - 当前结论可靠性等级
  - 主要不确定性来源
  - 与外部锚点（预测市场/历史基准）偏差
- 高风险场景主动告警：
  - 信息污染风险
  - 场景外推风险
  - 模型失配风险
- 周期发布“系统局限性报告”

涉及文件：新增 `services/reliability_disclosure.py`，
修改 `push_engine.py` 与报告渲染层

### 探索十八：对手分析系统逆向建模（Adversary Analytics Modeling）

**问题**：若对手也使用 AI 分析系统，仅从“我们视角”分析会低估博弈层风险。

**方案**（先粗粒度）：
- 估计对手可观测公开信息集合
- 模拟“对手系统可能得出的结论分布”
- 估计其可能决策并与我方结论对齐比对
- 输出“对手视角风险提示”

边界：
- 先做一阶近似，不做高复杂度精确仿真
- 作为决策辅助，不直接替代主分析结论

涉及文件：新增 `services/adversary_modeling.py`，
修改 `services/war_gaming.py`（接入对手推理视角）

### 探索十九：分析产品化（Audience-Specific Products）

**问题**：单一报告模板无法覆盖决策者、专家、行动团队、审计人员的不同需求。

**方案**：
- 按受众分层输出产品：
  - 决策者：一页摘要 + action + 风险/收益
  - 领域专家：完整推理链 + 证据矩阵 + 替代假设
  - 行动团队：实时态势 + 触发条件 + 监测指标
  - 审计人员：全链路溯源 + 决策日志 + 偏误检测
- 同一分析结果，多视图渲染（不是复制四份独立报告）
- 对外输出默认最小必要信息，内部视图保留完整细节

涉及文件：新增 `services/report_productizer.py`，
修改 API 报告路由与前端渲染契约

### 探索二十：意图推断（Intent Inference）

**问题**：事实分析回答“发生了什么”，但决策真正需要“行为体为什么这么做”。

**方案**：
- 显示性偏好：优先看行动而非表态，计算言行一致性分数
- 成本信号：以“行为体愿意支付的真实成本”反推意图强度
- 选项排除：建模可选行动集，分析“为何选 A 而非 B/C/D”
- 历史偏离：与历史同类情境对比，偏离程度作为意图变更信号

实现原则：
- LLM 只负责生成候选意图叙事
- 结构化证据（成本、约束、历史模式）负责筛选与加权
- 输出 `intent_hypotheses`（含可证伪信号与时间窗）

涉及文件：新增 `services/intent_inference.py`，
修改 `services/war_gaming.py` 与 `services/hypothesis_engine.py`（接入意图假设）

### 探索二十一：未知之未知压缩（Unknown-Unknown Compression）

**问题**：系统可量化“已知不确定性”，但难以发现“我不知道我不知道什么”。

**方案**：
- 维度覆盖率审计：按主题检查军事/经济/内政/外交/技术等维度覆盖度
- 历史类比缺口：当前 case 与历史相似 case 的维度差异
- 外部锚点差异：与预测市场/智库/外部系统关注维度做差分

输出：
- `blind_spot_report`：可能遗漏维度、置信等级、补盲优先级
- 将高优先级盲点转为主动采样任务（对接 Active Evidence Acquisition）

涉及文件：新增 `services/coverage_auditor.py`，
修改 `services/meta_analysis.py`（加入盲点评估）

### 探索二十二：时间压力模式切换（Time-Pressure Modes）

**问题**：现实决策受时限约束，当前深度分级未显式建模“可用时间”。

**方案**：定义按时限切换的分析模式（不是简单跳步骤）：
- `T-5m`：快速风险卡（最可能解释 + 最大风险 + 立即行动）
- `T-1h`：简化 pipeline + 小规模对抗验证
- `T-1d`：完整 pipeline
- `T-1w`：完整锦标赛 + 反事实 + 情景树

关键约束：
- 危机模式优先复用常驻 agent 记忆与现有态势缓存
- 每种模式独立定义：允许方法、预算上限、输出模板、置信声明

涉及文件：新增 `services/time_pressure_router.py`，
修改 `pipeline_orchestrator.py`（按时限策略路由）

### 探索二十三：针对系统的欺骗检测（System-Targeted Deception Defense）

**问题**：现有机制可识别一般信息操作，但不足以识别“专门骗 AEGI”的对抗输入。

**方案**：
- 伪独立源检测：来源在措辞/时序/细节过度同步时上调可疑度
- 信息论异常：监控事件流熵分布与语义重复度异常
- 对抗探针：在受控环境执行蜜罐测试，识别针对性利用模式
- 结果门控：高可疑证据不得直接进入高置信裁决链路

涉及文件：新增 `services/deception_defense.py`，
修改 `services/coordination_detector.py` 与质量门控模块

### 探索二十四：认知惯性检测（Cognitive Inertia Control）

**问题**：常驻 agent 长期运行后会形成路径依赖，导致先验与记忆污染后续结论。

**方案**：
- 归零对照：定期用“空白 agent”对同题并行分析
- 先验敏感性分析：扰动先验，观察结论翻转阈值
- 记忆消融实验：部分移除历史记忆，评估结论稳定性
- 计算 `inertia_score`，超阈值触发先验重置/记忆审计

涉及文件：新增 `services/inertia_monitor.py`，
修改 `services/analysis_memory.py` 与 `services/tournament.py`

### 探索二十五：协作情报交换协议（Collaborative Intelligence Exchange）

**问题**：单实例闭环会限制系统边界，跨组织协作需要标准化“分析交换”能力。

**方案**：
- 先交换“结论级工件”，不交换原始敏感数据
- 可交换对象：
  - 结论摘要与置信区间
  - 校准参数与偏差告警
  - 本体扩展提案与红队场景
- 定义交换契约（版本、签名、溯源、可撤销）

边界：
- 优先做同构系统之间的最小互操作
- 默认零信任，外部输入必须走本地验证与隔离

涉及文件：新增 `contracts/intel_exchange.py` 与 `services/intel_exchange_gateway.py`

### 探索二十六：人类专家能力的机器化

人类专家团队最强的六个能力及其机器化路径：

| 人类能力 | 机器化方案 | 实现路径 |
|---------|----------|---------|
| 直觉（经验压缩） | 场景识别器 | 分析经验 -> 特征提取 -> 场景分类器 |
| 叙事能力 | 受众自适应叙事生成 | LLM 叙事层 + 受众模型 |
| 关系网络 | 专家能力图谱 + 主动咨询 | 反馈数据 -> 领域准确率 -> 定向推送 |
| 跨域类比 | 因果图结构匹配 | 因果图 -> 部分同构 -> 历史轨迹迁移 |
| 框架元认知 | 框架适配评估 + 自动切换 | 框架-问题匹配模型 + PiEvo |
| 政治敏感度 | 策略可行性过滤器 | 专家约束规则 + 约束内搜索 |

### 探索二十七：自我进化闭环

系统自动驱动变强的闭环：
- 自我诊断：元分析按场景/领域/时间切片识别短板
- 原因定位：脆弱性分析 + Shapley 定位薄弱环节
- 改进计划：自动规划参数调整、数据补采、框架修订
- 验证上线：Shadow/Replay 验证后再晋升

### 探索二十八：反事实推理标准化

反事实从“可选工具”升级为“标准输出”：
- 每个关键结论附“关键前提失效时结论变化”
- 每个策略建议附“不执行时反事实基线”
- 每个历史预测附“反事实回顾”
- 推断必须标注识别条件状态（满足/不满足/未知）

### 探索二十九：战略注意力分配器

系统级资源分配（战略层）：
- 输入：全局态势、资源预算、用户优先级
- 输出：领域/话题资源比例
- 目标函数：按边际信息增益分配，不按事件数量分配
- 与 Budget Market 关系：战略层（注意力）指导战术层（token）

### 探索三十：预测窗口（Predictive Attention Windows）

预测“何时需要重点关注”：
- 维护全球事件日历（选举、峰会、协议到期等）
- 基于历史模式识别高风险时间窗口
- 自动上调监测频率与分析深度
- 高关注话题预计算假设框架和关键指标

### 探索三十一：隐含关系发现（KG Dark Matter）

发现“无显式边但高行为相关”的隐藏关系：
- 系统扫描实体对的异常相关与时滞影响
- 结合 NPMI + PCMCI + 图模式检测发现候选关系
- 关系先进入候选本体，经验证再晋升核心本体

### 探索三十二：认知多样性量化保障

防止多 agent 退化为单一视角：
- 量化：假设集 Jaccard 距离 + 错误相关性双指标
- 强制：同质化触发配置重采样（prompt/工具/模型）
- 结构异构：不同 agent 使用不同推理范式（贝叶斯/类比/博弈等）
- 多模型对冲：不同 agent 绑定不同 LLM 以降低同源偏见

### 探索三十三：世界模型主动刷新

防止“世界观过时”：
- 季度因果图压力测试（近期数据重跑关键边）
- 本体过期扫描（长期未引用实体/关系）
- 模式库有效性验证（近期匹配率与收益）
- 检测到结构性漂移时触发世界模型重建

### 探索三十四：信息时效性竞赛

构建时间优势：
- 接入更实时源（流式社媒/频道/事件流）
- 分层处理：秒级初筛 + 分钟级深度分析
- 高关注主题预计算，减少从零分析开销
- 跟踪端到端延迟并持续优化

### 探索三十五：可证伪性追踪

每个关键判断自动生成证伪条件并跟踪：
- 条件模板：“若 X 天内未出现 Y，则削弱假设 H”
- 到期自动验证并调整后验
- 统计“高证伪率判断类型”，提高证据门槛

### 探索三十六：行动执行层

从“建议做什么”到“能做的先做”：
- 策略建议拆解为自动执行子任务与人工待办
- 自动执行示例：调监测频率、跑验证查询、生成通报草稿
- 人工任务示例：审批、外交动作、组织级协同决策

### 探索三十七：全局战略视图

从单 Case 走向全局态势：
- 汇总所有 case 的后验、趋势、风险等级
- 识别跨 case 系统性变化与联动链
- 输出全局态势仪表盘（热度、趋势、关联、风险排名）

### 探索三十八：学习迁移

跨领域方法论迁移：
- 分离“领域知识”与“领域无关方法论”
- 将高价值方法论自动迁移到新领域
- 利用结构类比辅助迁移起步

### 探索三十九：LLM 能力边界动态感知

系统内部显式管理 LLM 能力边界：
- 按任务类型追踪历史可靠性曲线
- 低可靠任务自动降权并增强验证
- LLM 与结构化方法冲突时按任务策略仲裁
- 模型版本升级后自动重评估边界

### 探索四十：黑天鹅应急模式

面向无历史先例事件：
- 联合异常触发“未知态势”告警
- 切换应急模式：历史权重降级 + 实时证据优先 + 人工闸门
- 快速构建临时因果图与临时分析框架
- 事后复盘更新阈值与应急策略

### 探索四十一：系统性偏见审计

检测并补偿方向性偏见：
- 控制实验：同场景替换实体名，比较输出差异
- 对差异做显著性检验并生成偏见画像
- 在相关任务中自动应用偏见补偿权重

### 探索四十二：信息过载防护

避免“噪声放大”拖垮系统：
- pipeline 入口轻量过滤（信息量、重复度、源质量）
- 与战略注意力分配协同（先选领域，再选信息）
- 召回保护抽检回流，防止弱信号被误删

### 探索方向优先级与实施建议

**基础五方向（既有）**

| 方向 | 价值 | 实现难度 | 建议阶段 | 依赖 |
|------|------|---------|---------|------|
| 预测市场校准锚点 | 高 | 极低（~200行） | P-next-2 可选扩展 | 无 |
| KG 多跳推理 | 高 | 中 | P-next-3 或 P-next-5 | Neo4j 数据积累 |
| 分析师反馈 Bandit | 高 | 低（~100行） | P-next-4 | feedback 数据积累 |
| 多模态信号融合 | 很高 | 高 | P-next-4 数值先行，长期扩展 | 数据源接入 |
| 对抗性模拟 | 很高 | 高 | P-next-5 扩展 | 行为体知识库 |

**新增六方向（6-11）**

| 方向 | 价值 | 实现难度 | 建议阶段 | 依赖 |
|------|------|---------|---------|------|
| 探索六：元分析能力 | 很高 | 中 | P-next-6 | Shadow/Replay、反馈闭环 |
| 探索七：时间尺度分层 | 很高 | 中高 | P-next-6+ | 多时间尺度编排能力 |
| 探索八：情景推演树 | 高 | 中高 | P-next-6+ | forecast + 贝叶斯更新 |
| 探索九：信息不对称建模（一阶） | 高 | 高 | P-next-6+ 后半段 | 行为体建模、证据分层 |
| 探索十：叙事竞争分析 | 很高 | 中 | P-next-6+ | LLM 语义抽取 + 行为数据对齐 |
| 探索十一：知识半衰期模型 | 很高 | 中 | P-next-6 | time_decay + 场景分层参数 |

**新增八方向（12-19）**

| 方向 | 价值 | 实现难度 | 建议阶段 | 依赖 |
|------|------|---------|---------|------|
| 探索十二：信息源主动培育 | 很高 | 中高 | P-next-6+ | source_credibility、采集编排 |
| 探索十三：语言与文化偏见补偿 | 很高 | 中 | P-next-6+ | 多语言采样与语言识别 |
| 探索十四：沉默信号检测 | 很高 | 中 | P-next-6 | 行为基线 + 数据源健康监控 |
| 探索十五：因果链脆弱性分析 | 很高 | 中 | P-next-6 | 因果链抽取 + 贝叶斯重算 |
| 探索十六：分析师网络效应 | 高 | 中高 | P-next-6+ | 多分析师反馈数据积累 |
| 探索十七：主动预期管理 | 很高 | 低中 | P-next-6 | meta-confidence + 校准输出 |
| 探索十八：对手分析系统逆向建模 | 高 | 高 | P-next-6+ 后半段 | war-gaming + 信息不对称建模 |
| 探索十九：分析产品化 | 很高 | 中 | P-next-6 | Decision Layer + 报告渲染层 |

**新增六方向（20-25）**

| 方向 | 价值 | 实现难度 | 建议阶段 | 依赖 |
|------|------|---------|---------|------|
| 探索二十：意图推断 | 很高 | 中高 | P-next-6+ | 行为体建模 + 成本信号抽取 |
| 探索二十一：未知之未知压缩 | 很高 | 中 | P-next-6 | meta-analysis + 外部锚点 |
| 探索二十二：时间压力模式切换 | 很高 | 中 | P-next-6 | 常驻 agent 记忆 + 编排路由 |
| 探索二十三：针对系统的欺骗检测 | 很高 | 高 | P-next-6+ | 反欺骗检测 + 质量门控 |
| 探索二十四：认知惯性检测 | 很高 | 中 | P-next-6 | memory + 先验敏感性分析 |
| 探索二十五：协作情报交换协议 | 高 | 高 | P-next-6+ 后半段 | 交换契约 + 零信任验证 |

**新增方向（探索二十六至四十二）**

| 方向 | 价值 | 实现难度 | 建议阶段 | 依赖 |
|------|------|---------|---------|------|
| 探索二十六：人类专家能力机器化 | 很高 | 高 | P-next-6+ | 因果图 + 常驻 agent + 反馈数据 |
| 探索二十七：自我进化闭环 | 很高 | 中高 | P-next-6+ | 元分析 + Shapley + Shadow |
| 探索二十八：反事实推理标准化 | 很高 | 中 | P-next-6 | DoWhy + 因果图 |
| 探索二十九：战略注意力分配器 | 很高 | 中高 | P-next-6+ | 常驻 agent + 全局态势 |
| 探索三十：预测窗口 | 高 | 中 | P-next-6 | 事件日历 + 历史模式 |
| 探索三十一：隐含关系发现 | 很高 | 中高 | P-next-6+ | NPMI + PCMCI + KG |
| 探索三十二：认知多样性量化 | 很高 | 中 | P-next-5 扩展 | 锦标赛架构 |
| 探索三十三：世界模型主动刷新 | 很高 | 中 | P-next-6 | 因果图 + 本体 + 模式库 |
| 探索三十四：信息时效性竞赛 | 高 | 中高 | P-next-6+ | 实时数据源接入 |
| 探索三十五：可证伪性追踪 | 很高 | 中 | P-next-6 | 预测校验 + 假设管理 |
| 探索三十六：行动执行层 | 高 | 中 | P-next-6+ | Decision Layer |
| 探索三十七：全局战略视图 | 很高 | 中高 | P-next-6+ | 多 Case 数据 + 态势模型 |
| 探索三十八：学习迁移 | 很高 | 高 | P-next-6+ | 方法论/知识分离 |
| 探索三十九：LLM 能力边界感知 | 很高 | 中 | P-next-6 | 历史准确率追踪 |
| 探索四十：黑天鹅应急模式 | 很高 | 中 | P-next-6 | 异常检测 + 应急编排 |
| 探索四十一：系统性偏见审计 | 很高 | 中 | P-next-6 | 控制实验框架 |
| 探索四十二：信息过载防护 | 高 | 低中 | P-next-5 扩展 | 轻量分类器 |

说明：
- 探索二十六至三十二的能力已分别纳入 `P-next-6.4` 与 `P-next-6.5` 的主章节设计；
- 探索四十至四十二已纳入 `P-next-6.6` 的主章节设计；
- 为避免重复定义，这里仅保留探索编号索引，不再重复列同名能力表。

**探索方向能力域聚类（42 -> 6 域）**

| 能力域 | 包含探索 | 核心问题 |
|--------|----------|----------|
| 自我认知与校准 | 6、11、15、17、21、24、35、39、41 | 系统知道自己有多可靠 |
| 决策与行动 | 19、22、29、30、36、37 | 从分析到行动的闭环 |
| 对抗与防御 | 5、9、18、23、40、42 | 抵抗欺骗与极端场景 |
| 认知增强 | 2、7、8、10、20、26、28、31、38 | 更深更广的推理能力 |
| 人机协作 | 3、12、13、16、25 | 人类与系统协同增益 |
| 系统进化 | 1、4、27、32、33、34 | 系统持续变强与自适应 |

**建议实施顺序（综合）**：
1. 探索六 + 探索十一 + 探索十四 + 探索十五 + 探索十七 + 探索二十一 + 探索二十四（先补齐“自我认知 + 时效 + 脆弱性 + 可靠性 + 盲点 + 惯性”底座）
2. 探索十九 + 探索二十二（把能力转化为产品，并支持危机时限模式切换）
3. 探索七 + 探索十 + 探索二十 + 探索二十六（建立多时间尺度、意图推断与“专家优势映射”主干）
4. 探索八（从单点预测升级到分支推演树）
5. 探索十三 + 探索十二 + 探索十六 + 探索二十六（偏见补偿、源组合优化、群体校准）
6. 探索九 + 探索十八 + 探索二十三 + 探索三十一（最后引入高复杂度对手信息、系统级反欺骗与暗物质关系）
7. 探索二十七 + 探索二十八 + 探索三十二（进入系统自驱动进化阶段）
8. 探索二十九 + 探索三十（形成战略级资源协调与前瞻监测）
9. 探索四十 + 探索四十一 + 探索四十二（确保极端场景下系统可控与可恢复）
10. 探索二十五 + 探索二十六（结构类比与策略可行性过滤，推进跨系统协作与高复杂策略能力收敛）
11. 同步推进既有低成本增益项：预测市场锚点、Bandit 优化

---

## 完整路线图总览

```
已完成：基础设施 → 报告 → KG增强 → OSINT → 流式 → 事件驱动 → 本体升级 → 调研Agent

P-next-1（底座修复 + 成本控制）
  ├─ LLM 并行化（串行深度 `1 + N*(1+3)` → 约 3 层）
  ├─ 采样置信度（关键判断跑 3 次）
  ├─ ACH 一致性校验（规则检测逻辑矛盾）
  ├─ grounding 强制执行
  ├─ LLMCallManager 统一抽象层（并行/采样/预算/日志/降级）
  ├─ 全局 token/cost budget 管理器
  └─ LLM 判断日志收集启动（为 P-next-4 蒸馏积累数据，零成本）

P-next-2（校准 + 检索 + 关联 + 因果发现）
  ├─ Platt scaling 概率校准
  ├─ RAG 式历史分析检索（增强现有分析记忆）
  ├─ NPMI 异常检测 + LLM 驱动交叉关联（重构现有引擎）
  └─ tigramite PCMCI 时序因果发现（集成到 likelihood 评估）

P-next-3（辩论 + DISARM + Shapley + 元评估）
  ├─ assertion_debate stage + 轻量 2-agent 辩论（高争议 assertion）
  ├─ DISARM 信息操作分类标签
  ├─ Shapley 置信度分解
  └─ 场景级自信度元评估（meta-confidence）

P-next-4（蒸馏 + 数据源扩展）
  ├─ 轻量分类器替代高频 LLM 调用（基于 P-next-1 积累的判断日志）
  └─ 多维数据源接入（ACLED / World Bank / ICEWS / UN Comtrade）

P-next-5（自主分析循环：Generate-Debate-Evolve 锦标赛架构）
  ├─ 多 Agent 独立探索（3-5 个不同认知框架的 OpenClaw agent，探索阶段内存隔离）
  ├─ 常驻专家 agent 网络（cron + heartbeat + memory，持续巡检）
  ├─ 锦标赛辩论（假设两两竞争，AEGI 贝叶斯做裁判，agent 失败优雅降级）
  ├─ 信息增益驱动搜索（启发式近似，数学指导搜索方向）
  ├─ 时间衰减 + 概念漂移检测（gamma 按证据类型分级，证据过期自动刷新）
  └─ 假设集完整性保障（异常驱动发现 + 红队注入 + H0 元认知循环）

P-next-6（智能化上限扩展：从分析准确率到决策收益）
  ├─ Decision Layer（VOI + action recommendation）
  ├─ Expert Feedback Compiler（专家纠正编译为可执行约束）
  ├─ 动态本体治理（Core/Candidate 分层 + 选择性专家晋升闸门）
  ├─ Active Evidence Acquisition（主动证据采样）
  ├─ Unified Relation Graph（关联/因果/KG 融合）
  ├─ 图数学优先路径（图扩散/概率图/因果先行，GNN 后置）
  ├─ 反应式 -> 策略式范式升级（推理循环 + 策略搜索 + 持续博弈）
  ├─ 人类优势映射层（直觉/叙事/咨询/类比/框架元认知/可行性过滤）
  ├─ 自进化与战略协调层（自我进化 + 反事实主化 + 注意力分配 + 多样性保障）
  ├─ 极端不确定性与质量防护层（黑天鹅应急 + 偏见审计 + 过载防护）
  ├─ Compute Budget Market（多 agent 动态预算分配）
  └─ Shadow Mode + Replay（影子评估与历史回放）
      ├─ 6A：决策底座与安全发布（Decision + Feedback + Shadow + Unified Graph）
      ├─ 6B：策略推理主链（P-next-6.3）
      ├─ 6C：人类优势映射与自进化（P-next-6.4 + P-next-6.5）
      └─ 6D：极端鲁棒性（P-next-6.6）
```

跨阶段依赖：
- P-next-1 的判断日志 → P-next-4 的蒸馏训练数据
- P-next-1 的 LLMCallManager → P-next-1/2/3 的采样、并行、预算与审计统一
- P-next-1 的 TokenBudgetManager → P-next-5 的多 agent 成本控制
- P-next-1 的采样一致率 → P-next-3 的 meta-confidence 信号之一
- P-next-2 的校准层 + 历史检索 → P-next-3 的元评估
- P-next-2 的校准层 → P-next-5 的贝叶斯裁判概率校准
- P-next-2 的 NPMI 异常检测 → P-next-5 的锦标赛触发条件之一
- P-next-2 的 PCMCI → P-next-4 的 ACLED 数据可消除 GDELT 媒体混淆
- P-next-2 的 PCMCI → P-next-5 的信息增益计算（因果图辅助）
- P-next-3 的 Shapley 分解 → P-next-5 的辩论结果可解释性
- P-next-3 的 meta-confidence → P-next-5 的收敛判断 + H0 元认知循环
- P-next-4 的蒸馏分类器 → P-next-5 降低多 agent LLM 调用成本
- P-next-4 的多数据源 → P-next-5 的 agent 工具丰富度
- P-next-5 的常驻专家网络 → P-next-6 的反馈编译与决策层（长期知识沉淀）
- P-next-2/3 的 KG + 贝叶斯 + 因果基础 → P-next-6 的图数学优先路径
- P-next-2/3 的因果图识别能力 → P-next-6.3 的干预推断与策略评估门禁
- P-next-5 的持续监测与记忆积累 → P-next-6.3 的时间压力模式与滚动策略搜索
- P-next-1~5 的历史分析日志与失败分类库 → P-next-6.4 的场景识别器与经验压缩
- 探索十九（产品化）+ 探索十六（分析师网络效应） → P-next-6.4 的叙事层与主动咨询
- 探索六（元分析）+ Replay 基础设施 → P-next-6.5 的自我进化闭环
- P-next-6.3 因果骨架 + DoWhy → P-next-6.5 的反事实主化能力
- Compute Budget Market（战术层）→ P-next-6.5 战略注意力分配器（战略层）
- 探索二十二（时间压力）+ 元分析漂移监控 → P-next-6.6 黑天鹅应急模式
- 多模型对冲 + 语言文化补偿 → P-next-6.6 系统性偏见审计
- 战略注意力分配器（选领域）+ 入口过滤器（选信息）→ P-next-6.6 过载防护
- ontology_versioning 的版本化能力 → P-next-6 的动态本体治理（提案晋升/回滚）
- P-next-6 的 Shadow Mode + Replay → 所有后续策略升级的安全发布机制
- P-next-6 的 Shadow Mode + Replay + 反事实基线 → P-next-6.3 的策略效果归因

演进逻辑：
  P-next-1~3 让系统"更准"（质量驱动）
  P-next-4 让系统"更便宜"（成本驱动）
  P-next-5 让系统"更像机构"（持续驱动）——从任务态 agent 升级为常驻专家网络
  P-next-6 让系统"更智能"（决策驱动）——从分析结论走向行动建议与策略闭环
  P-next-6+ 让系统"超越人"（全域驱动）——突破文本边界，多模态+推演+自适应

远景探索方向（P-next-6+，按优先级）：
  ├─ 元分析能力（分析系统自身表现，驱动参数与策略自适应）
  ├─ 知识半衰期模型（按知识类型建模过期速度，提升刷新与前提管理）
  ├─ 沉默信号检测（识别“未发生事件”的异常价值）
  ├─ 因果链脆弱性分析（定位结论最易坍塌环节）
  ├─ 主动预期管理（可靠性声明 + 局限性主动披露）
  ├─ 未知之未知压缩（覆盖率审计 + 类比缺口 + 外部锚点差分）
  ├─ 认知惯性检测（归零对照 + 先验敏感性 + 记忆消融）
  ├─ 场景识别器与经验压缩（机器化“直觉”快速路由）
  ├─ 受众自适应叙事层（Truth/Narrative 分层表达）
  ├─ 专家能力图谱与主动咨询路由（知道“该问谁”）
  ├─ 结构类比引擎（因果图部分同构 + 角色映射）
  ├─ 框架元认知（框架适配评估 + 自动切换/组合）
  ├─ 策略可行性过滤器（政治/组织/时机约束前置）
  ├─ 自我进化闭环（系统自主诊断短板并驱动改进）
  ├─ 反事实主化（关键结论与策略默认附反事实对照）
  ├─ 战略注意力分配器（领域级资源按边际价值分配）
  ├─ 关注窗口预测器（提前识别高风险时间窗口）
  ├─ 隐含关系发现器（扫描无显式边但高行为相关关系）
  ├─ 认知多样性量化保障（距离 + 错误相关双指标）
  ├─ 黑天鹅应急模式（结构性异常触发的应急推理与人工闸门）
  ├─ 系统性偏见审计（对照实验 + 显著性检验 + 偏见补偿）
  ├─ 信息过载防护（入口信息量过滤 + 召回保护抽检）
  ├─ 行动执行层（策略建议自动拆解为可自动执行与人工待办）
  ├─ 全局战略视图（跨 Case 态势聚合与系统性联动检测）
  ├─ 学习迁移（领域无关方法论跨区域迁移复用）
  ├─ LLM 能力边界动态感知（按任务类型动态加权与冲突仲裁）
  ├─ 分析产品化（按受众输出决策版/专家版/行动版/审计版）
  ├─ 时间压力模式切换（5分钟/1小时/1天/1周的策略路由）
  ├─ 时间尺度分层引擎（分钟/天/周/月并行分析，跨尺度信息流）
  ├─ 叙事竞争分析（叙事图谱 + 叙事-行动一致性）
  ├─ 意图推断（显示性偏好 + 成本信号 + 选项排除 + 历史偏离）
  ├─ 情景推演树（分支未来 + 在线分支概率更新）
  ├─ 语言与文化偏见补偿（多语言覆盖 + 偏置风险告警）
  ├─ 信息源主动培育（覆盖率/冗余度/成本的源组合优化）
  ├─ 分析师网络效应（多分析师群体智慧聚合与分歧建模）
  ├─ 信息不对称建模（一阶“对手知道什么”）
  ├─ 针对系统的欺骗检测（识别伪独立源与信息流对抗注入）
  ├─ 对手分析系统逆向建模（粗粒度估计“对手AI如何看我们”）
  ├─ 协作情报交换协议（结论级互换 + 校准/本体/红队场景交换）
  ├─ 预测市场校准锚点（极低成本，P-next-2 可选扩展）
  ├─ 分析师反馈 Bandit 优化（低成本，P-next-4 扩展）
  ├─ KG 多跳推理辅助假设生成（中等成本，P-next-5 扩展）
  ├─ 多模态信号融合（数值先行→航运→卫星，渐进扩展）
  └─ 对抗性模拟 War Gaming（行为体建模+多方推演+预测验证）

---

## 执行治理层（Execution Governance）

前述 P-next-1 ~ P-next-6 和横切面给出了“能力怎么做”。本节补齐“工程如何持续可执行”：
失败分类、成本约束、基准评估、飞轮量化、统一降级、阶段过渡闸门。

### 附录 A：失败分类学（Failure Taxonomy）

目标：把“失败”从个案复盘升级为标准化对象，驱动红队测试与运行时监控。

| failure_id | 失败类型 | 定义 | 主检测信号 | 主防御机制 | 对应模块 |
|------------|----------|------|------------|------------|----------|
| F-01 | 遗漏型失败 | 正确假设未进入候选集 | H0 后验持续升高、孤儿证据占比升高 | 假设集完整性保障、异常驱动发现 | hypothesis_discovery / metacognitive_loop |
| F-02 | 误判型失败 | 错误假设被选为最优 | 事后真值偏差、后验排序翻转 | 校准层、辩论、Shapley 解释 | bayesian_ach / assertion_debate |
| F-03 | 延迟型失败 | 判断正确但时效失效 | 检出滞后、决策窗口错过率 | 时间压力模式、多 tempo 引擎 | time_pressure_router / multi_tempo_orchestrator |
| F-04 | 过度自信型失败 | 置信度显著高于实际命中率 | ECE/Brier 退化、置信-命中差扩大 | Platt 校准、meta-confidence | calibration / confidence_scorer |
| F-05 | 级联型失败 | 上游错误引发链式误判 | 单点移除后结论大幅坍塌 | 因果链脆弱性分析、反事实归因 | causal_fragility / reasoning_trace |
| F-06 | 沉默型失败 | 系统未意识到应分析对象 | 覆盖率异常低、静默事件漏检 | 沉默信号检测、覆盖率审计 | silence_detector / coverage_auditor |
| F-07 | 对抗型失败 | 被针对性欺骗输入误导 | 伪独立源同步、熵异常 | System-targeted deception defense | deception_defense / coordination_detector |
| F-08 | 退化型失败 | 系统长期变差且未自知 | 滚动窗口性能下降、惯性分数升高 | 元分析、认知惯性检测 | meta_analysis / inertia_monitor |
| F-09 | 黑天鹅型失败 | 超出历史模式导致推理链整体失效 | 多信号同向异常偏离、历史匹配率骤降 | 黑天鹅应急模式 + 临时因果图 | black_swan_router / emergency_orchestrator |
| F-10 | 偏见型失败 | 方向性偏见导致系统性误判 | 对照实验显著偏差、跨实体输出不对称 | 偏见审计 + 偏见补偿 | bias_audit / bias_compensation |

落地要求：
- 每个 failure_id 必须绑定测试场景（红队）与线上监控指标（运行时）。
- 每次重大事故复盘必须归类到一个或多个 failure_id，更新分类库。

### 附录 B：成本模型框架（Cost Model Framework）

目标：让 TokenBudgetManager 和 Budget Market 有明确优化目标，不再凭经验控成本。

**统一成本口径**
- `cost_per_case(mode)`：单 case 成本（按模式：T-5m/T-1h/T-1d/T-1w）
- `cost_per_tournament_round`：单轮锦标赛成本
- `cost_per_day_resident_agents`：常驻 agent 日成本
- `cost_per_month_total`：系统月总成本（模型调用 + 数据源 API + 存储计算）

**估算公式（首版）**
```text
cost_per_case = Σ(model_calls_i * unit_price_i) + tool_api_cost + infra_allocated_cost
monthly_total = case_volume * avg_cost_per_case + resident_agents_daily_cost * 30 + fixed_infra
```

**阶段成本台账（必填）**

| 指标 | P-next-1~3 | P-next-4 | P-next-5 | P-next-6 |
|------|------------|----------|----------|----------|
| 单次完整分析成本（token） | 估算 | 估算 | 估算 | 估算 |
| 月度常驻 agent 成本 | N/A | N/A | 估算 | 估算 |
| 锦标赛单轮成本 | N/A | N/A | 估算 | 估算 |
| 月度总运行成本 | 估算 | 估算 | 估算 | 估算 |

### 附录 C：评估基准（Benchmark）

目标：指标不只“绝对分数”，还要有“对照组”。

**三类基准**

| 基准类型 | 来源 | 用途 |
|---------|------|------|
| 预测市场价格 | Polymarket / Metaculus | 概率校准外部锚点 |
| 历史事件真相集 | 人工标注 100+ 事件 | 准确率基准 |
| 人类分析师基线 | 文献 / 合作机构 | 超越目标 |

**基准集治理**
- 维护 `benchmark_cases`（含事后真值、时间窗、场景标签）
- 版本冻结：每次阶段升级必须在同一基准集复测
- 指标最小集合：Brier、ECE、时效、误报漏报、决策效用

### G4. 数据飞轮量化（Flywheel Quantification）

目标：量化“飞轮多久转一圈、转一圈提升多少”。

| 飞轮 | 冷启动阈值 | 观测周期 | 增益指标 | 加速手段 |
|------|------------|----------|----------|----------|
| 校准飞轮 | >=100 标注样本 | 周级 | ECE/Brier 改善 | 历史回放预热 |
| 专家反馈飞轮 | >=N 次结构化纠正 | 双周 | 误判率下降 | Feedback Compiler 自动编译 |
| 本体晋升飞轮 | 候选提案池达到阈值 | 周级 | 晋升精度/回滚率 | Candidate 批量回放 |
| 常驻记忆飞轮 | 连续运行 >=X 周 | 月级 | 策略命中率提升 | 记忆审计 + 失效回收 |

落地要求：
- 每个飞轮必须有“触发阈值 + 增益指标 + 时间窗口”。
- 若连续两个观测周期无增益，触发飞轮诊断任务。

### G5. 统一降级框架（Unified Degradation Framework）

目标：把“模块各自降级”升级为“系统一致降级策略”。

**统一触发源**
- 资源压力：token 预算不足、延迟超 SLO
- 依赖故障：LiteLLM/Neo4j/GDELT/API 不可用
- 质量风险：meta-confidence 低、欺骗风险高

**统一降级矩阵（首版）**

| 触发条件 | 降级动作 | 保留能力 | 输出标注 |
|----------|----------|----------|----------|
| LLM 限流/超时 | 降低辩论轮次，切换轻量模式 | 基础证据聚合 + 保守结论 | `degraded_mode=llm_throttle` |
| 图数据库不可用 | 关闭多跳/因果图搜索 | 文本证据链 + 简化更新 | `degraded_mode=graph_unavailable` |
| 外部源不可用 | 启动缓存与替代源 | 历史检索 + 已有证据复评 | `degraded_mode=source_fallback` |
| 总体预算告急 | 只跑高优先级 case + T-5m/T-1h 模式 | 快速风险卡 | `degraded_mode=budget_emergency` |

强制规则：
- 降级输出必须显式标注 `degraded_mode`、降级原因、可能影响范围。
- 任何 Level 3 自主输出在降级模式下默认降一级信任展示。

### 附录 D：Phase 过渡标准（Phase Transition Gates）

目标：明确“何时可以启动下一阶段”，避免路线图失控并行。

**闸门类型**
- 硬性前置（Hard Gate）：不满足则禁止进入下一阶段
- 软性前置（Soft Gate）：建议满足，可并行推进但需风险说明

**阶段闸门模板**

| from -> to | 硬性前置（必须完成） | 软性前置（建议完成，可并行） |
|------------|----------------------|------------------------------|
| P1 -> P2 | LLMCallManager 上线、采样置信度可用、grounding 强制 | 红队基础套件 10 场景通过 |
| P2 -> P3 | 校准层冷启动完成（50+ 标注）、PCMCI 可运行 | RAG 历史检索上线 |
| P3 -> P4 | 辩论机制验证有效、meta-confidence 可用 | Shapley 分解上线 |
| P4 -> P5 | 蒸馏分类器替代率 >30%、多数据源至少 2 个接入 | 判断日志积累 >1000 条 |
| P5 -> P6 | 锦标赛架构验证有效、常驻 agent 运行 >1 月 | 假设集完整性三层保障验证 |
| P6 -> P6+ | Decision Layer + Shadow/Replay + 治理闸门闭环 | 策略效用显著优于旧版 |

执行规则：
- 每次阶段切换都需形成“闸门检查记录”（通过/豁免/整改项）。
- 豁免放行必须写明风险、回滚条件、责任人。

### 附录 E：架构决策待定（AD-01 ~ AD-19）

以下议题必须在对应阶段前形成明确决策并落地实现，避免后期架构返工。

| AD ID | 议题 | 必要决策 | 最晚落地阶段 | 状态 |
|-------|------|----------|--------------|------|
| AD-01 | 贝叶斯 ACH 互斥假设限制 | 定义非互斥场景替代框架（factor graph / argument map）与切换条件 | P-next-6.3 前 | 待定 |
| AD-02 | 因果图冷启动与质量门控 | 定义因果图质量指标、冲突仲裁、低质量自动降级策略 | P-next-6.3 前 | 待定 |
| AD-03 | 多 agent 一致性 | 明确 Core/Candidate 本体一致性协议与冲突处理流程 | P-next-5 前 | 待定 |
| AD-04 | 推理链存储成本 | 定义推理链分层存储（热/温/冷）与归档策略 | P-next-5 前 | 待定 |
| AD-05 | 多时间尺度评估闭环 | 按短中长期拆分校准模型并定义中间检查点机制 | P-next-5 前 | 待定 |
| AD-06 | 自主权安全边界 | 固化自治动作矩阵（Level 1/2/3）与不可自动化红线 | P-next-6 前 | 待定 |
| AD-07 | 多租户/多场景预留 | 数据模型预留 `tenant_id/scope_id` 与隔离策略 | P-next-6 前（至少字段预留） | 待定 |
| AD-08 | LLM 升级兼容性 | 版本锁定 + Shadow 回归 + Prompt 版本绑定策略 | P-next-6 前 | 待定 |
| AD-09 | 实时流与批处理分离 | 定义实时层/批处理层边界与双向接口 | P-next-5 前 | 待定 |
| AD-10 | 证据质量传播衰减 | 定义跨 stage 信息保真度传播与阈值告警 | P-next-3 前 | 待定 |
| AD-11 | 时间一致性 | 定义时序冲突检测与“后续证据否定”机制 | P-next-3 前 | 待定 |
| AD-12 | 递归深度控制 | 定义全局递归深度、边际收益停止、递归成本上限 | P-next-6 前 | 待定 |
| AD-13 | 模块错误隔离 | 定义 stage 级熔断与降级策略（内部异常场景） | P-next-3 前 | 待定 |
| AD-14 | Neo4j/Qdrant 一致性 | 明确真相源与索引源、重嵌入触发与最终一致性窗口 | P-next-3 前 | 待定 |
| AD-15 | Prompt 系统治理 | 建立 prompt 注册表、依赖图与回归测试 | P-next-3 前 | 待定 |
| AD-16 | 专家反馈激励与负载 | 定义最小反馈面、即时回报、智能路由与负载均衡 | P-next-6 前 | 待定 |
| AD-17 | 可观测性体系 | 统一健康仪表盘、关联告警与审计日志规范 | P-next-3 前 | 待定 |
| AD-18 | 灾难恢复 | 定义备份频率、恢复优先级、降级运行预案 | P-next-6 前 | 待定 |
| AD-19 | 注意力惯性 | 定义探索-利用平衡策略（如 epsilon-greedy） | P-next-6 前 | 待定 |

`AD-06` 自主权矩阵（基线）：

| 行动类型 | Level 1 | Level 2 | Level 3 |
|----------|---------|---------|---------|
| 调整监测频率 | 人工审批 | 自动 + 通知 | 自动 |
| 修改校准参数 | 人工审批 | Shadow 验证后自动 | 自动 |
| 修改因果图边 | 人工审批 | 人工审批 | Shadow 验证后自动 |
| 发送外部通知 | 人工审批 | 人工审批 | 自动 + 人工可撤销 |
| 修改 pipeline 逻辑 | 禁止 | 禁止 | 人工审批 |

---

## 横切面：贯穿所有阶段的设计原则

以下五个方向不是独立 Phase，而是从 P-next-1 开始就应融入每个模块设计的原则。

### 横切面一：对抗性红队测试

**问题**：整个路线图都在优化"系统做对事情的能力"，但没有系统性测试"系统在什么情况下会犯错"。
情报分析最危险的不是系统不够准，而是系统很自信地给出错误结论，分析师信了。

**现状**：
- hypothesis_adversarial.py 有正方/反方/法官三角色对抗框架（452 行）
- bias_detector 检测 4 种偏误，coordination_detector 检测协同传播
- fixture_import_service 可注入预构建测试数据（20+ 场景）
- 但没有系统性红队测试套件，没有中途注入对抗性数据的机制

**方案**：

a) 红队测试套件（P-next-1 开始）：
   - 定义 10-20 个对抗性场景：矛盾高可信度来源、协同假信息投放、数据源质量突变、
     prompt injection 尝试、极端值输入
   - 每个场景有预期行为（应该检测到/应该降级/应该标记）
   - 作为 CI 的一部分持续运行

b) 中途注入机制：
   - pipeline 增加 `inject_adversarial` 测试钩子，可在任意 stage 之间注入对抗性数据
   - 仅在测试模式启用，生产环境禁用

c) 数据源质量监控：
   - source_credibility 增加"历史可信度趋势"，某来源可信度突然下降时告警
   - 与 P-next-3 的 meta-confidence 联动

涉及文件：新增 `tests/adversarial/` 目录，修改 `pipeline_orchestrator.py`（测试钩子），
修改 `source_credibility.py`（趋势监控）

### 横切面二：分析师工作流定义

**问题**：所有模块都是"能力就绪"，但没有端到端的用户旅程把它们串起来。
API 设计、推送粒度、报告格式都应该由工作流驱动，而不是反过来。

**现状**：
- API 端点齐全（case CRUD、pipeline 运行、chat、quality、subscriptions、investigations）
- 推送系统有 priority_threshold（0-3）
- 但没有统一 dashboard 端点，没有"推荐下一步"，没有 case 级优先级排序

**方案**：

a) 定义典型工作流（输出为 `docs/v0.3/analyst-workflow.md`）：
   ```
   晨间巡检：GET /dashboard/morning-brief → 过夜事件摘要 + 高优先级变化
   深入分析：GET /cases/{uid}/analysis-summary → 假设评估 + 证据缺口 + 推荐动作
   审核调研：GET /investigations?status=completed → 自动调研结果 + 新证据影响
   输出结论：POST /cases/{uid}/judgments → 标注结论 + 置信度 + 依据
   ```

b) 新增统一 dashboard 端点：
   - `GET /dashboard/morning-brief`：聚合过夜事件、hypothesis 变化、investigation 完成、高优先级推送
   - `GET /cases/{uid}/recommended-actions`：基于当前 evidence gaps 和 meta-confidence 推荐下一步

c) 工作流定义反过来影响后续 Phase 的实现优先级——
   如果分析师最常用的是 morning-brief → 深入分析 → 审核调研，
   那 P-next-2 的历史检索和 P-next-3 的元评估应该优先服务这条路径。

涉及文件：新增 `docs/v0.3/analyst-workflow.md`，新增 `api/routes/dashboard.py`

### 横切面三：统一推理链（reasoning_trace）

**问题**：各模块内部都有推理记录（ToolTrace、ACHResult、BayesianUpdateResult、InvestigationRound），
但没有统一格式，分析师无法看到完整的"为什么系统得出这个结论"。

**现状**（已有基础，实现成本低）：
- ToolTraceV1：tool_name、request、response、status、duration_ms、trace_id、span_id
- ActionV1：action_type、rationale、inputs、outputs、trace_id
- ACHResult：supporting/contradicting assertion UIDs、gap_list、confidence、grounding_level
- BayesianUpdateResult：prior/posterior、likelihoods、diagnosticity、max_change
- InvestigationRound：gap_description、search_queries、results_count、posterior_change
- 分布式追踪：trace_id 跨 stage 传播，span_id 每个工具调用独立

**缺的是**：
- 统一的 reasoning_trace API（现在要分别查 tool_traces + actions + investigation rounds）
- 贝叶斯更新的自然语言解释（"为什么从 40% 升到 62%"）
- 交叉关联的可验证推理链（不只是 LLM 说"这个模式重要"）

**方案**：

a) 统一 `ReasoningTrace` schema：
   ```python
   class ReasoningStep(BaseModel):
       step_type: str          # "evidence_assessment" | "bayesian_update" | "investigation_search" | ...
       input_summary: str      # 输入摘要（中文）
       judgment: str           # 判断结果
       basis: list[str]        # 依据（SourceClaim UIDs 或统计指标）
       confidence: float       # 该步骤的置信度
       trace_id: str           # 关联到 ToolTrace
   ```

b) 每个模块输出时附带 ReasoningStep，pipeline 汇总为完整 reasoning_trace

c) 新增 API：`GET /cases/{uid}/reasoning-trace` → 按时间排序的完整推理链

涉及文件：新增 `contracts/reasoning.py`（schema），修改各 stage（输出 ReasoningStep），
新增 `api/routes/reasoning.py`

### 横切面四：渐进式信任机制（trust_level）

**问题**：系统刚上线时分析师不会信任它。一开始就推送"战争准备概率 62%"会适得其反。

**现状**：
- settings.py 无 trust_level 或 automation_level 概念
- investigation_enabled 只有全局开关，无 per-case 控制
- push_engine 有 priority_threshold 但无自动化级别
- pipeline 无 approval gate（人工审核门）

**方案**：

a) Case 模型加 `trust_level` 字段（1-3）：
   - Level 1（信息聚合）：只做数据收集和结构化，不输出判断。推送内容为"这三条新闻可能相关"
   - Level 2（辅助分析）：输出判断但标注为"系统建议"，与分析师判断并行展示。
     高风险结论（confidence > 0.8 的预测）需要人工确认才推送
   - Level 3（自主分析）：系统判断直接输出，InvestigationAgent 自动触发，
     只有 meta-confidence 低于阈值时才要求人工介入

b) pipeline_orchestrator 根据 trust_level 控制行为：
   - Level 1：跳过 hypothesis_analyze、adversarial_evaluate、forecast_generate
   - Level 2：全部运行，但输出标记 `system_suggestion: true`
   - Level 3：全部运行，高 meta-confidence 结果自动推送

c) 新 case 默认 trust_level=1，分析师手动升级。
   系统可建议升级（"该场景历史准确率 > 80%，建议升级到 Level 2"），但不自动升级。

d) 渐进式放权路径（与 P-next-6.3 对齐）：
   - **现阶段（P-next-1~3）**：AI 做分析，人类做判断。trust_level 默认 1-2，
     人类的每次判断（agree/disagree/修正）都在校准 AI 的认知模型
   - **中期（P-next-4~5）**：AI 做分析和初步判断，人类做审核和边界设定。
     已校准领域可自动升级到 Level 3，新领域仍需人类参与
   - **远期（P-next-6+）**：AI 自主运行，人类定义目标和约束。
     人类说"关注中东局势，底线是误判冲突概率不超过 20%"，AI 自主决定分析策略

e) trust_level 自动计算（替代纯手动设置）：
   - 基于该场景/领域的历史准确率、校准误差、专家一致率自动计算建议 trust_level
   - 当某领域历史准确率持续超过人类基线 -> 系统建议升级
   - 当某领域出现连续误判 -> 系统自动降级
   - 放权依据是数据（可量化的历史表现），不是感觉
   - 人类保留最终否决权：任何自动升级可被人工覆盖

涉及文件：修改 `db/models/case.py`（加 trust_level），修改 `pipeline_orchestrator.py`（条件执行），
修改 `push_engine.py`（按 trust_level 过滤推送内容）

### 横切面实施节奏

这五个不是一次性做完，而是随 Phase 逐步深化：

| 横切面 | P-next-1 | P-next-2 | P-next-3 | P-next-4 | P-next-5 | P-next-6 |
|--------|----------|----------|----------|----------|----------|----------|
| 红队测试 | 基础套件（10 场景） | 交叉关联对抗场景 | 辩论对抗场景 | 蒸馏分类器对抗测试 | 多 agent 共谋/群体思维检测 + 假设集完整性对抗 | 策略建议对抗测试 + 因果图投毒检测 |
| 工作流 | analyst-workflow.md 定义 | morning-brief 端点 | recommended-actions 端点 | 自动化工作流 | 锦标赛进度实时查看 + 人工干预入口 | 策略建议审核流 + 放权仪表盘 |
| 推理链 | ReasoningStep schema + 基础输出 | 校准解释 + 历史案例引用 | Shapley 分解可视化 | 分类器决策解释 | 完整辩论记录 + 信息增益决策链 | 因果干预链 + 反事实基线 + 策略效果归因 |
| 信任等级 | trust_level 字段 + Level 1/2 | Level 2 完善 | Level 3 + meta-confidence 联动 | 自动升级建议 | Level 3 全自主循环 | 基于历史表现的自动放权 + 人类否决权 |

### 横切面五：系统鲁棒性（失败模式防御）

**问题**：前面所有优化都在提升系统的"最大能力"，但没有机制在运行时检测系统是否正在犯错。
情报分析中，一次高置信度的错误判断比十次正确判断的危害大得多。
横切面一的红队测试是事后的、离线的；这里需要的是运行时的、实时的防御层。

**现状**：
- `bias_detector.py` 已有 4 种偏误检测（single_source_dependency、single_stance_bias、
  source_homogeneity、confirmation_bias），纯规则实现
- `blindspot_detector.py` 检测覆盖缺口、时间窗口过窄、周期性信息空白
- `confidence_scorer.py` 有 5 维质量评分，但不追踪不确定性在 pipeline 步骤间的传播
- `hypothesis_adversarial.py` 是 LLM 辩论 + 规则聚合，无形式化逻辑检查
- `StageResult` 无 confidence/uncertainty 字段，pipeline 不追踪每步不确定性

**方案**：分为单次分析内的实时检查和跨分析的长期适应两类。

#### 单次分析内的实时检查

**a) 认知偏误扩展审计（基于 MindScope 检测数据集与框架）**

现有 `bias_detector.py` 的 4 种偏误是起点，扩展到情报分析最相关的 15-20 种：
- 锚定效应：第一条搜索结果对最终结论的影响是否过大？打乱证据输入顺序，看结论是否变化
- 群体极化：锦标赛多轮辩论后，后验是否在极端化（从 60% 涨到 95%）而没有对应新证据
- 框架效应：同一证据用不同措辞描述时，LLM 的评估是否一致
- 后见之明偏误：系统是否在事后"合理化"已知结果

参考：MindScope (arXiv:2410.04452) 提供 72 种偏误类别的 5170 个检测问题，
从中筛选情报分析相关子集。在现有 bias_detector 基础上扩展，不是替代。

涉及文件：修改 `services/bias_detector.py`（扩展偏误类型），
新增 `tests/adversarial/bias_scenarios.py`（偏误检测测试场景）

**b) 形式化逻辑预检（基于 FormalJudge 思路）**

在假设生成之后、辩论之前，用符号逻辑检查基本一致性：
- 同一条证据不能同时 support 和 contradict 同一个假设
- 假设之间不能存在逻辑蕴含关系（H1 蕴含 H2 则应合并）
- 证据-假设关系矩阵的行列一致性

不需要引入 Z3/Dafny 全套形式化验证，用 Python 规则检查即可覆盖 ACH 场景。
形式化逻辑检查比贝叶斯裁判更精确——贝叶斯处理概率，逻辑处理必然。

参考：FormalJudge (arXiv:2602.11136) 的神经符号混合范式

涉及文件：新增 `services/logic_checker.py`（ACH 矩阵逻辑一致性检查），
修改 `services/tournament.py`（辩论前调用逻辑预检）

**c) 不确定性传播追踪（基于 UProp 思路）**

pipeline 每步量化不确定性，追踪累积效应。不确定性在多步推理中会累积放大，
且 LLM 自身无法感知这种累积。当累积不确定性超过阈值时标记"低可信度"。
关键是每个 stage 有明确计算口径，而不是统一占位字段。

```python
class StageUncertainty(BaseModel):
    stage: str
    input_uncertainty: float   # 输入不确定性（上一步传来）
    stage_uncertainty: float   # 本步骤引入的不确定性
    output_uncertainty: float  # 输出不确定性 = f(input, stage)
    method: str                # 量化方法（"sampling" | "entropy" | "beta_variance"）
```

每个 stage 输出时附带 StageUncertainty，pipeline 汇总为不确定性传播链。
当 output_uncertainty 超过阈值时，后续 stage 的输出自动标记为"低可信度"。

stage 级计算口径（首版）：
- `assertion_fuse`：`stage_uncertainty = ds_conflict_degree`
- `hypothesis_analyze`：`stage_uncertainty = 1 - agreement_rate`（采样一致率）
- `adversarial_evaluate`：`stage_uncertainty = defense/prosecution 分歧度`
- `narrative_build`：`stage_uncertainty = 1 - evidence_coverage`（无直接概率时用覆盖率代理）
- `forecast_generate`：`stage_uncertainty = normalized_prediction_interval_width`

输出层约束：所有 stage 都必须产出可解释的不确定性来源说明（`method` + `detail`）。

参考：UProp (arXiv:2506.17419) 的信息论不确定性分解框架

涉及文件：修改 `services/pipeline_orchestrator.py`（StageResult 加 uncertainty），
新增 `services/uncertainty_tracker.py`（传播计算 + 阈值告警）

**d) 推理轨迹实时审计（基于 TrajAD 思路）**

与 agent 执行并行运行（不是执行完再审计），检测推理跳跃、证据遗漏、逻辑断裂。

冷启动策略：先用规则检测明显的轨迹异常（搜索跳过关键来源、推理步骤缺失、
结论与证据不匹配），积累标注数据后再训练专门的 verifier 模型。

规则检测示例：
- agent 搜索了 5 个来源但只引用了 1 个 → 标记"证据选择性引用"
- agent 的结论中出现了搜索结果中没有的事实 → 标记"幻觉风险"
- agent 在 3 步内从"不确定"跳到"高置信度" → 标记"推理跳跃"

参考：TrajAD (arXiv:2602.06443) 的细粒度过程监督

涉及文件：新增 `services/trajectory_auditor.py`（规则审计 + 标注收集），
修改 `services/tournament.py`（agent 执行时并行审计）

**e) 多样性与置信度校准（基于 Demystifying MAD）**

锦标赛中不能只靠不同 system prompt 保证多样性。需要：
- 显式多样性度量：agent 初始假设的语义相似度矩阵，相似度 > 0.9 时强制重新生成
- 置信度校准门：agent 的置信度需要校准后才参与辩论，否则过度自信的 agent 会主导结果
- 辩论权重：按校准后的置信度加权，而非"声音最大的 agent 赢"

参考：Demystifying MAD (arXiv:2601.19921) 的多样性 + 校准置信度机制

涉及文件：修改 `services/tournament.py`（多样性检查 + 置信度校准门）

#### 跨分析的长期适应

**f) 原则演化（基于 PiEvo 思路）**

不是在固定认知框架中搜索，而是让系统自动发现新的分析框架。
周期性评估各认知框架的历史有效性，淘汰长期无效的框架，
当现有框架无法解释异常时自动扩展框架空间。

与 Bandit 优化（探索三）的区别：Bandit 在固定框架集合中选择最优子集，
PiEvo 扩展框架集合本身。两者互补。

参考：PiEvo (arXiv:2602.06448) 的贝叶斯优化 + 高斯过程原则空间搜索

涉及文件：新增 `services/principle_evolution.py`（框架有效性评估 + 自动扩展）

**g) 可证伪性约束 + 结构化假设精炼**

每个假设在生成时必须附带：
- 预测：如果假设成立，未来 48 小时内应该观察到什么？
- 否证条件：什么证据出现就说明假设错了？
- 关键测试：哪一条搜索能最有效地区分这个假设和竞争假设？

系统自动监测预测和否证条件。预测没兑现 → 自动降低后验。否证条件出现 → 淘汰假设。
这比纯贝叶斯更新更强——贝叶斯是被动的（有新证据才更新），可证伪性是主动的
（没有预期证据出现本身就是信号）。

假设改进过程用结构化增量编辑框架约束——每次只允许一个局部修改
（修改一个前提、增加一条证据、调整一个参数），避免假设在改进过程中面目全非。

参考：Tiny Moves (arXiv:2602.09801) 的结构化增量编辑框架

涉及文件：修改 `contracts/schemas.py`（HypothesisV1 加 predictions/falsification_conditions），
新增 `services/falsification_monitor.py`（预测监测 + 自动后验调整）

#### 自适应分析深度

不是所有事件都值得启动完整锦标赛。系统根据事件重要性自动选择分析深度：

```
Level 0：纯规则过滤（GDELT 事件量 < 阈值，直接忽略）
Level 1：单 agent 快速分析（常规事件，~30 秒，~2k tokens）
Level 2：双 agent 辩论（有争议的事件，~2 分钟，~10k tokens）
Level 3：完整锦标赛（重大事件，~5-15 分钟，~50k tokens）
Level 4：锦标赛 + War Gaming（危机级事件，~30+ 分钟，~200k tokens）
```

升级触发：Level 1 分析后 max(P(Hi)) < 0.4 → 升级到 Level 2；
Level 2 辩论后仍不收敛 → 升级到 Level 3。
边际收益递减检测：连续两轮后验变化 < 2% → 提前终止。
成本-价值权衡：每轮 token 成本 vs 预期信息增益，成本 > 预期增益时停止。

涉及文件：修改 `services/pipeline_orchestrator.py`（分析深度路由），
与 TokenBudgetManager 联动

#### 鲁棒性横切面实施节奏

| 机制 | P-next-1 | P-next-2 | P-next-3 | P-next-5 |
|------|----------|----------|----------|----------|
| 偏误检测 | 扩展到 8 种（在现有 4 种基础上） | 锚定效应 + 框架效应检测 | 群体极化检测（辩论场景） | 全套 15-20 种 |
| 逻辑预检 | ACH 矩阵基本一致性 | — | 辩论前逻辑门 | 完整形式化检查 |
| 不确定性传播 | StageUncertainty schema + assertion/hypothesis/adversarial 口径落地 | 校准步骤的不确定性量化 | Shapley 分解的不确定性 | 全 pipeline 传播链 |
| 轨迹审计 | 规则检测（3 类异常） | — | — | 训练 verifier（基于积累数据） |
| 多样性校准 | — | — | 2-agent 辩论的多样性检查 | 锦标赛多样性 + 置信度校准门 |
| 原则演化 | — | — | — | 框架有效性评估 + 自动扩展 |
| 可证伪性 | — | — | 假设附带预测/否证条件 | 自动监测 + 后验调整 |
| 分析深度 | Level 0-1 | Level 0-2 | Level 0-2 | Level 0-4 全套 |

---

## 架构指导与约束（AD-20 ~ AD-39）

本章节将“问题 26-50 与 33 条指导建议”收敛为可执行架构决策，
并与 `附录 E（AD-01 ~ AD-19）` 形成连续编号体系。

分级定义：
- `MUST`：未完成不得进入对应阶段
- `SHOULD`：建议完成，可在风险说明后并行推进
- `CAN`：增强项，可后续迭代

### AD 决策清单（新增）

| AD ID | 级别 | 决策项 | 最晚落地阶段 |
|-------|------|--------|--------------|
| AD-20 | MUST | LLM 结构化解析韧性：监控每个调用点解析失败率；失败时执行“简化 schema + 简化 prompt + 降级输出”链路；增加语义合理性校验（范围/实体存在性） | P-next-3 前 |
| AD-21 | MUST | 测试策略分层：单元（数学正确性）、集成（接口契约）、回归（变更后稳定性）、性能（延迟/吞吐 SLO）四层基线 | P-next-3 前 |
| AD-22 | SHOULD | 配置治理：配置注册表（默认值、范围、依赖、变更史）+ 参数敏感性分析 + 配置变更 Shadow 验证 | P-next-4 前 |
| AD-23 | MUST | 数据与输出合规：数据源使用条款登记、输出分级字段 `classification_level`、访问控制与免责声明策略 | P-next-1 前（治理就绪） |
| AD-24 | MUST | 可复现性双层定义：`审计回放可复现`（必须，基于完整调用记录）与 `实时重跑可复现`（不保证，仅统计一致性） | P-next-1 前（审计先行） |
| AD-25 | MUST | 数据源对抗性适应：除“源独立性”外，新增“信息过度一致性/低熵异常”检测，识别高阶协调注入 | P-next-6 前 |
| AD-26 | SHOULD | 二次传播效应：标注预测是否可能改变被预测对象；该类样本在校准统计中单列或降权 | P-next-6 前 |
| AD-27 | SHOULD | 语义漂移治理：关键术语语义版本化 + 周期性 embedding 质量复检 + 世界模型刷新联动 | P-next-6 前 |
| AD-28 | MUST | 锚定效应轻量缓解：每次贝叶斯更新后执行先验 ±20% 敏感性快检，输出“先验驱动风险标签” | P-next-3 前 |
| AD-29 | SHOULD | 跨语言保真：关键 claim 保留“原文+译文+翻译偏差分数”；高风险场景优先语言原生模型 | P-next-6 前 |
| AD-30 | CAN | 创造力补充：反直觉假设、类比假设、缺失行为体检测并入候选假设池（不替代主生成器） | P-next-6+ |
| AD-31 | MUST | 记忆污染防控：记忆来源追溯、证据失效联动重验、跨 agent 记忆冲突审计 | P-next-5 前 |
| AD-32 | MUST | 群体极化防御：探索阶段内存隔离；辩论阶段仅交换论点/证据，禁止交换置信度与投票信号 | P-next-5 前 |
| AD-33 | MUST | 似然函数质量：LLM 似然值必须带可靠性指标（采样一致率/校准误差）；结构化数据优先统计似然 | P-next-6.3 前 |
| AD-34 | MUST | DS 与贝叶斯接口：DS 用于证据层，贝叶斯用于假设层；DS 的 pignistic 可转入似然。若 DS“无知质量”超阈值（如 `m(Theta) > 0.4`），禁止强制概率化，输出“证据不足” | P-next-3 前 |
| AD-35 | MUST | PCMCI 适用门禁：仅在满足数据长度/稳定性/可观测性条件的子域启用统计因果；其余使用语义/专家因果并标注适用限制 | P-next-3 前 |
| AD-36 | MUST | 解释计算近似策略：Shapley 与信息增益按规模分层（低维精算、中维采样、高维熵代理）并公开阈值 | P-next-5 前 |
| AD-37 | SHOULD | 校准样本效率：按领域 × 风险等级 × 预测窗口分层校准；样本不足层显式标注“未校准” | P-next-4 前 |
| AD-38 | MUST | 锦标赛收敛与对冲成本：定义收敛判据 + 最大轮次 + 不收敛降级输出；多模型对冲按风险分层触发（低/中/高） | P-next-5 前 |
| AD-39 | MUST | 动态图工程约束：大图采用局部近似/增量算法；事件以 event-time 排序 + watermark 重排 + 幂等重放；建立认知负债指数并周期清理 | P-next-6 前 |

### AD 决策清单（新增二：AD-40 ~ AD-49）

| AD ID | 级别 | 决策项 | 最晚落地阶段 |
|-------|------|--------|--------------|
| AD-40 | MUST | LiteLLM 单点故障消除：LiteLLM 至少双实例高可用，LLMCallManager 提供直连 fallback；代理层不可用时系统进入“规则+统计”极端降级模式 | P-next-1 前 |
| AD-41 | MUST | KG schema 演进治理：图写入统一经由 schema 校验 API；类型别名映射；类型新增/合并/废弃的自动迁移工具 | P-next-3 前 |
| AD-42 | SHOULD | Embedding 模型迁移：向量记录带模型版本；新旧模型增量共存与按需重算策略；迁移期间检索质量回归监控 | P-next-5 前 |
| AD-43 | MUST | 常驻 agent 资源隔离：每个 agent 具备最低保障配额 + 上限配额；超限触发降级而非停机；与 Budget Market 联动 | P-next-5 前 |
| AD-44 | MUST | Pipeline 版本化与灰度发布：从 P-next-1 开始支持“双版本并跑 + 指标对比 + 回滚”基础能力（Shadow/Replay 的前身） | P-next-1 前 |
| AD-45 | SHOULD | 分析保质期：每份分析输出附建议有效期（TTL）；过期自动降级展示并提示重分析；关键前提失效时触发失效通知 | P-next-6 前 |
| AD-46 | MUST | 跨 Case 证据污染防护：区分原始证据与衍生证据；禁止循环引用；跨 Case 引用时展示外部 Case 评估上下文 | P-next-5 前 |
| AD-47 | SHOULD | 注意力盲区扫描：在全量信息流做“未知聚类中心”检测，发现非已知领域信号并自动创建探索任务 | P-next-6+ |
| AD-48 | SHOULD | 专家主动输入通道：允许专家主动提交关系/因果/线索，自动结构化入库并纳入反馈编译闭环 | P-next-6 前 |
| AD-49 | SHOULD | 解释债务治理：多层解释（一句话/摘要/完整链）+ 按需展开 + 反事实解释优先 + 关键证据可视化 | P-next-6 前 |

### AD 决策清单（新增三：AD-50 ~ AD-62）

| AD ID | 级别 | 决策项 | 最晚落地阶段 |
|-------|------|--------|--------------|
| AD-50 | SHOULD | 开放世界贝叶斯扩展：在假设空间中引入 `catch-all` 假设并动态更新其后验；当其后验持续升高时触发假设发现。说明：该机制降低遗漏风险，不承诺“数学上不遗漏” | P-next-6.3 前 |
| AD-51 | MUST | 因果融合统一：采用“LLM 因果先验 + 统计/专家似然更新”框架；边级不确定性需受图结构约束与冲突仲裁，不允许独立边无约束漂移 | P-next-6.3 前 |
| AD-52 | SHOULD | Pipeline 拓扑升级：从线性 stage 链路升级为 DAG 调度，按显式依赖并行执行无依赖 stage，降低端到端延迟 | P-next-3 前 |
| AD-53 | MUST | 增量分析机制：新证据仅触发受影响假设更新；保留定期全量重算用于纠偏，避免增量误差长期累积 | P-next-5 前 |
| AD-54 | MUST | 假设结构化表示：以结构化字段（actor/action/target/timeframe/conditions）替代纯文本假设，支持去重、互斥判定与参数化修改 | P-next-4 前 |
| AD-55 | SHOULD | 证据多粒度表示：同源信息生成粗/中/细粒度 claim，按任务与时间尺度匹配检索粒度 | P-next-5 前 |
| AD-56 | SHOULD | 主动学习反馈路由：专家反馈请求按“预期改进收益”排序，只请求 top-K 样本，提升单位反馈价值 | P-next-6 前 |
| AD-57 | SHOULD | 形式化安全不变量验证：定义并验证关键安全不变量（如单源证据后验上限）；说明：保障不变量成立，不等同于“系统完全安全” | P-next-6 前 |
| AD-58 | MUST | 计算图去重与缓存：对确定性计算做缓存与共享；可共享原始证据与确定性中间结果，禁止跨 agent 共享派生判断/结论 | P-next-5 前 |
| AD-59 | MUST | 在线/离线学习分离：明确在线可更新参数与离线可更新参数，离线产物与在线状态采用“合并策略”而非直接覆盖 | P-next-5 前 |
| AD-60 | MUST | Pareto 决策实用化：前沿结果必须经偏好模型二次排序输出“推荐/备选/高风险高收益”；偏好来源（显式输入或历史学习）必须可审计 | P-next-6 前 |
| AD-61 | SHOULD | 图规则推理引擎：补充传递性/对称性/类型继承等规则推理，结果标记为“推理得出”并与观测事实隔离展示 | P-next-4 前 |
| AD-62 | MUST | 时序数据专用管道：时序数据走独立处理链（清洗/特征/异常/趋势/预测），主 pipeline 仅消费结构化时序证据摘要 | P-next-4 前 |

### AD 决策清单（新增四：AD-63 ~ AD-74）

| AD ID | 级别 | 决策项 | 最晚落地阶段 |
|-------|------|--------|--------------|
| AD-63 | MUST | 证据信息量度量：同时计算“观测后信息量”（解释用）与“期望信息量”（调度用），避免单一指标循环定义；高信息量证据进入关键证据槽位 | P-next-3 前 |
| AD-64 | MUST | 证据独立性校正：维护证据依赖图（共源/引用/共事件），对高依赖证据去重或降权，避免条件独立假设导致后验过度自信 | P-next-3 前 |
| AD-65 | SHOULD | 假设粒度层次化：建立粗中细粒度假设树，证据支持可向上传播；锦标赛优先同粒度比较 | P-next-5 前 |
| AD-66 | SHOULD | 博弈论嵌入策略搜索：在策略评估中引入“对手 top-K 反应 + 有限前瞻”机制，避免单方最优化偏差 | P-next-6 前 |
| AD-67 | SHOULD | 证据时间价值多模型：支持指数/阶梯/钟形/不衰减四类衰减函数，并按证据类型映射与在线再估计参数 | P-next-6 前 |
| AD-68 | SHOULD | 元认知分层触发：按 Level 0-3 触发不同元认知检查，并将元认知成本纳入预算分配 | P-next-5 前 |
| AD-69 | SHOULD | 辩论信息效率协议：强制“回应目标 + 新增论点”结构，启用重复检测与信息增益递减提前终止 | P-next-5 前 |
| AD-70 | MUST | 知识图谱时态建模：关系边必须支持 `valid_from/valid_to`，提供时态查询与关系变迁检测 | P-next-5 前 |
| AD-71 | MUST | 概率认知负荷优化：概率输出必须同时给出数字+语言标签+行动阈值建议；阈值映射须按组织偏好校准并可审计 | P-next-3 前 |
| AD-72 | SHOULD | 分析可比性：为每次分析生成方法论指纹（证据集/假设集/模型版本/参数），仅在可比条件下做趋势比较 | P-next-3 前 |
| AD-73 | SHOULD | 反馈延迟偏差修正：反馈到达后执行回溯标记；蒸馏训练优先使用“已验证样本”或显式验证状态权重 | P-next-6 前 |
| AD-74 | SHOULD | 全口径成本效率：成本模型扩展到计算/存储/网络全量，统一优化目标为 `decision_utility / total_cost` | P-next-6 前 |

### 执行约束补充

- AD-20/21/24/28/34/35/38 为“质量闸门组”，任一未达标不得提升 `trust_level`。
- AD-23/25/31/39 为“长期运行安全组”，任一未达标不得启用 Level 3 全自主循环。
- AD-40/41/44/46 为“基础设施硬闸门组”，任一未达标不得进入 P-next-5 常驻化阶段。
- AD-51/54/60/62 为“核心推理与决策闸门组”，任一未达标不得进入 P-next-6.3 策略化主链。
- AD-53/58/59 为“性能与可扩展闸门组”，任一未达标不得扩大多 agent 并发规模。
- AD-63/64/71 为“信息论与证据质量闸门组”，任一未达标不得进入 P-next-3 后的概率决策输出。
- AD-65/68/69/70 为“时态与辩论质量闸门组”，任一未达标不得进入 P-next-5 锦标赛常态化运行。
- AD-66/67/73/74 为“策略与长期效率闸门组”，任一未达标不得开启 P-next-6 全量策略闭环。
- AD-30 为探索增强项，不作为阶段放行前置条件。

---

## 参考文献

### 核心架构论文（直接影响设计）

- **AI Co-Scientist**: [arXiv:2502.18864](https://arxiv.org/abs/2502.18864) (Google, 2025.02) — Generate-Debate-Evolve 锦标赛假设发现，多 agent 异步执行，test-time compute scaling。锦标赛架构的核心参考
- **BioDisco**: [arXiv:2508.01469](https://arxiv.org/abs/2508.01469) (2025.08) — 多 agent 假设生成 + dual-mode evidence（文献+数据）+ 迭代反馈 + 时间评估。多视角证据收集 + 假设时间验证参考
- **Silent Scholar**: [arXiv:2512.20884](https://arxiv.org/abs/2512.20884) (2025.12) — Beta-Bernoulli 信念模型 + 遗忘因子(γ) + 信息增益驱动搜索 + epistemic caching。时间衰减 + KL 散度搜索策略参考
- **Tool-MAD**: [arXiv:2601.04742](https://arxiv.org/abs/2601.04742) (2026.01) — 不同 agent 不同工具访问权限的多 Agent 辩论，事实核查。认知框架差异化 + 证据隔离设计参考
- **D2D Debate-to-Detect**: [arXiv:2505.18596](https://arxiv.org/abs/2505.18596) (2025.05) — 辩论式误信息检测，模拟真实世界事实核查流程。辩论机制在事实核查场景的验证

### LLM 推理与自我纠错

- **LLMs Cannot Self-Correct Reasoning Yet**: [arXiv:2310.01798](https://arxiv.org/abs/2310.01798) (Huang et al., ICLR 2024) — LLM 在没有外部反馈时无法有效自我纠错，性能甚至下降。证明单 agent 自我质疑有天花板，需要多 agent + 外部裁判
- **Abductive Inference in RAG**: arXiv (Lin, 2025.11) — RAG 检索证据不完整时，用溯因推理生成缺失前提并验证。异常驱动假设发现的方法参考
- **GEAR: General Evaluation Framework for Abductive Reasoning**: arXiv (2025.09) — LLM 溯因推理能力的系统评估框架。评估 LLM 在假设生成场景的能力边界
- **Metacognitive Prompting for Debiasing**: arXiv (Hills, 2025.07) — 用元认知提示减少 LLM 的认知偏误。元认知评估层的 prompt 设计参考
- **Diversity of Thought in Multi-Agent Debate**: arXiv (Hegazy, 2024.10/2025.01) — 多 agent 辩论中思维多样性越高，推理效果越好。支持不同认知框架的设计决策
- **PDR: Parallel-Distill-Refine**: [arXiv:2510.01123](https://arxiv.org/abs/2510.01123) (Madaan et al., 2025.10) — 并行生成多个草案 → 蒸馏到工作空间 → 精炼，比长 CoT 更准且更快。多 agent 并行探索后的结果聚合策略参考

### 系统鲁棒性与失败模式防御

- **TrajAD**: [arXiv:2602.06443](https://arxiv.org/abs/2602.06443) (2026.02) — 运行时推理轨迹异常检测，细粒度过程监督 verifier。agent 轨迹审计参考
- **PiEvo**: [arXiv:2602.06448](https://arxiv.org/abs/2602.06448) (2026.02) — 贝叶斯优化 + 高斯过程在原则空间上搜索，不确定性最小化驱动的科学发现。认知框架自动演化参考
- **FormalJudge**: [arXiv:2602.11136](https://arxiv.org/abs/2602.11136) (2026.02) — 神经符号混合范式，LLM 编译高层意图为原子可验证约束，Z3/Dafny 形式化验证。ACH 逻辑一致性检查参考
- **UProp**: [arXiv:2506.17419](https://arxiv.org/abs/2506.17419) (2025.06) — 多步 agent 决策中不确定性的传播与累积，信息论分解框架。pipeline 不确定性追踪参考
- **Demystifying MAD**: [arXiv:2601.19921](https://arxiv.org/abs/2601.19921) (Zhu et al., 2026.01) — vanilla 多 agent 辩论失败原因分析，多样性初始化 + 校准置信度辩论协议。锦标赛多样性机制参考
- **MindScope**: [arXiv:2410.04452](https://arxiv.org/abs/2410.04452) (ECAI 2024) — 72 种认知偏误类别的检测数据集与框架，多 agent + RAG + RL，比 GPT-4 高 35%。偏误检测扩展参考
- **Tiny Moves**: [arXiv:2602.09801](https://arxiv.org/abs/2602.09801) (2026.02) — 结构化增量编辑框架，固定语法的局部修改做假设精炼。假设改进过程约束参考
- **Scientific Hypothesis Generation Survey**: [arXiv:2505.04651](https://arxiv.org/abs/2505.04651) (2025.05) — LLM 假设生成与验证方法、数据集、评估指标综述。P-next-5 设计参考手册

### 校准与置信度

- **EvolveCast**: [arXiv:2509.23936](https://arxiv.org/abs/2509.23936) (2025.09) — LLM 收到新证据时不会正确更新信念
- **TruthTensor**: arXiv:2601.13545 (2026.01) — 准确率相似的模型校准度差异巨大
- **Calibration-Aware RL**: arXiv:2601.13284 (2026.01) — RLHF 导致过度自信
- **采样置信度基准**: [arXiv:2602.00279](https://arxiv.org/abs/2602.00279) (2026.02) — 采样频率 > 口头置信度
- **SCA Calibration**: arXiv:2602.07842 (2026.02) — 语义置信度聚合
- **Semantic Entropy**: [arXiv:2302.09664](https://arxiv.org/abs/2302.09664) (Kuhn et al., 2023) — 语义聚类后计算熵，预测 LLM 输出正确性
- **AIA Forecaster**: [arXiv:2511.07678](https://arxiv.org/abs/2511.07678) (2025.11) — 首个匹配人类超级预测者的 LLM 系统，agentic search + 统计校准

### 预测与可解释性

- **PRISM/Shapley**: arXiv:2601.09151 (2026.01) — Shapley 值分解预测贡献
- **sdLM**: arXiv:2601.14862 (2026.01) — 战略教义约束 LLM 输出

### 因果发现与异常检测

- **tigramite**: [github.com/jakobrunge/tigramite](https://github.com/jakobrunge/tigramite) — PCMCI 时序因果发现
- **Runge et al.** (2019), Science Advances — PCMCI 原始论文
- **Runge et al.** (2023), Nature Reviews Earth & Environment — 因果发现综述
- **GCAD: Granger Causality Anomaly Detection**: arXiv (2025.01) — 用 Granger 因果做多变量时序异常检测。数据驱动异常共变发现的方法参考
- **Structured Temporal Causality for Anomaly Detection**: arXiv (2025.10) — 结构化时序因果关系用于可解释异常检测
- **Entropy Causal Graphs for Anomaly Detection**: arXiv (2023.12/2025.08) — 熵因果图做多变量时序异常检测。第零层异常共变发现的算法参考

### 知识蒸馏

- **Distilling Step-by-Step**: [arXiv:2305.02301](https://arxiv.org/abs/2305.02301) (Hsieh et al., 2023) — 770M 模型用 80% 数据超过 540B 模型
- **MiniLLM**: arXiv:2306.08543 (2023) — 反向 KL 散度蒸馏
- **ChatGPT as Annotator**: arXiv:2303.15056 (2023) — LLM 标注质量超过众包

### 多 Agent 与事实核查

- **AutoPrunedRetriever**: arXiv (2026.02) — 最小推理子图，token 降 100×

### 竞品与生态

- **OpenCTI**: [github.com/OpenCTI-Platform/opencti](https://github.com/OpenCTI-Platform/opencti) (8.2k stars) — STIX2 情报平台，连接器生态参考
- **LightRAG**: [github.com/HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) (28.3k stars) — KG+向量混合检索，graphrag 参考
- **Cognee**: [github.com/topoteretes/cognee](https://github.com/topoteretes/cognee) (12.3k stars) — KG 记忆引擎，分析记忆参考
- **SpiderFoot**: [github.com/smicallef/spiderfoot](https://github.com/smicallef/spiderfoot) (16.6k stars) — OSINT 自动化，数据源接入参考
- **ACH-Grounding**: [github.com/suprathermal/ACH-Grounding](https://github.com/suprathermal/ACH-Grounding) (2025.12) — ACH + LLM + RAG，架构参考（玩具级但思路对）

### 远景探索相关

- **PyKEEN**: [github.com/pykeen/pykeen](https://github.com/pykeen/pykeen) (2k+ stars) — 知识图谱嵌入 + 链接预测，KG 多跳推理参考
- **Polymarket API**: [docs.polymarket.com](https://docs.polymarket.com) — 预测市场公开 API，校准锚点数据源
- **Metaculus API**: [metaculus.com/api](https://www.metaculus.com/api/) — 预测问题 + 社区校准概率，校准基准参考
- **DISARM Framework**: [github.com/DISARMFoundation/DISARMframeworks](https://github.com/DISARMFoundation/DISARMframeworks) — 信息操作分类体系（MITRE ATT&CK 风格）
- **Yahoo Finance (yfinance)**: [github.com/ranaroussi/yfinance](https://github.com/ranaroussi/yfinance) — 金融数据 API，多模态数值信号接入
- **FRED API**: [fred.stlouisfed.org/docs/api](https://fred.stlouisfed.org/docs/api/) — 美联储经济数据，宏观经济信号
- **Sentinel Hub**: [sentinel-hub.com](https://www.sentinel-hub.com/) — ESA 卫星图像 API，远期多模态视觉信号
- **DoWhy**: [github.com/py-why/dowhy](https://github.com/py-why/dowhy) — 因果推断框架，AEGI 已集成
