<!-- Author: msq -->

## Decisions

1. 叙事与 SourceClaim 多对多关联。
2. 协同检测输出置信度与误报解释。

## Input / Output Contracts

- 输入：`SourceClaimV1[]`、`AssertionV1[]`、时间窗口参数
- 输出：`NarrativeV1[]`
  - 必填：`narrative_uid`、`theme`、`source_claim_uids`、`first_seen_at`、`latest_seen_at`
- 协同检测输出：`CoordinationSignalV1[]`
  - 必填：`group_id`、`similarity_score`、`time_burst_score`、`confidence`

## API Contract

- `POST /cases/{case_uid}/narratives/build`
- `POST /cases/{case_uid}/narratives/detect_coordination`
- `GET /cases/{case_uid}/narratives/{narrative_uid}/trace`

## Detection Strategy

1. 叙事聚类：语义相似 + 事件窗口约束
2. 溯源：按最早出现时间定位源节点
3. 协同：短时间高相似批量传播标记为可疑

## Fixtures

- `defgeo-narrative-001`：单叙事自然传播
- `defgeo-narrative-002`：疑似协同传播
- `defgeo-narrative-003`：冲突叙事并存

## Acceptance

1. 每条叙事链可回放到 source_claim。
2. 协同检测输出必须包含误报解释字段。
3. 冲突叙事不得被覆盖或丢弃。
