# End-to-End Pipeline Orchestration Proposal

## 问题描述

当前系统缺乏统一的管道编排机制，存在以下问题：

1. **缺乏端到端编排**: 各个分析阶段独立运行，缺乏统一的编排和状态管理
2. **增量执行困难**: 无法从中间阶段开始执行，必须重新运行整个管道
3. **错误处理不完善**: 缺乏降级机制，单个阶段失败导致整个管道崩溃
4. **状态跟踪缺失**: 无法跟踪管道执行状态和各阶段耗时

## 解决方案

### 核心方案
实现统一的管道编排器 `PipelineOrchestrator`，提供：

1. **全链路编排**
   - 定义标准阶段顺序：`assertion_fuse` → `hypothesis_analyze` → `forecast_generate` → `quality_score`
   - 自动处理阶段间数据传递
   - 统一的执行结果格式

2. **增量执行支持**
   - 支持从任意阶段开始执行
   - 智能跳过已完成的阶段
   - 支持指定阶段子集执行

3. **降级处理机制**
   - 空输入时自动跳过（skip）
   - 弱证据时降级执行（degraded）
   - 错误时优雅失败，不影响后续阶段

### 技术架构
```python
class PipelineOrchestrator:
    def run_full(
        self, 
        case_uid: str,
        source_claims: list[SourceClaimV1],
        start_from: str | None = None,
        stages: list[str] | None = None
    ) -> PipelineResult
    
    def run_stage(
        self, 
        stage_name: str, 
        inputs: dict
    ) -> StageResult
```

### API 设计
- `POST /cases/{case_uid}/pipelines/full_analysis` - 全链路分析
- `POST /cases/{case_uid}/pipelines/run_stage` - 单阶段执行

## 影响范围

### 新增组件
- `services/pipeline_orchestrator.py` - 核心编排器
- `api/routes/orchestration.py` - API 路由
- 测试 fixtures 支持多场景验证

### 集成点
- 与现有各阶段服务集成
- 数据库状态持久化
- 错误监控和日志

## 风险评估

**中等风险**:
- 新增核心组件，需要充分测试
- 与现有服务集成可能存在兼容性问题
- 需要处理复杂的错误场景

**缓解措施**:
- 分阶段实现和测试
- 保持现有 API 不变
- 完善的测试覆盖和监控