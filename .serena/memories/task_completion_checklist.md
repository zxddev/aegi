# 任务完成检查清单

完成任何代码修改后，必须依次执行：

1. `cd code/aegi-core && uv run ruff check .`
2. `cd code/aegi-core && uv run ruff format .`
3. `cd code/aegi-core && uv run pytest`
4. `cd code/aegi-mcp-gateway && uv run ruff check .`
5. `cd code/aegi-mcp-gateway && uv run ruff format .`
6. `cd code/aegi-mcp-gateway && uv run pytest`

所有命令必须通过后才能宣称"完成"。
