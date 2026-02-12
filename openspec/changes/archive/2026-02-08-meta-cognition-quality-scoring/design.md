<!-- Author: msq -->

## Decisions

1. 每个 Judgment 输出可解释可信度构成。
2. 偏见/盲区提示进入审核与回归。

## Input / Output Contracts

- 输入：`JudgmentV1` + 上游产物（Hypothesis/Narrative/Forecast）
- 输出：`QualityReportV1`
  - 必填：`confidence_score`、`confidence_breakdown`、`bias_flags`、`blindspot_items`、`evidence_diversity`

## API Contract

- `POST /cases/{case_uid}/quality/score_judgment`
- `GET /cases/{case_uid}/quality/judgments/{judgment_uid}`

## Scoring Dimensions

1. 证据强度（独立来源数、来源可靠性）
2. 覆盖度（关键维度是否缺证）
3. 一致性（上游模块输出冲突程度）
4. 新鲜度（时效）

## Bias / Blindspot

1. 偏见检测：单源依赖、单立场偏置、确认偏误信号
2. 盲区检测：关键维度缺证据、时间窗缺失、地理盲点

## Acceptance

1. 每个 judgment 有可解释分解，不是单分值黑盒。
2. bias/blindspot 输出可追溯证据来源。
3. 质量报告支持回归比较（版本间差异）。
