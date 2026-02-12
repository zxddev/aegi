# Cases Service Layer Design

## 架构设计

### 服务层架构
```
API Layer (routes/cases.py)
    ↓ (依赖注入)
Service Layer (services/case_service.py)
    ↓
Data Layer (db/models/case.py, db/models/action.py)
```

### 类设计
```python
class CaseService:
    """Cases 业务逻辑服务类"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_case(
        self, *, title: str, actor_id: str | None, 
        rationale: str | None, inputs: dict
    ) -> dict:
        """创建 Case 及关联 Action"""
        
    async def get_case(self, *, case_uid: str) -> dict:
        """获取 Case 详情"""
        
    async def list_case_artifacts(self, *, case_uid: str) -> dict:
        """列出 Case 关联的 Artifacts"""
```

### 依赖注入设计
```python
# aegi_core/api/deps.py
async def get_case_service(session: AsyncSession = Depends(get_session)) -> CaseService:
    return CaseService(session)

# aegi_core/api/routes/cases.py
@router.post("/cases")
async def create_case(
    request: CreateCaseRequest,
    service: CaseService = Depends(get_case_service)
):
    return await service.create_case(...)
```

## 数据流设计

### 创建 Case 流程
1. API 接收请求 → 验证参数
2. Service 生成 UIDs → 创建 Case 和 Action 记录
3. 数据库事务提交 → 返回响应

### 错误处理
- 保持现有错误处理逻辑
- 404 错误通过 `not_found()` 函数抛出
- 数据库错误由 SQLAlchemy 处理

## 验收标准

### 功能验收
- [x] CaseService 类实现完成
- [x] 支持依赖注入模式
- [x] API 路由重构完成
- [x] 保持现有 API 契约

### 测试验收
- [x] 现有集成测试 `test_cases_api.py` 通过
- [x] 新增服务层单元测试
- [x] 错误处理测试覆盖

### 性能验收
- [x] 响应时间无明显变化
- [x] 内存使用无明显增加

### 代码质量验收
- [x] 代码符合项目规范
- [x] 类型注解完整
- [x] 文档字符串完整