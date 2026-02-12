# Proposal: 端到端 Pipeline 编排

## 问题
各 pipeline 阶段（claim_extract, assertion_fuse, hypothesis 等）独立存在，缺少统一编排层。

## 方案
新增 PipelineOrchestrator，支持全链路执行和增量单阶段触发，每阶段可独立跳过/降级。

## 范围
- 新增 services/pipeline_orchestrator.py
- 新增 POST /pipelines/full_analysis 和 /pipelines/run_stage 端点
- 新增 test_pipeline_orchestration.py
