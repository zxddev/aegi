<!-- Author: msq -->

# cases.py 拆分重构

> 目标：将 routes/cases.py（486行）中的业务逻辑迁移到 service 层，路由层只做参数解析和 service 调用。

## 1. 拆分 service

- [ ] 1.1 新增 `services/case_service.py`：迁移 create_case / get_case / list_case_artifacts 的 DB 逻辑
- [ ] 1.2 新增 `services/tool_archive_service.py`：迁移 call_tool_archive_url 的 Action+ToolTrace 创建逻辑
- [ ] 1.3 新增 `services/fixture_import_service.py`：迁移 import_fixture 的批量导入逻辑

## 2. 瘦化路由层

- [ ] 2.1 routes/cases.py 改为调用 service 层函数，路由函数体不超过 10 行
- [ ] 2.2 保持所有 API 签名（路径、参数、响应模型）不变，纯内部重构

## 3. 验证

- [ ] 3.1 现有 cases 相关测试全部通过，无行为变更
- [ ] 3.2 全量 pytest 无回归
- [ ] 3.3 ruff check 通过
