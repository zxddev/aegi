# Design: Cases API 服务层重构

## 架构

```
routes/cases.py (瘦路由) → services/case_service.py (DB 逻辑)
                          → services/tool_archive_service.py (归档逻辑)
                          → services/fixture_import_service.py (导入逻辑)
```

## 验收标准

- [x] 路由函数体不超过 10 行
- [x] 所有 API 签名不变
- [x] 现有测试全部通过
- [x] ruff clean
