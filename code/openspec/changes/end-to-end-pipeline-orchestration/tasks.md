# End-to-End Pipeline Orchestration

## 背景
实现完整的端到端分析管道编排，支持从 source claims 到 forecast 的全链路处理，包括增量执行和降级处理。

## 任务

### 1. 核心编排器实现
- 实现 `PipelineOrchestrator` 类，支持全链路执行
- 定义标准阶段顺序：`assertion_fuse` → `hypothesis_analyze` → `forecast_generate` → `quality_score`
- 支持从任意阶段开始执行（增量模式）

### 2. 阶段管理
- 实现 `run_full()` 方法支持完整管道执行
- 实现 `run_stage()` 方法支持单阶段执行
- 支持指定阶段子集执行

### 3. 降级路径处理
- 空输入时阶段自动跳过（skip）而非崩溃
- 弱证据场景下降级执行（degraded）
- 错误恢复机制

### 4. API 集成
- 实现 `/cases/{case_uid}/pipelines/full_analysis` 端点
- 实现 `/cases/{case_uid}/pipelines/run_stage` 端点
- 返回标准化的执行结果格式

## 测试场景

### 4.1 全链路测试 (defgeo-claim-001)
- 从 source_claims 开始完整执行
- 验证所有阶段按顺序执行
- 确保无崩溃发生

### 4.2 增量测试 (defgeo-ach-001)
- 从 hypothesis_analyze 阶段开始
- 跳过已完成的 assertion_fuse 阶段
- 验证阶段依赖正确处理

### 4.3 降级测试 (defgeo-forecast-003)
- 弱证据输入场景
- forecast 阶段降级但不崩溃
- 验证错误恢复机制

## 验收标准
- [x] PipelineOrchestrator 实现完成
- [x] 全链路测试通过
- [x] 增量执行测试通过
- [x] 降级路径测试通过
- [x] API 端点实现完成