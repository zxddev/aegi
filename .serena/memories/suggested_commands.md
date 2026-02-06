# 常用命令

## aegi-core
```bash
cd code/aegi-core
uv run ruff check .          # lint 检查
uv run ruff format .         # 格式化
uv run pytest                # 运行测试
uv run pytest -x             # 遇到第一个失败即停
uv run pytest tests/contract_tests/  # 仅契约测试
```

## aegi-mcp-gateway
```bash
cd code/aegi-mcp-gateway
uv run ruff check .
uv run ruff format .
uv run pytest
```

## 系统工具
- git, ls, cd, grep, find (Linux)
