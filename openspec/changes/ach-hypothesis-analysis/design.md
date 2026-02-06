<!-- Author: msq -->

## Decisions

1. 假设必须可追溯到 Assertions/SourceClaims。
2. 输出覆盖率与冲突解释。
3. 引入 Defense/Prosecution/Judge 对抗式评估，避免单路评分偏置。

## Input / Output Contracts

- 输入：`AssertionV1[]`、`SourceClaimV1[]`、可选上下文（时间窗、地域）
- 输出：`HypothesisV1[]`
  - 必填：`hypothesis_text`、`supporting_assertion_uids`、`contradicting_assertion_uids`、`coverage_score`、`confidence`、`gap_list`

## API Contract

- `POST /cases/{case_uid}/hypotheses/generate`
- `POST /cases/{case_uid}/hypotheses/{hypothesis_uid}/score`
- `GET /cases/{case_uid}/hypotheses/{hypothesis_uid}/explain`

## Adversarial Reasoning Flow

1. Defense Agent：构建支持链（支持证据优先按诊断性排序）
2. Prosecution Agent：构建反证链与漏洞清单
3. Judge Agent：输出平衡裁决（不确定项与证据缺口必须显式）

## Fixtures

- `defgeo-ach-001`：支持证据占优
- `defgeo-ach-002`：反证占优
- `defgeo-ach-003`：证据不足（必须输出 gap）

## Acceptance

1. 每个假设必须包含支持/反证/缺口三类输出。
2. explain API 可回放到 Assertion/SourceClaim。
3. 对抗流程输出稳定，不得丢失冲突解释。
