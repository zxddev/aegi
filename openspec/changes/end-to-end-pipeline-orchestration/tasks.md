<!-- Author: msq -->

# 端到端 Pipeline 编排

> 目标：将独立 service 模块串联为完整分析 pipeline，支持一键从 Artifact 到 QualityReport 的全链路执行。

## 1. Pipeline 编排 service

- [x] 1.1 新增 `services/pipeline_orchestrator.py`：定义 FullAnalysisPipeline
- [x] 1.2 实现阶段编排：chunk → claim_extract → assertion_fuse → hypothesis_analyze → narrative_build → forecast_generate → quality_score
- [x] 1.3 每个阶段可独立跳过/降级（某阶段输入缺失时 skip 而非 fail）
- [x] 1.4 输出 PipelineResult：包含每阶段产物 + 耗时 + 状态（success/skipped/degraded）

## 2. 增量 Pipeline（单步触发）

- [x] 2.1 支持从任意阶段开始执行（如已有 assertions，直接从 hypothesis 开始）
- [x] 2.2 支持只执行指定阶段子集

## 3. API 暴露

- [x] 3.1 新增 `POST /cases/{case_uid}/pipelines/full_analysis`（全链路）
- [x] 3.2 新增 `POST /cases/{case_uid}/pipelines/run_stage`（单阶段）
- [x] 3.3 注入 DB session，每阶段产物持久化到 DB

## 4. 验证

- [x] 4.1 新增 `test_pipeline_orchestration.py`
- [x] 4.2 用现有 fixture 数据驱动全链路测试
- [x] 4.3 验证降级路径（缺失输入 → skip 而非 crash）
- [x] 4.4 全量 pytest 无回归
- [x] 4.5 ruff check 通过
