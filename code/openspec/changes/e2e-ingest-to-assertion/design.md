# E2E Ingest to Assertion Design

## 架构设计

### 端到端数据流架构
```
File Upload → Gateway (doc_parse) → Core (ingest) → Core (claim_extract) → Core (assertion_fuse)
     ↓              ↓                    ↓                ↓                      ↓
  Storage      Unstructured API      Chunks         SourceClaims         Assertions
```

### 组件集成设计
```python
# Gateway ASGI Tool Client
class _AsgiGatewayToolClient:
    """通过 ASGI transport 调用真实 Gateway app"""
    
    async def doc_parse(self, artifact_version_uid: str, 
                       file_url: str | None = None) -> dict

# Mock 外部依赖
def _make_mock_httpx_client():
    """Mock Unstructured API 和文件下载"""
```

### 测试数据设计
```python
MOCK_UNSTRUCTURED_ELEMENTS = [
    {
        "text": "军事演习在台湾海峡附近展开",
        "type": "NarrativeText", 
        "metadata": {"page_number": 1}
    }
]

MOCK_LLM_CLAIMS = [
    {
        "quote": "军事演习在台湾海峡附近展开",
        "selectors": [{"type": "TextQuoteSelector", "exact": "..."}],
        "attributed_to": "官方声明"
    }
]
```

## 数据流设计

### 完整管道流程
1. **文档摄取 (ingest)**
   - 接收 `artifact_version_uid` 和 `file_url`
   - 通过 Gateway 调用 Unstructured API 解析文档
   - 创建 Chunk 记录，返回 `chunk_uids`

2. **声明提取 (claim_extract)**
   - 对每个 chunk 调用 LLM 提取声明
   - 创建 SourceClaim 记录
   - 返回 `claim_uids`

3. **断言融合 (assertion_fuse)**
   - 接收所有 `source_claim_uids`
   - 融合相关声明生成断言
   - 创建 Assertion 记录
   - 返回 `assertion_uids`

### 错误处理策略
- Gateway 内部 HTTP 调用通过 mock 拦截
- LLM 调用通过依赖注入 mock
- 数据库操作使用真实 PostgreSQL
- 异常传播和错误响应验证

## Mock 策略设计

### HTTP 调用 Mock
```python
# Mock Gateway 内部的 httpx.AsyncClient
with patch("aegi_mcp_gateway.api.routes.tools.httpx.AsyncClient", 
           return_value=mock_httpx):
    # 执行 ingest 调用
```

### LLM 调用 Mock  
```python
# 通过依赖注入 mock LLM
mock_llm = AsyncMock()
mock_llm.invoke = AsyncMock(return_value=MOCK_LLM_CLAIMS)
app.dependency_overrides[get_llm_client] = lambda: mock_llm
```

### 真实组件保留
- PostgreSQL 数据库连接
- SQLAlchemy ORM 操作
- FastAPI 应用和路由
- 数据模型验证

## 验收标准

### 功能验收
- [x] 端到端数据流完整性验证
- [x] 每个阶段输出格式正确
- [x] 数据库记录创建正确
- [x] 错误处理机制有效

### 集成验收  
- [x] Gateway 和 Core 应用集成
- [x] ASGI transport 通信正常
- [x] Mock 策略有效隔离外部依赖
- [x] 真实数据库操作验证

### 数据验证
- [x] Chunk 数据与 Unstructured 输出对应
- [x] SourceClaim 数据与 LLM 输出对应  
- [x] Assertion 数据与融合逻辑对应
- [x] 数据关联关系正确

### 测试验证
- [x] 测试用例 `test_full_pipeline_ingest_to_assertion` 通过
- [x] Mock 数据覆盖多语言场景
- [x] 异常场景处理验证
- [x] 性能基准满足要求