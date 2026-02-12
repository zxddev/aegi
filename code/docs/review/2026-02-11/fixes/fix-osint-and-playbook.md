# Fix: OSINT Claims 回流 + Playbook YAML 加载

## 问题 A：OSINT 采集结果未回流 pipeline 数据流

**文件**: `src/aegi_core/services/stages/osint_collect.py`

**现状**: `OSINTCollectStage.run()` 采集到的 `source_claim_uids` 只存到了 `ctx.config["osint_claim_uids"]`，没有加载为 `SourceClaimV1` 对象合入 `ctx.source_claims`。导致后续 `assertion_fuse`、`narrative_build` 等 stage 拿不到 OSINT 采集的数据。

**修复**:
- 新增 `_load_claims()` 静态方法：通过 `sa.select(SourceClaim).where(uid.in_(uids))` 从 DB 加载行，转换为 `SourceClaimV1` Pydantic 对象
- 在 `run()` 中采集完成后调用 `_load_claims()`，将结果 `extend` 到 `ctx.source_claims`
- `StageResult.output` 新增 `claims_loaded` 字段，方便观测实际加载数量

## 问题 B：Playbook YAML 未在启动时加载

**结论**: 已修复，无需额外改动。

`main.py` 的 `lifespan` 中（第 77-83 行）已包含 playbook 加载逻辑：
```python
from aegi_core.services.stages.playbook import load_playbooks
_pb_path = Path(__file__).resolve().parent.parent.parent.parent / "deploy" / "playbooks.yaml"
if _pb_path.exists():
    load_playbooks(_pb_path)
```

`deploy/playbooks.yaml` 已定义 7 个 playbook，包括 `osint_deep`。

## 测试验证

```
uv run pytest tests/test_osint_stage.py tests/test_pipeline_orchestration.py tests/test_osint_integration.py -x -v
# 15 passed, 4 skipped (需要真实 SearXNG)
```
