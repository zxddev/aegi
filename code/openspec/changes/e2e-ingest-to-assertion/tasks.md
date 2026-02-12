# E2E Ingest to Assertion Integration

## 背景
实现从文档摄取到断言生成的完整端到端集成测试，验证 Gateway 和 Core 应用间的数据流。

## 任务

### 1. Gateway 集成测试框架
- 实现 `_AsgiGatewayToolClient` 通过 ASGI transport 调用 Gateway
- 保持真实的 Gateway 应用逻辑
- 支持 `doc_parse` 工具调用

### 2. 外部依赖 Mock 策略
- Mock Unstructured API HTTP 调用
- Mock 文件下载请求
- Mock LLM 调用返回预设声明
- 保持数据库操作真实性

### 3. 端到端数据流验证
- 验证 ingest → claim_extract → assertion_fuse 完整链路
- 确保每个阶段的输入输出格式正确
- 验证数据库中的完整数据链

### 4. 多语言场景支持
- 中文内容处理验证
- 英文内容处理验证
- 混合语言场景测试

## 测试数据设计

### Mock Unstructured 输出
```python
MOCK_UNSTRUCTURED_ELEMENTS = [
    {
        "text": "军事演习在台湾海峡附近展开",
        "type": "NarrativeText",
        "metadata": {"page_number": 1, "filename": "report.pdf"}
    },
    {
        "text": "Oil prices surged due to geopolitical tensions", 
        "type": "NarrativeText",
        "metadata": {"page_number": 2}
    }
]
```

### Mock LLM 声明输出
```python
MOCK_LLM_CLAIMS = [
    {
        "quote": "军事演习在台湾海峡附近展开",
        "selectors": [{"type": "TextQuoteSelector", "exact": "军事演习在台湾海峡附近展开"}],
        "attributed_to": "官方声明"
    }
]
```

## 验收标准
- [x] Gateway ASGI 集成测试框架完成
- [x] 外部依赖 Mock 策略实现
- [x] 端到端数据流验证通过
- [x] 多语言场景测试覆盖
- [x] 数据库完整性验证通过