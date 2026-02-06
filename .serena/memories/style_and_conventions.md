# 代码风格与约定

- Python 3.12, type hints 必须, Google 风格 docstring
- ruff lint + format, line-length=100
- 禁止裸 except, 异常必须具体
- FastAPI 路由优先 async def
- 文件头部必须有 `# Author: msq`
- 注释使用中文
- 测试: pytest + pytest-asyncio, asyncio_mode=auto
