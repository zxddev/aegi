# Cases API Service Layer Refactor Proposal

## 问题描述

当前 Cases API 的业务逻辑直接在路由层实现，存在以下问题：

1. **可测试性差**: 业务逻辑与 HTTP 层耦合，难以进行单元测试
2. **代码复用性低**: 业务逻辑无法在其他上下文中复用
3. **架构不一致**: 其他模块已采用服务层模式，Cases 模块需要保持一致

## 解决方案

### 核心方案
将 Cases 相关业务逻辑从路由层重构到服务层：

1. **创建 CaseService 类**
   - 封装现有的 `create_case`, `get_case`, `list_case_artifacts` 函数
   - 采用依赖注入模式，接受 `AsyncSession` 作为构造参数
   - 保持现有函数签名和返回格式

2. **更新 API 路由**
   - 修改 `aegi_core.api.routes.cases` 使用新的服务类
   - 通过 FastAPI 依赖注入获取服务实例
   - 保持 API 契约不变

### 技术实现
```python
class CaseService:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_case(self, *, title: str, actor_id: str | None, 
                         rationale: str | None, inputs: dict) -> dict:
        # 现有逻辑迁移
    
    async def get_case(self, *, case_uid: str) -> dict:
        # 现有逻辑迁移
    
    async def list_case_artifacts(self, *, case_uid: str) -> dict:
        # 现有逻辑迁移
```

## 影响范围

### 修改文件
- `aegi_core/services/case_service.py` - 重构为类
- `aegi_core/api/routes/cases.py` - 使用新服务类
- `aegi_core/api/deps.py` - 添加服务依赖注入

### 测试影响
- 现有集成测试保持不变
- 新增服务层单元测试

## 风险评估

**低风险**: 
- 纯重构，不改变外部 API 契约
- 现有测试可验证功能完整性
- 可逐步迁移，支持回滚