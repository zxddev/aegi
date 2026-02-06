# baize-mcp-gateway

独立 MCP Gateway 服务，用于统一工具调用入口与鉴权。

## 运行方式（开发）

```bash
set -a
source .env
set +a
PYTHONPATH=./src python3 -m uvicorn baize_mcp_gateway.main:app --reload --host 0.0.0.0 --port 9100
```

## 环境变量

- `MCP_GATEWAY_ENV`：运行环境（默认 dev）
- `MCP_API_KEY`：API Key（必须）
- `MCP_TOOL_REGISTRY_PATH`：工具注册表路径（必须）
- `MCP_REQUEST_TIMEOUT_MS`：请求超时（毫秒，必须）
- `MCP_HOST` / `MCP_PORT`：监听地址与端口（必须）
- `MCP_ALLOWED_DOMAINS`：允许域名列表（逗号分隔，必须设置才能抓取）
- `MCP_DENIED_DOMAINS`：拒绝域名列表（逗号分隔）
- `MCP_DOMAIN_RPS`：每域名请求速率（默认 2）
- `MCP_DOMAIN_CONCURRENCY`：每域名并发限制（默认 2）
- `MCP_CACHE_TTL_SECONDS`：响应缓存 TTL（默认 300）
- `MCP_ROBOTS_REQUIRE_ALLOW`：robots.txt 必须允许（默认 true）
- `MCP_DB_DSN`：Scrape Guard 数据库连接串（启用数据库模式时必须）
- `MCP_GUARD_USE_DB`：是否从数据库读取域名与阈值（默认 true）
- `MCP_GUARD_REFRESH_SECONDS`：域名清单刷新间隔秒数（默认 60）
- `MCP_MAX_CONTENT_BYTES`：单次响应/内容最大字节数（默认 5000000）
- `MCP_ALLOWED_MIME_TYPES`：允许的 MIME 类型（逗号分隔）
- `MINIO_ENDPOINT`：MinIO 地址（doc_parse 读取 Artifact）
- `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`：MinIO 凭据
- `MINIO_SECURE`：是否启用 HTTPS
- `MINIO_BUCKET`：Artifact 存储桶
- `ARCHIVEBOX_HOST`：ArchiveBox Web 地址
- `ARCHIVEBOX_PORT`：ArchiveBox 端口
- `ARCHIVEBOX_CONTAINER`：ArchiveBox 容器名
- `ARCHIVEBOX_USER`：ArchiveBox 容器内用户

## 工具注册表

`tool_registry.json` 需要配置实际工具地址，未注册工具将直接返回 404。

### SearxNG（meta_search）适配

网关内置 `searxng` 适配器，会把 SearxNG JSON 输出规范化为 `meta_search` 协议。

`tool_registry.json` 示例：

```json
{
  "tools": {
    "meta_search": {
      "url": "http://192.168.31.50:8601/search",
      "method": "GET",
      "adapter": "searxng"
    }
  }
}
```

注意：如果 SearxNG 不在本机，请改成实际地址，例如 `http://192.168.31.50:8601/search`。

### Unstructured（doc_parse）适配

网关内置 `unstructured` 适配器，输入只接受 `artifact_uid`、`chunk_size`、`chunk_overlap`。
适配器会从 MinIO 读取对应 Artifact，再调用 Unstructured 解析并输出 `Chunk[]`。

### ArchiveBox（archive_url）适配

网关内置 `archivebox` 适配器，通过 `docker exec` 调用 ArchiveBox CLI。
输出必须包含 `timestamp`、`content_sha256` 与 `mime_type` 字段，否则会直接报错。

## Scrape Guard 配置

- `MCP_ALLOWED_DOMAINS` 必须配置，否则外联工具会被拒绝。
- `MCP_DENIED_DOMAINS` 可选，优先级高于允许列表。
- `MCP_DOMAIN_RPS` 与 `MCP_DOMAIN_CONCURRENCY` 为每域限制。
- `MCP_CACHE_TTL_SECONDS` 控制响应缓存。
- `MCP_ROBOTS_REQUIRE_ALLOW` 为 true 时，robots.txt 不允许则拒绝。

## 协议

- `GET /health`
- `POST /tools/{tool_name}/invoke`

Header: `Authorization: Bearer <MCP_API_KEY>`
