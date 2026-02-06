<!-- Author: msq -->

# API 设计 + PostgreSQL 表设计

## 1. REST 设计

- 资源导向：资源是名词，操作用 HTTP 方法表达。
- HTTP 方法语义：GET（读取/幂等）、POST（创建）、PUT（整体替换/幂等）、PATCH（部分更新）、DELETE（删除/幂等）。
- 强制偏好：
  - 集合用复数（`/api/users`）
  - 正确状态码（2xx/4xx/5xx）
  - 大集合必须分页
  - 从第一天规划版本化
  - 限流与鉴权工程化
  - 文档优先：OpenAPI/Swagger

## 2. GraphQL 设计

- Schema-first：先设计 schema 再写 resolver。
- 避免 N+1：使用 DataLoader/batching。
- 输入验证：schema + resolver 双层兜底。
- 分页：优先游标分页（Relay 规范）。

## 3. PostgreSQL 核心规则

- ID 优先 `BIGINT GENERATED ALWAYS AS IDENTITY`；仅在需要全局唯一性时用 `UUID`。
- 先规范化到 3NF；只有测量证明 join 成本不可接受时才反规范化。
- 能 `NOT NULL` 就 `NOT NULL`；常见值提供 `DEFAULT`。
- 索引按真实查询路径设计：PK/unique（自动）、**FK 列（手动！）**、常用过滤/排序。

## 4. PostgreSQL 常见"坑"

- 标识符不带引号会自动小写化；统一 `snake_case`。
- `UNIQUE` + `NULL`：允许多个 NULL；需要时用 `NULLS NOT DISTINCT`（PG15+）。
- FK 不会自动建索引：必须手动建。
- identity/序列有间隙是正常现象。

## 5. 数据类型偏好

| 场景 | 推荐 | 避免 |
|------|------|------|
| 时间 | `TIMESTAMPTZ` | 无时区 `timestamp` |
| 金额 | `NUMERIC(p,s)` | `float`、`money` |
| 字符串 | `TEXT` + `CHECK` | — |
| JSON | `JSONB` + GIN 索引 | 仅用于半结构化属性 |

## 6. 索引选择

- **B-tree**：等值/范围/排序（默认）
- **复合索引**：最左前缀原则；顺序比列数更重要
- **覆盖索引**：`INCLUDE` 提升仅索引扫描命中率
- **部分索引**：只为热子集建（`WHERE status = 'active'`）
- **GIN**：JSONB/数组/全文
- **BRIN**：超大且自然有序（时间序列）
