# Proposal: assertion_fuser 时间冲突 + 地理冲突检测

## Why
fuse_claims 只做简单去重，缺少时间矛盾和地理矛盾检测。

## What
- 新增 `_detect_temporal_conflict`：同一 attributed_to 的 claims 时间表达矛盾
- 新增 `_detect_geographic_conflict`：同一时间段同一实体出现在不同地点
