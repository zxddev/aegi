# CC-3: Fix report_generate always skipped + SSE progress callback bug

## Issue A: ReportGenerateStage always skipped

**Root cause**: `should_skip()` checked `ctx.config.get("generate_report")` — since no playbook
ever set this config key, the falsy `None` default caused the stage to always be skipped.

**Fix** (builtin.py line 242-244):
- Changed condition from `if not ctx.config.get("generate_report")` to
  `if ctx.config.get("generate_report") is False`
- Default behavior is now to run the report stage; only an explicit `generate_report: false`
  in stage_config will skip it.

**Playbook changes** (deploy/playbooks.yaml + playbook.py):
- Added `report_generate` to `default`, `deep`, and `osint_deep` playbook stage lists
- Updated `DEFAULT_STAGES` in playbook.py to include `report_generate`

## Issue B: SSE stages_completed always empty

**Root cause**: `_on_progress` callback in pipeline_stream.py used `'result' in dir()` to check
if the `result` variable existed. Since `result` is only assigned after `orch.run_playbook()`
returns, this was always `False` during pipeline execution, yielding `stages_completed: []`.

**Fix** (pipeline_stream.py line 99-110):
- Replaced the broken `dir()` check with a local `completed_stages: list[str]` accumulator
- The callback now appends the stage name when `status` is `"success"` or `"skipped"`
- `tracker.update()` receives the incrementally built list

## Verification

```bash
uv run pytest tests/test_pipeline_stream_api.py tests/test_pipeline_orchestration.py -x -v
# 16 passed
```
