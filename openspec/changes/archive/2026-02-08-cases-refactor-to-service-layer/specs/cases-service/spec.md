<!-- Author: msq -->

## ADDED Requirements

### Requirement: Route handlers MUST delegate to service layer
路由函数 MUST 只做参数解析和 service 调用，函数体不超过 10 行。

#### Scenario: Route delegates to CaseService
- **WHEN** 收到 POST /cases 请求
- **THEN** 路由调用 case_service.create_case()，不直接操作 DB

### Requirement: Service layer MUST encapsulate all DB logic
所有 DB 操作 MUST 封装在 service 层，路由层不直接使用 session。

#### Scenario: Tool archive uses service
- **WHEN** 收到 archive_url 请求
- **THEN** 路由调用 tool_archive_service，Action/ToolTrace 创建在 service 内完成
