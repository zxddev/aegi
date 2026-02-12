# AEGI 贝叶斯 ACH 升级 — 架构指导

> 作者：白泽（架构师）
> 日期：2026-02-11
> 用途：指导 CC 将现有静态 ACH 升级为贝叶斯动态 ACH

---

## 一、问题

现有 ACH（hypothesis_engine.py）是**一次性静态分析**：
- 给定一组证据和假设 → LLM 判断每条证据支持/反驳哪个假设 → 输出置信度
- 新证据到来时，必须重新跑整个分析，无法增量更新
- 置信度计算是简单比例（支持数/总数），没有概率论基础
- 专家无法知道"什么变了、为什么变了"

## 二、目标

升级为**贝叶斯动态 ACH**：
- 每个假设有一个先验概率，新证据到来时用贝叶斯公式更新后验概率
- 支持增量更新：不需要重新分析所有证据，只处理新证据
- 输出概率变化轨迹：专家能看到"假设A从60%升到75%，因为证据X"
- 量化证据的诊断性（diagnosticity）：哪条证据对区分假设最有价值

## 三、核心原则

### 1. 不引入重型框架
- 不用 pgmpy、pymc 等贝叶斯网络库
- 贝叶斯 ACH 的数学很简单，就是贝叶斯公式的直接应用，自己写几十行就够
- 保持代码可读、可调试

### 2. 向后兼容
- 现有 ACHResult 数据结构保留，新增字段
- 现有 generate_hypotheses() 和 analyze_hypothesis_llm() 保留，新增贝叶斯层
- 现有测试不能 break

### 3. LLM 负责定性判断，数学负责定量计算
- LLM 判断：这条证据支持/反驳哪个假设？强度如何？（这个现有代码已经做了）
- 数学计算：基于 LLM 的判断，用贝叶斯公式计算概率更新（这是新增的）
- 不要让 LLM 直接输出概率——LLM 对概率的校准很差

### 4. 可审计
- 每次概率更新都要记录：哪条证据、更新前概率、更新后概率、似然比
- 专家可以回溯整个推理链

---

## 四、贝叶斯 ACH 数学模型

### 核心公式

对于假设 H_i 和新证据 E：

```
P(H_i | E) = P(E | H_i) * P(H_i) / P(E)

其中 P(E) = Σ P(E | H_j) * P(H_j)  （对所有假设求和）
```

### 似然度估计

关键问题：P(E | H_i) 怎么来？

用 LLM 的判断转换：
- LLM 判断 "support" + 高置信度 → P(E|H) = 0.8~0.9
- LLM 判断 "support" + 低置信度 → P(E|H) = 0.6~0.7
- LLM 判断 "irrelevant" → P(E|H) = 0.5（不提供信息）
- LLM 判断 "contradict" + 低置信度 → P(E|H) = 0.3~0.4
- LLM 判断 "contradict" + 高置信度 → P(E|H) = 0.1~0.2

这个映射表可配置，不要硬编码。

### 诊断性（Diagnosticity）

证据 E 对区分假设 H_i 和 H_j 的诊断性：

```
diagnosticity(E, H_i, H_j) = P(E|H_i) / P(E|H_j)
```

诊断性越高，这条证据越有价值。诊断性接近 1 的证据对区分假设没用。

### 先验概率

初始状态：所有假设等概率（均匀先验）。
专家可以手动调整先验（体现专家判断）。

---

## 五、数据模型变更

### 5.1 hypotheses 表新增字段

```python
# 在现有 Hypothesis 模型上新增
prior_probability: float          # 先验概率（初始 = 1/N）
posterior_probability: float      # 当前后验概率
probability_history: list[dict]   # 概率变化轨迹 [{"evidence_uid", "prior", "posterior", "likelihood", "timestamp"}]
```

### 5.2 新增 evidence_assessment 表

记录每条证据对每个假设的似然度评估：

```
evidence_assessments:
  - uid
  - case_uid (FK)
  - hypothesis_uid (FK → hypotheses)
  - evidence_uid (str, 指向 assertion 或 source_claim)
  - relation: support / contradict / irrelevant
  - strength: float (LLM 给出的强度 0~1)
  - likelihood: float (转换后的 P(E|H))
  - assessed_by: "llm" / "expert" (支持专家覆盖)
  - created_at
```

---

## 六、模块设计

### 6.1 新增 services/bayesian_ach.py

核心类 `BayesianACH`：

```
class BayesianACH:
    """贝叶斯竞争性假设分析引擎。"""

    初始化(hypotheses, prior_probabilities=None)
        → 设置先验（默认均匀分布）

    assess_evidence(evidence, llm) → list[EvidenceAssessment]
        → 用 LLM 判断证据与每个假设的关系和强度
        → 将 relation+strength 映射为似然度 P(E|H)

    update(assessments) → BayesianUpdateResult
        → 用贝叶斯公式更新所有假设的后验概率
        → 返回更新前后的概率、似然比、诊断性排名

    get_state() → 当前所有假设的概率分布 + 历史轨迹

    get_most_diagnostic_gaps() → 哪些信息如果获得能最大程度区分假设
```

### 6.2 与现有代码的关系

```
现有流程：
  generate_hypotheses() → [ACHResult] → analyze_hypothesis_llm() → confidence

升级后流程：
  generate_hypotheses() → [ACHResult]
      ↓
  BayesianACH(hypotheses) → 初始化先验
      ↓
  新证据到来 → assess_evidence() → update() → 更新后验
      ↓
  事件驱动层 emit hypothesis.updated → 推送给专家
```

BayesianACH 是在现有 ACH 之上的一层，不替换现有代码。

### 6.3 与事件驱动层的集成

当 `claim.extracted` 事件触发时：
1. EventBus 通知 BayesianACH handler
2. handler 加载该 case 的当前假设和概率状态
3. 对新证据调用 assess_evidence() + update()
4. 如果概率变化超过阈值（如 >5%），emit `hypothesis.updated` 事件
5. PushEngine 将更新推送给订阅了该 case 的专家

---

## 七、推送消息格式

专家收到的通知应该是这样的：

```
[案例: 中东局势分析]

假设概率更新：
  假设A "伊朗将在3个月内重启核谈判" 
    60.0% → 75.3% (+15.3%)
  假设B "伊朗将加速铀浓缩" 
    25.0% → 15.2% (-9.8%)
  假设C "维持现状" 
    15.0% → 9.5% (-5.5%)

触发证据：[来源: Reuters] "伊朗外长表示愿意在特定条件下恢复对话"
诊断性：该证据强烈区分假设A和假设B（诊断比=4.5）
```

这种输出比"假设A最可能"有价值得多。

---

## 八、不要做的事

- 不要引入 pgmpy / pymc / 任何贝叶斯网络库
- 不要改变现有 ACHResult 的结构（只新增字段）
- 不要让 LLM 直接输出概率数值
- 不要做复杂的贝叶斯网络（假设之间的依赖关系）——初期假设之间独立
- 不要做前端展示（概率变化通过 API 和推送输出）
- 不要做降级逻辑

---

## 九、CC 的任务

1. 详细设计文档（数据模型、接口、似然度映射表、与事件驱动层的集成点）
2. Alembic migration（hypotheses 表新增字段 + evidence_assessments 新表）
3. 实现 services/bayesian_ach.py
4. 实现事件驱动集成（claim.extracted → 贝叶斯更新 → hypothesis.updated）
5. 新增 API 端点：GET /cases/{id}/hypotheses/probabilities（返回当前概率分布和历史）
6. 测试：贝叶斯更新的数学正确性 + 端到端集成

设计文档写入：`/home/user/workspace/gitcode/aegi/code/docs/design/bayesian-ach.md`

---

_白泽出品，CC 执行。_
