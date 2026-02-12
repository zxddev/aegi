# E2E Ingest to Assertion Integration Proposal

## 问题描述

当前系统缺乏端到端集成测试，存在以下问题：

1. **组件间集成验证不足**: Gateway 和 Core 应用间的数据流缺乏验证
2. **外部依赖测试困难**: Unstructured API 和 LLM 调用难以在测试环境中稳定运行
3. **数据链完整性未验证**: 从文档到断言的完整数据转换链路缺乏验证
4. **多语言场景覆盖不足**: 中英文混合内容处理的集成测试缺失

## 解决方案

### 核心方案
实现完整的端到端集成测试框架：

1. **真实应用集成**
   - 使用 ASGI transport 调用真实的 Gateway 应用
   - 保持 Core 应用的完整业务逻辑
   - 验证应用间的真实通信

2. **智能 Mock 策略**
   - Mock 外部 HTTP 调用（Unstructured API、文件下载）
   - Mock LLM 调用返回预设的结构化数据
   - 保持数据库操作的真实性

3. **完整数据流验证**
   - 验证 ingest → claim_extract → assertion_fuse 链路
   - 检查每个阶段的数据格式和内容正确性
   - 确保数据库中的关联关系完整

### 技术实现
```python
class _AsgiGatewayToolClient:
    """通过 ASGI transport 调用真实 Gateway app"""
    
    def __init__(self, gateway_app):
        self._transport = httpx.ASGITransport(app=gateway_app)
    
    async def doc_parse(self, artifact_version_uid: str, 
                       file_url: str | None = None) -> dict:
        # 真实的 Gateway 调用
```

### Mock 策略
```python
# Mock Gateway 内部的外部调用
with patch("aegi_mcp_gateway.api.routes.tools.httpx.AsyncClient"):
    # Mock Unstructured API 和文件下载
    
# Mock Core 应用的 LLM 依赖
app.dependency_overrides[get_llm_client] = lambda: mock_llm
```

## 影响范围

### 测试框架增强
- 新增 Gateway ASGI 集成测试工具
- 完善 Mock 策略和测试数据
- 增加端到端验证用例

### 数据验证覆盖
- Chunk 创建和内容验证
- SourceClaim 提取和格式验证
- Assertion 融合和关联验证

## 风险评估

**低风险**:
- 纯测试框架增强，不影响生产代码
- Mock 策略隔离外部依赖，测试稳定性高
- 可以逐步增加测试场景

**收益**:
- 提高系统集成可靠性
- 早期发现组件间兼容性问题
- 为多语言支持提供验证基础