# Cases API Refactor to Service Layer

## 背景
当前 Cases API 直接在路由层处理业务逻辑，需要重构到服务层以提高可测试性和代码复用性。

## 任务

### 1. 重构 case_service.py
- 将现有的 `create_case`, `get_case`, `list_case_artifacts` 函数重构为 `CaseService` 类
- 实现依赖注入模式，接受 `AsyncSession` 作为构造参数
- 保持现有 API 契约不变

### 2. 更新 API 路由
- 修改 `/cases` 路由使用新的 `CaseService` 类
- 通过依赖注入获取服务实例
- 确保响应格式保持一致

### 3. 测试验证
- 现有测试 `test_cases_api.py` 应继续通过
- 添加服务层单元测试
- 验证错误处理逻辑不变

## 验收标准
- [x] `CaseService` 类实现完成
- [x] API 路由重构完成
- [x] 所有现有测试通过
- [x] 新增服务层测试覆盖