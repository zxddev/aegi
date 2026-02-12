# Design: 端到端 Pipeline 编排

## 架构

```
POST /pipelines/full_analysis → PipelineOrchestrator.run_full()
POST /pipelines/run_stage     → PipelineOrchestrator.run_stage()

STAGE_ORDER: assertion_fuse → hypothesis_analyze → narrative_build → kg_build → forecast_generate → quality_score
```

## 验收标准

- [x] 全链路执行产出 PipelineResult
- [x] 支持从任意阶段开始 / 只执行子集
- [x] 缺失输入时 skip 而非 crash
- [x] 全量 pytest 通过
- [x] ruff clean
