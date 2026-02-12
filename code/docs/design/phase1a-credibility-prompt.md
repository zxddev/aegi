# Phase 1-A：source_credibility 升级（给 Claude Code）

## 任务

将 `src/aegi_core/services/source_credibility.py` 从 105 行的域名查表升级为多信号评分系统。

**在开始前，先阅读：**
- `src/aegi_core/services/source_credibility.py` — 当前实现（105 行）
- `src/aegi_core/services/assertion_fuser.py` — 调用方（看它怎么用 credibility）
- `src/aegi_core/contracts/schemas.py` — SourceClaimV1 结构
- `docs/design/optimization-roadmap.md` — Phase 1.1 部分
- `tests/` 中所有 `*credib*` 相关测试

## 当前问题

```python
# 只有 13 个高可信域名 + 3 个低可信域名
# 其他所有域名一律返回 score=0.5, tier="unknown"
# 无法区分 CNN 和一个随机博客
```

## 目标架构

```python
@dataclass
class CredibilityScore:
    domain: str
    score: float              # 0.0-1.0 综合分
    tier: str                 # high | medium | low | unknown
    reason: str
    # 新增字段
    domain_scores: dict[str, float] | None = None  # 按领域可信度 {"military": 0.9, "economy": 0.6}
    signals: dict[str, float] | None = None         # 各信号分数
    conflict_discount: float = 1.0                   # 冲突折扣因子（0.0-1.0）
```

## 实现步骤

### Step 1：扩展域名信誉库

新建 `src/aegi_core/infra/domain_reputation.py`：

从公开来源整理域名信誉数据，至少覆盖 100 个域名：

```python
# 数据结构
@dataclass
class DomainProfile:
    domain: str
    base_score: float           # 0.0-1.0
    tier: str                   # high | medium | low
    category: str               # wire_service | major_outlet | state_media | tabloid | blog | academic | government
    country: str                # ISO 2-letter
    domain_strengths: dict[str, float]  # 领域特长 {"military": 0.9, "economy": 0.7}
    notes: str = ""

# 至少包含以下类别：
# 1. 国际通讯社（Reuters, AP, AFP, Xinhua, TASS, Yonhap, Kyodo）— score 0.85-0.95
# 2. 主流英文媒体（NYT, WaPo, Guardian, BBC, CNN, FT, Bloomberg, Economist）— score 0.80-0.90
# 3. 主流中文媒体（新华网, 人民日报, 环球时报, 南华早报, 联合早报）— score 0.70-0.85
# 4. 主流其他语言媒体（Al Jazeera, DW, France24, NHK, RT）— score 0.60-0.80
# 5. 政府/军方官网（.gov, .mil, mod.gov.*, defense.gov）— score 0.75-0.85
# 6. 学术/智库（RAND, CSIS, Brookings, IISS, CFR, Carnegie）— score 0.80-0.90
# 7. 行业专业媒体（Jane's, Defense News, The Diplomat, Foreign Affairs）— score 0.80-0.90
# 8. 已知低可信度（infowars, naturalnews, breitbart, rt.com 争议性标注）— score 0.15-0.30
# 9. 社交媒体/UGC（twitter.com, reddit.com, weibo.com）— score 0.30-0.40

# 每个域名标注领域特长，例如：
# janes.com: {"military": 0.95, "defense_industry": 0.95, "economy": 0.5}
# ft.com: {"economy": 0.95, "finance": 0.95, "military": 0.6}
# reuters.com: {"military": 0.85, "economy": 0.85, "politics": 0.90}  # 全能型

def lookup_domain(domain: str) -> DomainProfile | None:
    """查找域名信誉。支持子域名匹配（news.bbc.co.uk → bbc.co.uk）。"""

def lookup_tld(domain: str) -> tuple[float, str] | None:
    """按顶级域名推断信誉（.gov → 0.80, .edu → 0.75, .mil → 0.80）。"""
```

### Step 2：多信号评分器

重写 `source_credibility.py`：

```python
def score_source(
    url: str,
    *,
    content: str | None = None,       # 文章内容（可选，用于煽情度检测）
    domain_context: str | None = None, # 领域上下文（如 "military"），用于 contextual scoring
) -> CredibilityScore:
    """多信号来源可信度评分。

    信号权重：
    - domain_reputation: 0.50  — 域名信誉（查表）
    - tld_trust: 0.15          — 顶级域名信任度
    - content_quality: 0.20    — 内容质量信号（如果有 content）
    - url_heuristics: 0.15     — URL 启发式（路径深度、参数数量、可疑模式）

    如果没有 content，权重重新分配：
    - domain_reputation: 0.60
    - tld_trust: 0.20
    - url_heuristics: 0.20
    """
```

#### 信号 1：域名信誉（查表）
从 `domain_reputation.py` 查找，支持子域名回退。

#### 信号 2：TLD 信任度
```python
_TLD_SCORES = {
    ".gov": 0.80, ".gov.cn": 0.80, ".gov.uk": 0.80,
    ".edu": 0.75, ".edu.cn": 0.75, ".ac.uk": 0.75,
    ".mil": 0.80,
    ".org": 0.55,  # 中等，org 域名质量参差不齐
    ".com": 0.50,  # 基线
    ".net": 0.45,
    ".info": 0.35,
    ".xyz": 0.25,
    ".tk": 0.15, ".ml": 0.15, ".ga": 0.15,  # 免费域名，常被滥用
}
```

#### 信号 3：内容质量（如果有 content）
```python
def _score_content_quality(content: str) -> float:
    """基于内容特征的质量评分。不用 LLM，纯规则。

    正面信号（加分）：
    - 包含引用/引述（"据...报道"、"said"、"according to"）
    - 包含具体数字/日期
    - 段落结构清晰（多段落）
    - 包含来源归属

    负面信号（减分）：
    - 全大写标题
    - 过多感叹号
    - 煽情词汇密度高（"SHOCKING", "BREAKING", "你绝对想不到"）
    - 过短（<100 字）
    """
```

#### 信号 4：URL 启发式
```python
def _score_url_heuristics(url: str) -> float:
    """URL 结构启发式评分。

    负面信号：
    - 路径深度 > 5
    - 包含大量查询参数
    - 包含可疑模式（/sponsored/, /partner/, /advertorial/）
    - 域名包含数字（news123.com）
    - 域名过长（>30 字符）
    """
```

### Step 3：Contextual Discounting

```python
def get_contextual_score(
    credibility: CredibilityScore,
    domain_context: str,
) -> float:
    """根据领域上下文返回调整后的可信度分数。

    例如：janes.com 在 military 领域 → 0.95，在 economy 领域 → 0.5
    如果没有领域特长数据，返回 base score。
    """
```

### Step 4：测试

`tests/test_source_credibility.py`：

```python
# 基础测试
def test_known_high_credibility_domains():
    """reuters.com, apnews.com 等返回 high tier, score > 0.8"""

def test_known_low_credibility_domains():
    """infowars.com 等返回 low tier, score < 0.3"""

def test_government_tld():
    """.gov, .mil 域名返回 medium+ tier"""

def test_unknown_domain_not_050():
    """未知域名不再一律 0.5，而是基于 TLD + URL 启发式"""

def test_subdomain_fallback():
    """news.bbc.co.uk → bbc.co.uk 的信誉"""

# 多信号测试
def test_content_quality_with_citations():
    """包含引用的内容得分更高"""

def test_content_quality_sensationalism():
    """煽情内容得分更低"""

def test_url_heuristics_suspicious():
    """可疑 URL 模式得分更低"""

# Contextual 测试
def test_contextual_military_domain():
    """janes.com 在 military 上下文得分 > economy 上下文"""

def test_contextual_finance_domain():
    """ft.com 在 economy 上下文得分 > military 上下文"""

def test_contextual_no_domain_data():
    """无领域数据时返回 base score"""

# 域名库测试
def test_domain_reputation_coverage():
    """域名库至少 100 个条目"""

def test_domain_reputation_categories():
    """覆盖所有 9 个类别"""

# 回归测试
def test_backward_compatible_api():
    """score_domain(url) 仍然可用，返回 CredibilityScore"""
```

## 关键约束

- **保持 `score_domain(url)` 函数签名不变**：这是现有 API，assertion_fuser 在用。新增 `score_source()` 作为增强版。
- **不依赖 LLM**：纯规则 + 查表，保持快速和确定性
- **不依赖外部 API**：域名信誉数据内嵌在代码中
- **CredibilityScore 新增字段必须 Optional**：不破坏现有消费者
- **现有测试不能 break**
