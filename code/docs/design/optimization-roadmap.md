# AEGI 系统深度分析与优化路线图

> 作者：白泽
> 日期：2026-02-12
> 基于：代码审查 + 深度调研报告 + E2E 验证报告

---

## 一、现状评估

### 已建成的能力

AEGI 核心骨架已经成型，模块覆盖面很广：

| 层 | 模块 | 行数 | 成熟度 |
|---|------|------|--------|
| 数据采集 | gdelt_monitor + gdelt_scheduler + osint_collector | ~900 | ⭐⭐⭐ 基本可用 |
| 信息提取 | claim_extractor + document_parser | ~400 | ⭐⭐⭐ 基本可用 |
| 证据融合 | assertion_fuser | 381 | ⭐⭐ 有硬伤 |
| 来源评估 | source_credibility | 105 | ⭐ 玩具级 |
| 假设分析 | hypothesis_engine + bayesian_ach | ~1170 | ⭐⭐⭐ 核心逻辑完整 |
| 因果推断 | causal_inference (DoWhy) + causal_reasoner (LLM) | ~990 | ⭐⭐ 两套独立系统 |
| 知识图谱 | graph_analysis + link_predictor (PyKEEN) + neo4j_store | ~1000 | ⭐⭐⭐ 基础扎实 |
| 协调检测 | coordination_detector | 150 | ⭐⭐ 简单规则 |
| 叙事构建 | narrative_builder | 217 | ⭐⭐ 基础版 |
| 报告生成 | report_generator | 585 | ⭐⭐ 单视角 |
| 推送引擎 | push_engine + event_bus | ~430 | ⭐⭐⭐ 架构完整 |
| 编排层 | pipeline_orchestrator | 839 | ⭐⭐⭐ 核心枢纽 |

**总计：~120 个 Python 文件，~15000 行核心代码，368 个测试通过。**

### 核心问题诊断

对照调研报告，AEGI 当前有 **5 个系统性短板**，不是 bug，是架构层面的缺失：

#### 短板 1：证据融合是"检测冲突但不解决冲突"

```python
# assertion_fuser.py:266 — 这就是全部的融合逻辑
confidence=0.5 if has_conflict else 0.9,
```

问题：
- 冲突检测后只做二值化降级（0.9→0.5），丢失冲突严重度
- 来源可信度只有 13 个硬编码域名 + 3 个低可信域名
- 不同来源的权重完全相同
- 无法表达"某来源在军事领域可信但经济领域不可信"

影响：整个证据链的质量上限被这里卡死。贝叶斯 ACH 再精确，输入的 confidence 就是 0.5 或 0.9 两个值，后续所有分析都建立在粗糙的基础上。

#### 短板 2：两套因果系统互不相通

- `causal_inference.py`（762 行）— DoWhy 统计因果推断，需要结构化数据
- `causal_reasoner.py`（229 行）— LLM 因果推理，自由文本

两者完全独立，没有信息流通。调研报告指出 ALCM 框架的三阶段模式（数据驱动发现→LLM 精炼→DoWhy 估计）是正确方向。

#### 短板 3：态势感知全靠硬阈值

```python
# settings.py
gdelt_anomaly_goldstein_threshold = -7.0  # 硬阈值
```

- GDELT 异常检测只有 Goldstein < -7 一条规则
- 没有趋势检测、变点检测、新兴话题发现
- 没有基线概念——"异常"应该是相对于基线的偏离，不是绝对值

#### 短板 4：知识图谱推理太浅

- `graph_analysis.py` 只做 multi-hop path 查询
- `link_predictor.py` 用 PyKEEN 做链接预测，但需要 50+ 三元组才能训练
- 没有时序推理能力（TKG）
- 没有利用 LLM 做图谱推理（ToG/RoG 范式）

#### 短板 5：没有反馈闭环

- 分析师无法对 Assertion 给反馈（同意/不同意/需要更多证据）
- 推送后不知道分析师是否采纳
- 系统无法从人类反馈中学习和校准
- 调研报告的元分析结论：**没有反馈的 AI 辅助反而有害**

---

## 二、优化策略

### 核心原则

1. **深度优先于广度** — 不再新增模块，把现有模块做深做透
2. **数据流优先于功能** — 先打通模块间的数据流，再优化单个模块
3. **概率化优先于规则化** — 硬阈值→概率分布，硬编码→学习型
4. **闭环优先于开环** — 加反馈机制，让系统能自我校准

### 不做什么

- 不做前端（主人说暂不考虑）
- 不引入重量级框架（CrewAI、LangGraph 等）— AEGI 自己的 pipeline_orchestrator 够用
- 不训练专用模型（PyKEEN 除外）— 用 LLM + ICL 替代
- 不追求论文级精度 — 追求工程可用性

---

## 三、分阶段优化路线

### Phase 1：证据质量基座（1-2 周）

**目标：让证据链的每一环都有真实的置信度，而不是 0.5/0.9 二值。**

这是最高优先级，因为所有下游分析（贝叶斯 ACH、因果推断、报告生成）的质量上限都取决于输入证据的质量。

#### 1.1 source_credibility 升级

从 105 行的域名查表升级为多信号评分：

```
输入：URL + 文章内容（可选）
输出：CredibilityScore {
    domain: str,
    score: float,           # 0.0-1.0 综合分
    tier: str,              # high/medium/low/unknown
    domain_scores: dict,    # 按领域的可信度向量（军事、经济、政治...）
    signals: {
        domain_reputation: float,    # 域名信誉（扩展到 100+ 域名）
        tld_trust: float,            # 顶级域名信任度
        content_sensationalism: float, # 内容煽情度（LLM 评估，可选）
        publication_frequency: float,  # 发布频率异常度
        cross_reference_rate: float,   # 被其他来源引用的频率
    },
    reason: str,
}
```

关键改动：
- 扩展域名库到 100+（从 MBFC、NewsGuard 等公开评级导入）
- 新增 `domain_scores` 字段支持 contextual discounting
- 新增煽情度检测（简单版：关键词匹配；进阶版：LLM 评估）

#### 1.2 assertion_fuser DS 理论升级

用 Dempster-Shafer 理论替换硬编码 confidence：

```
当前：confidence = 0.5 if has_conflict else 0.9
目标：
  1. 每条 SourceClaim → mass function（基于 source_credibility 分数）
  2. 多条 SourceClaim → Dempster 组合规则融合
  3. 冲突度量 → plausibility-belief 散度（不是布尔值）
  4. 最终 confidence → Pignistic 概率变换
```

依赖：`pip install dstz`（MIT，8 stars 但数学实现完整）

#### 1.3 Assertion 反馈 API

新增模型和端点：

```
POST /assertions/{uid}/feedback
{
    "user_id": "expert_alice",
    "verdict": "agree" | "disagree" | "need_more_evidence",
    "comment": "可选的文字说明",
    "confidence_override": 0.85  # 可选，分析师手动校准
}
```

反馈数据用于：
- 调整该来源的 credibility 权重（长期学习）
- 触发 push_engine 阈值校准
- 贝叶斯 ACH 的人工证据输入

### Phase 2：态势感知升级（1-2 周）

**目标：从硬阈值异常检测升级为概率化、多维度的态势感知。**

#### 2.1 River ADWIN 在线漂移检测

在 `GDELTScheduler` 的 poll 循环中加入：

```python
from river.drift import ADWIN

# 每次 poll 后
for event in new_events:
    adwin_tone.update(event.avg_tone)
    adwin_freq.update(event_count_this_interval)
    if adwin_tone.drift_detected or adwin_freq.drift_detected:
        await event_bus.emit(AegiEvent(
            event_type="trend.drift_detected",
            severity="medium",
            payload={...}
        ))
```

替换 `gdelt_anomaly_goldstein_threshold = -7.0` 硬阈值。

#### 2.2 BOCPD 变点检测

新增 `ChangePointDetector` 服务：

```
输入：GDELT tone/频率时间序列
输出：变点概率 + 变点位置 + 变化方向（升/降）
触发：emit "trend.changepoint_detected" 到 EventBus
```

在线用 BOCPD 实时检测，定期用 ruptures PELT 离线确认。

#### 2.3 BERTopic 新兴话题发现

新增 `TopicTracker` 服务：

```
监听：gdelt.event_detected 事件
处理：每批新文章 → embedding（复用 localhost:8001 BGE-M3）→ BERTopic partial_fit
输出：
  - 新兴话题 → emit "topic.emerging"
  - 话题激增 → emit "topic.surge"
  - 话题消退 → emit "topic.declining"
```

### Phase 3：因果推断统一（2-3 周）

**目标：统一两套因果系统为 ALCM 三阶段流水线。**

#### 3.1 三阶段因果流水线

```
Stage 1: 数据驱动发现
  - causal-learn PC 算法从结构化数据发现候选因果图
  - tigramite PCMCI 从 GDELT 时序发现滞后因果关系
  - 输出：候选因果图（有向边 + 置信度）

Stage 2: LLM 精炼
  - 对候选因果图中的每条边，用 LLM 判断因果方向和强度
  - 用 CausalCoT 提示策略（CLadder 论文）
  - 过滤掉 LLM 认为不合理的边
  - 输出：精炼后的因果图

Stage 3: DoWhy 估计
  - 对精炼后的因果图，用 DoWhy 做效应估计
  - 反驳检验（placebo、random common cause 等）
  - 输出：因果效应量 + 置信区间 + 反驳结果
```

#### 3.2 时序因果发现

新增 `TemporalCausalDiscovery` 服务（独立进程，因为 tigramite 是 GPL）：

```
输入：GDELT 事件时间序列（按国家/CAMEO 编码聚合）
输出：滞后因果关系（"A 国制裁 → 3 天后 → B 国军事调动"）
```

### Phase 4：知识图谱推理深化（2-3 周）

**目标：从浅层路径查询升级为 LLM 驱动的深度图谱推理。**

#### 4.1 ICL-TKG 时序预测

不训练专用模型，直接用 LLM：

```
1. 从 Neo4j 提取实体的历史事件序列
2. 格式化为 prompt：
   "Given the following events involving Iran:
    2026-01-15: Iran [cooperate] IAEA
    2026-01-20: US [threaten] Iran
    2026-02-01: Iran [refuse] US
    Predict the next likely event involving Iran."
3. LLM 生成预测 → structured output
4. 预测结果写回 Neo4j 作为"预测边"（标记 is_predicted=true）
```

与现有 `invoke_structured()` 完全兼容，不需要新基础设施。

#### 4.2 Think-on-Graph 推理升级

替换 `graph_analysis.py` 的 multi-hop 查询为迭代 beam search：

```
当前：固定 depth 的 multi-hop path 查询
目标：LLM 作为 agent，在图上迭代探索
  1. LLM 看当前节点的邻居，选择最相关的 k 个方向
  2. 沿选择的方向扩展
  3. 重复直到找到答案或达到深度限制
  4. 返回推理路径（可追溯）
```

### Phase 5：信息鉴别增强（2-3 周）

**目标：从简单规则升级为多层次的信息真伪鉴别。**

#### 5.1 声明验证 pipeline stage

在 pipeline_orchestrator 中新增 `claim_verification` stage：

```
输入：claim_extractor 输出的 SourceClaims
处理：
  1. 对每条 claim，用 SearXNG 搜索交叉验证
  2. 多 Agent 辩论（简化版 D2D）：
     - Agent A：支持该 claim 的论据
     - Agent B：反对该 claim 的论据
     - Judge：综合判断
  3. 输出 verification_score + reasoning
```

#### 5.2 DISARM TTP 分类

导入 DISARM 框架的 TTP 分类表，coordination_detector 输出自动匹配：

```
检测到协调行为 → 匹配 DISARM TTP → 输出标准化的信息操作分类
例如：T0023 (Distort Facts) + T0046 (Use Search Engine Optimization)
```

#### 5.3 coordination_detector 因果升级

从 `(similarity + burst) / 2` 升级为因果检验：

```
当前：相似度 > 阈值 → 标记协调
目标：
  1. 时间序列因果检验（Granger 因果）
  2. 传播模式分析（是否符合自然传播还是人为放大）
  3. 输出因果置信度而非布尔值
```

### Phase 6：报告与推送优化（1-2 周）

**目标：报告从单视角升级为多视角，推送从规则匹配升级为智能推荐。**

#### 6.1 STORM 多视角报告

借鉴 STORM 的两阶段方法：

```
Stage 1 预写：
  - 从多个角度研究主题（政治、经济、军事、社会）
  - 模拟不同专家视角的对话
  - 收集多视角论据

Stage 2 写作：
  - 综合多视角生成报告
  - 每个论点附带证据链引用
  - 标注置信度和不确定性
```

#### 6.2 推送智能化

push_engine 增加：
- 基于反馈历史的阈值自适应
- 分析师关注点学习（从反馈和浏览行为推断）
- 推送时机优化（避免信息过载）

---

## 四、依赖关系与执行顺序

```
Phase 1 ──→ Phase 2 ──→ Phase 3
  │                        │
  │                        ↓
  │         Phase 4 ←── Phase 3
  │           │
  ↓           ↓
Phase 5 ←── Phase 1 + Phase 4
  │
  ↓
Phase 6 ←── 所有 Phase
```

- Phase 1 是基座，必须先做
- Phase 2 和 Phase 3 可以并行
- Phase 4 依赖 Phase 3 的因果图
- Phase 5 依赖 Phase 1 的 credibility 升级
- Phase 6 是最后的集成层

## 五、新增依赖清单

| 包 | 用途 | 许可证 | Phase |
|---|------|--------|-------|
| dstz | DS 理论证据融合 | MIT | 1 |
| river | 在线漂移检测 | BSD-3 | 2 |
| ruptures | 离线变点检测 | BSD-2 | 2 |
| bertopic | 话题建模 | MIT | 2 |
| causal-learn | 因果发现 | MIT | 3 |
| tigramite | 时序因果（独立服务） | GPL-3 | 3 |
| stumpy | Matrix Profile | BSD-3 | 2（可选） |

总计 7 个新依赖，其中 tigramite 因 GPL 需作为独立微服务。

## 六、预期效果

| 指标 | 当前 | Phase 1 后 | 全部完成后 |
|------|------|-----------|-----------|
| 证据 confidence 精度 | 2 个值（0.5/0.9） | 连续分布 0.0-1.0 | 多维度 + 领域特异 |
| 来源评估覆盖 | 16 个域名 | 100+ 域名 + 多信号 | + 内容分析 + 交叉引用 |
| 异常检测 | 1 条硬规则 | 概率化漂移检测 | + 变点 + 话题 + 模式 |
| 因果推断 | 两套独立系统 | — | 统一三阶段流水线 |
| 图谱推理 | 固定 depth 路径 | — | LLM 驱动 beam search |
| 信息鉴别 | 无 | — | 多 Agent 辩论验证 |
| 人机协作 | 无反馈 | 反馈 API | 自适应推送 + 偏差防护 |

## 七、给 CC 的任务拆分建议

Phase 1 可以拆成 3 个并行 CC：
- CC-A：source_credibility 升级 + 域名库扩展
- CC-B：assertion_fuser DS 理论升级（依赖 dstz）
- CC-C：Assertion 反馈 API + DB 模型

Phase 2 可以拆成 2 个并行 CC：
- CC-D：River ADWIN + BOCPD 变点检测
- CC-E：BERTopic 话题追踪

后续 Phase 根据进度再拆。

---

> 白泽的判断：AEGI 的骨架已经很好了，模块覆盖面在同类项目中算广的。但"广而不深"是当前最大问题。Phase 1 的证据质量基座是一切的前提——贝叶斯 ACH 再精确，输入只有 0.5 和 0.9 两个值，输出也不会好到哪去。先把地基打实，再往上盖楼。
