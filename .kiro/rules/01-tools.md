<!-- Author: msq -->

# 工具使用手册与操作细则

## 0. Kiro 原生工具

以下工具始终可用，无需额外配置：
- `fs_read` / `fs_write`：文件读写
- `execute_bash`：执行 shell 命令
- `grep` / `glob`：文本搜索与文件查找
- `code`：AST 级代码分析（search_symbols、pattern_search 等）

## 1. MCP 扩展工具

以下工具通过 Kiro CLI 全局配置或 `dev.json` 的 `mcpServers` 加载。

### 1.1 serena（语义代码分析与精确编辑）

改代码前必须先理解。常用：
- `serena_get_symbols_overview`：文件顶层符号结构
- `serena_find_symbol`：按名称/路径查符号
- `serena_find_referencing_symbols`：找引用点
- `serena_read_file`：读取文件/片段
- `serena_replace_content`：literal/regex 安全替换
- `serena_insert_before_symbol` / `serena_insert_after_symbol`：符号边界插入

### 1.2 sequentialthinking（深度思考/分步推理）

见 `00-mandatory.md` §0.3。先拆步骤再动手，每步对应证据/输入/输出。

### 1.3 context7（权威库文档查询）

流程：`resolve-library-id` → `query-docs`。

### 1.4 langchain-docs（LangChain 文档检索）

涉及 LangChain/LangGraph/Deep Agents 时优先使用。

### 1.5 deepwiki（外部仓库结构化阅读）

快速理解 GitHub 仓库模块结构、关键文件、设计思路。

### 1.6 github（GitHub 读写操作）

Issue/PR/文件内容读取，创建 issue/PR，查询 diff/状态。

### 1.7 repomix（代码库打包索引）

需要全局理解或跨大量文件检索时使用。排除 `.venv/`、`node_modules/`。

### 1.8 exa / tavily（网络搜索）

- `exa`：代码示例/官方仓库/StackOverflow
- `tavily`：通用检索

### 1.9 playwright（网页交互/可视化抓取）

登录后页面抓取、复杂渲染、下载、截图、表单交互。

### 1.10 postgres（只读数据库查询）

只允许 SELECT。任何写操作一律禁止。

## 2. 操作细则

- 先 `Glob` 找文件 → `Grep` 定位内容 → `serena_*` 做符号级修改。
- 大范围理解用 `repomix`，排除 `.venv/`、`node_modules/`、大文件。
- 永远不要并行编辑同一个文件。
- 运行命令前先确认工具存在（`uv`、`ruff`、`pytest`），在正确目录执行。
- 探索代码库优先 `Grep`/`Glob`/目录列表；不要用 shell 的 `find/grep` 代替。
- 路径默认用绝对路径；引用文件时用"仓库相对路径 + 行号"更可审计。

## 3. 工具优先级

| 场景 | 优先 | 次选 | 兜底 |
|------|------|------|------|
| 改代码前理解 | serena（符号级） | Grep/Glob | repomix |
| 查外部知识 | context7 / langchain-docs | exa / tavily | — |
| 完成宣称 | 必须先跑验证命令 | — | — |
