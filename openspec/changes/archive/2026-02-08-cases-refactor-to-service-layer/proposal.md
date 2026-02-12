# Proposal: Cases API 服务层重构

## 问题
routes/cases.py（486行）混合了路由参数解析和业务逻辑，违反单一职责原则。

## 方案
将业务逻辑迁移到 service 层（case_service / tool_archive_service / fixture_import_service），路由层只做参数解析和 service 调用。

## 范围
- 纯内部重构，所有 API 签名不变
- 新增 3 个 service 文件，瘦化 routes/cases.py
