# Phase 1-B：assertion_fuser DS 理论升级（给 Claude Code）

## 任务

将 `src/aegi_core/services/assertion_fuser.py` 的证据融合从硬编码 confidence（0.5/0.9）升级为 Dempster-Shafer 理论驱动的概率化融合。

**在开始前，先阅读：**
- `src/aegi_core/services/assertion_fuser.py` — 当前实现（381 行）
- `src/aegi_core/services/source_credibility.py` — 来源可信度评分
- `src/aegi_core/services/bayesian_ach.py` — 下游消费者（看它怎么用 confidence）
- `src/aegi_core/contracts/schemas.py` — AssertionV1, SourceClaimV1
- `src/aegi_core/db/models/assertion.py` — DB 模型
- `docs/design/optimization-roadmap.md` — Phase 1.2 部分
- `tests/test_assertion_fuser.py` — 现有测试

## 当前问题

```python
# assertion_fuser.py:266 — 整个融合逻辑的精度就这一行
confidence=0.5 if has_conflict else 0.9,
```

- 冲突检测后只做二值化降级（0.9→0.5）
- 丢失冲突严重度信息（4 种冲突类型权重相同）
- 不同来源的权重完全相同（Reuters 和随机博客一样）
- 下游贝叶斯 ACH 收到的 confidence 只有两个值

## DS 理论简介

Dempster-Shafer 理论用 mass function 表示证据的信念分配：

```
辨识框架 Θ = {true, false}（某个 claim 为真或假）

mass function m: 2^Θ → [0,1]
  m({true})  = 支持为真的信念
  m({false}) = 支持为假的信念
  m({true, false}) = 不确定性（既不支持也不反对）

约束：m(∅) = 0, Σm(A) = 1
```

Dempster 组合规则：两个独立证据源的 mass function 可以组合：
```
m12(A) = (1/(1-K)) × Σ{B∩C=A} m1(B) × m2(C)
K = Σ{B∩C=∅} m1(B) × m2(C)  # 冲突度
```

Pignistic 概率变换：将 mass function 转为点概率估计：
```
BetP(x) = Σ{x∈A} m(A) / |A|
```

## 实现步骤

### Step 1：安装 dstz

```bash
cd /home/user/workspace/gitcode/aegi/code/aegi-core
source .venv/bin/activate
pip install dstz
```

验证安装：
```python
python -c "from dstz.core import MassFunction; print('dstz ok')"
```

如果 dstz 安装失败或 API 不符合预期，自己实现核心 DS 数学（mass function、Dempster 组合、Pignistic 变换），代码量不大（~100 行）。

### Step 2：新建 DS 融合引擎

新建 `src/aegi_core/services/ds_fusion.py`：

```python
"""Dempster-Shafer 证据融合引擎。

将 SourceClaim 的 confidence + source credibility 转换为 mass function，
通过 Dempster 组合规则融合多条证据，输出概率化的 confidence。
"""

from dataclasses import dataclass


@dataclass
class DSFusionResult:
    """DS 融合结果。"""
    confidence: float           # Pignistic 概率（0.0-1.0）
    belief: float               # 信念下界 Bel({true})
    plausibility: float         # 似然上界 Pl({true})
    uncertainty: float          # 不确定性 m({true,false})
    conflict_degree: float      # 冲突度 K（0.0-1.0）
    mass_true: float            # m({true})
    mass_false: float           # m({false})
    source_count: int           # 参与融合的证据源数量


def claim_to_mass(
    claim_confidence: float,
    source_credibility: float,
) -> tuple[float, float, float]:
    """将单条 SourceClaim 转换为 mass function。

    Args:
        claim_confidence: claim 自身的置信度（0.0-1.0）
        source_credibility: 来源可信度（0.0-1.0）

    Returns:
        (m_true, m_false, m_uncertain) 三元组

    转换逻辑：
    - 来源可信度作为"折扣因子"（discounting）
    - discount = 1 - source_credibility
    - m({true}) = claim_confidence × source_credibility
    - m({false}) = (1 - claim_confidence) × source_credibility
    - m({true,false}) = discount（不确定性）

    例如：
    - Reuters (credibility=0.9) 报道某事 (confidence=0.8):
      m_true=0.72, m_false=0.18, m_uncertain=0.10
    - 随机博客 (credibility=0.3) 报道同一事 (confidence=0.8):
      m_true=0.24, m_false=0.06, m_uncertain=0.70
    """


def combine_masses(
    masses: list[tuple[float, float, float]],
) -> DSFusionResult:
    """用 Dempster 组合规则融合多个 mass function。

    Args:
        masses: [(m_true, m_false, m_uncertain), ...] 列表

    Returns:
        DSFusionResult

    注意：
    - 如果只有 1 个 mass，直接返回（不需要组合）
    - 如果冲突度 K > 0.9，说明证据严重矛盾，标记但仍然输出
    - 使用 Pignistic 变换将最终 mass 转为点概率
    """


def fuse_claims_ds(
    claims: list["SourceClaimV1"],
    credibility_scores: dict[str, float],  # claim_uid → credibility score
) -> DSFusionResult:
    """高层接口：融合一组 SourceClaims。

    1. 每条 claim → claim_to_mass()
    2. 所有 mass → combine_masses()
    3. 返回 DSFusionResult
    """
```

### Step 3：修改 assertion_fuser.py

在 `fuse_claims()` 函数中集成 DS 融合：

```python
# 修改前：
confidence=0.5 if has_conflict else 0.9,

# 修改后：
# 1. 获取每条 claim 的来源可信度
from aegi_core.services.source_credibility import score_domain
from aegi_core.services.ds_fusion import fuse_claims_ds

credibility_scores = {}
for c in group:
    cred = score_domain(c.source_url) if hasattr(c, 'source_url') and c.source_url else None
    credibility_scores[c.uid] = cred.score if cred else 0.5

# 2. DS 融合
ds_result = fuse_claims_ds(group, credibility_scores)

# 3. 使用 DS 融合结果
assertion = AssertionV1(
    uid=uuid.uuid4().hex,
    case_uid=case_uid,
    kind="fused_claim",
    value={
        "attributed_to": key if key != "_unattributed_" else None,
        "rationale": "; ".join(rationale_parts),
        "has_conflict": has_conflict,
        # 新增 DS 融合元数据
        "ds_belief": ds_result.belief,
        "ds_plausibility": ds_result.plausibility,
        "ds_uncertainty": ds_result.uncertainty,
        "ds_conflict_degree": ds_result.conflict_degree,
        "source_count": ds_result.source_count,
    },
    source_claim_uids=group_uids,
    confidence=ds_result.confidence,  # 用 DS Pignistic 概率替换硬编码
    modality=group[0].modality,
    created_at=now,
)
```

关键：`confidence` 字段现在是连续值（0.0-1.0），不再是 0.5/0.9 二值。

### Step 4：处理 SourceClaimV1 没有 source_url 的情况

检查 `SourceClaimV1` 的字段。如果没有 `source_url`，需要从 claim 的 `artifact_version_uid` 追溯到 artifact 获取 URL。

如果追溯太复杂，提供 fallback：
```python
# 无法获取来源 URL 时，使用默认 credibility
DEFAULT_CREDIBILITY = 0.5
```

### Step 5：测试

`tests/test_ds_fusion.py`：

```python
# 核心数学测试
def test_claim_to_mass_high_credibility():
    """高可信来源：m_uncertain 小"""
    m = claim_to_mass(0.8, 0.9)
    assert abs(m[0] - 0.72) < 0.01  # m_true
    assert abs(m[2] - 0.10) < 0.01  # m_uncertain

def test_claim_to_mass_low_credibility():
    """低可信来源：m_uncertain 大"""
    m = claim_to_mass(0.8, 0.3)
    assert m[2] > 0.6  # 大部分是不确定性

def test_combine_two_agreeing_sources():
    """两个一致的高可信来源 → confidence 很高"""
    m1 = claim_to_mass(0.8, 0.9)
    m2 = claim_to_mass(0.85, 0.85)
    result = combine_masses([m1, m2])
    assert result.confidence > 0.9

def test_combine_two_conflicting_sources():
    """两个矛盾的来源 → conflict_degree 高"""
    m1 = claim_to_mass(0.9, 0.8)   # 来源 A 说是真的
    m2 = claim_to_mass(0.1, 0.8)   # 来源 B 说是假的
    result = combine_masses([m1, m2])
    assert result.conflict_degree > 0.3

def test_combine_high_vs_low_credibility():
    """高可信来源应该压过低可信来源"""
    m_reuters = claim_to_mass(0.8, 0.9)   # Reuters
    m_blog = claim_to_mass(0.2, 0.3)      # 随机博客说相反的
    result = combine_masses([m_reuters, m_blog])
    assert result.confidence > 0.6  # Reuters 的判断占主导

def test_combine_single_source():
    """单一来源直接返回"""
    m = claim_to_mass(0.8, 0.9)
    result = combine_masses([m])
    assert abs(result.confidence - 0.8) < 0.1

def test_combine_many_weak_sources():
    """多个弱来源聚合可以增强信念"""
    masses = [claim_to_mass(0.7, 0.4) for _ in range(5)]
    result = combine_masses(masses)
    assert result.confidence > 0.7  # 多个弱证据聚合

def test_pignistic_probability():
    """Pignistic 变换正确"""
    # m_true=0.6, m_false=0.1, m_uncertain=0.3
    # BetP(true) = 0.6 + 0.3/2 = 0.75
    result = combine_masses([(0.6, 0.1, 0.3)])
    assert abs(result.confidence - 0.75) < 0.01

def test_extreme_conflict():
    """极端冲突时 conflict_degree 接近 1"""
    m1 = claim_to_mass(0.99, 0.99)
    m2 = claim_to_mass(0.01, 0.99)
    result = combine_masses([m1, m2])
    assert result.conflict_degree > 0.8

# 集成测试
def test_fuse_claims_ds_basic():
    """fuse_claims_ds 高层接口正常工作"""

def test_fuse_claims_ds_empty():
    """空 claims 列表不崩溃"""

# assertion_fuser 集成测试
def test_fuse_claims_no_longer_binary():
    """融合后的 confidence 不再只有 0.5 和 0.9"""
    # 构造多条 claims，验证输出的 confidence 是连续值
```

修改 `tests/test_assertion_fuser.py` 中的现有测试：
- 如果现有测试硬编码检查 `confidence == 0.5` 或 `confidence == 0.9`，改为范围检查
- 例如：`assert 0.3 < assertion.confidence < 0.7`（有冲突时）
- 例如：`assert assertion.confidence > 0.7`（无冲突时）

## 关键约束

- **`fuse_claims()` 函数签名不变**：返回类型不变，只是 confidence 值更精确
- **AssertionV1.value 中新增的 DS 元数据是附加信息**：不影响现有消费者
- **如果 dstz 不可用，自己实现核心数学**：mass function + Dempster 组合 + Pignistic 变换，~100 行
- **冲突检测逻辑保留**：4 种冲突检测器不动，DS 融合是在冲突检测之上的概率化层
- **LLM 语义冲突检测保留**：`adetect_semantic_conflicts()` 不动
- **现有测试适配**：硬编码的 confidence 断言改为范围检查
- **全量 pytest 0 failed**
