# End-to-End Pipeline Orchestration Design

## 架构设计

### 管道编排架构
```
API Layer (routes/orchestration.py)
    ↓
Orchestrator (services/pipeline_orchestrator.py)
    ↓
Stage Services (assertion_fuser, hypothesis_engine, etc.)
    ↓
Data Layer (各种 models)
```

### 核心类设计
```python
@dataclass
class StageResult:
    stage: str
    status: Literal["success", "skipped", "degraded", "error"]
    output: Any | None
    error: str | None
    duration_ms: int

@dataclass  
class PipelineResult:
    case_uid: str
    stages: list[StageResult]
    total_duration_ms: int

class PipelineOrchestrator:
    STAGE_ORDER = [
        "assertion_fuse",
        "hypothesis_analyze", 
        "forecast_generate",
        "quality_score"
    ]
    
    def run_full(self, case_uid: str, source_claims: list[SourceClaimV1], 
                 start_from: str | None = None, 
                 stages: list[str] | None = None) -> PipelineResult
    
    def run_stage(self, stage_name: str, inputs: dict) -> StageResult
```

### 阶段执行逻辑
```python
def _execute_stage(self, stage_name: str, context: dict) -> StageResult:
    """执行单个阶段，处理各种状态"""
    try:
        # 检查输入条件
        if not self._has_required_inputs(stage_name, context):
            return StageResult(stage=stage_name, status="skipped", ...)
        
        # 执行阶段逻辑
        output = self._stage_handlers[stage_name](context)
        
        # 检查输出质量
        if self._is_degraded_output(output):
            return StageResult(stage=stage_name, status="degraded", ...)
        
        return StageResult(stage=stage_name, status="success", ...)
        
    except Exception as e:
        return StageResult(stage=stage_name, status="error", error=str(e), ...)
```

## 数据流设计

### 全链路执行流程
1. **输入验证**: 检查 source_claims 有效性
2. **阶段规划**: 确定执行阶段列表和起始点
3. **逐阶段执行**: 按顺序执行各阶段，传递上下文
4. **结果聚合**: 收集各阶段结果，计算总耗时

### 增量执行流程
1. **状态检查**: 确定已完成的阶段
2. **起始点定位**: 从指定阶段开始
3. **上下文重建**: 从数据库恢复中间状态
4. **继续执行**: 执行剩余阶段

### 降级处理策略
- **空输入**: `source_claims=[]` → 所有阶段 skip
- **弱证据**: `confidence < 0.3` → forecast 降级
- **服务异常**: 单阶段错误不影响后续阶段

## API 设计

### 全链路分析端点
```http
POST /cases/{case_uid}/pipelines/full_analysis
Content-Type: application/json

{
  "source_claim_uids": ["sc_001", "sc_002"],
  "start_from": "hypothesis_analyze",  // 可选
  "stages": ["assertion_fuse", "quality_score"]  // 可选
}

Response:
{
  "case_uid": "case_001",
  "stages": [
    {
      "stage": "assertion_fuse",
      "status": "success",
      "duration_ms": 1500,
      "output": {...}
    }
  ],
  "total_duration_ms": 3000
}
```

### 单阶段执行端点
```http
POST /cases/{case_uid}/pipelines/run_stage
Content-Type: application/json

{
  "stage_name": "assertion_fuse",
  "inputs": {
    "source_claims": [...]
  }
}

Response:
{
  "stage": "assertion_fuse",
  "status": "success", 
  "duration_ms": 1500,
  "output": {...}
}
```

## 验收标准

### 功能验收
- [x] PipelineOrchestrator 类实现完成
- [x] 支持全链路执行（defgeo-claim-001）
- [x] 支持增量执行（defgeo-ach-001）
- [x] 支持降级处理（defgeo-forecast-003）
- [x] API 端点实现完成

### 性能验收
- [x] 单阶段执行时间 < 5秒
- [x] 全链路执行时间 < 30秒
- [x] 内存使用合理

### 可靠性验收
- [x] 单阶段失败不影响其他阶段
- [x] 空输入优雅处理
- [x] 异常情况有详细错误信息

### 测试验收
- [x] 全链路测试覆盖
- [x] 增量执行测试覆盖
- [x] 降级路径测试覆盖
- [x] API 集成测试覆盖