# 修复 test_tool_trace_gateway_integration 测试卡死问题（给 Claude Code）

## 问题

`tests/test_tool_trace_gateway_integration.py` 在全量 `pytest` 时会无限挂起，导致整个测试套件卡在 97%。

原因：该测试通过 `_import_gateway_app()` 动态导入 `aegi-mcp-gateway` 的 FastAPI app，导入过程中可能触发外部服务连接（ArchiveBox 等），在服务不可用时无限等待。

## 在开始编码前，先阅读

- `tests/test_tool_trace_gateway_integration.py` — 问题测试
- `tests/conftest.py` — 现有的 `requires_postgres`、`_port_open()` 等 skip 机制
- `aegi-mcp-gateway/src/aegi_mcp_gateway/api/main.py` — gateway app 入口，看导入时是否有阻塞初始化

## 修复方案

### 方案 A：加 `requires_gateway` skip 标记（推荐）

在 `conftest.py` 中新增 gateway 可用性检测：

```python
# conftest.py 新增
_gateway_importable = False
try:
    import importlib
    import sys
    from pathlib import Path
    _gw_src = Path(__file__).resolve().parents[1] / "aegi-mcp-gateway" / "src"
    if _gw_src.exists():
        sys.path.insert(0, str(_gw_src))
        # 只检测能否导入，不实际启动
        _gateway_importable = True
except Exception:
    _gateway_importable = False

requires_gateway = pytest.mark.skipif(
    not _gateway_importable or not _port_open("127.0.0.1", 8703, timeout=1.0),
    reason="MCP Gateway 或其依赖服务不可用",
)
```

然后在 `test_tool_trace_gateway_integration.py` 中：

```python
from conftest import requires_postgres, requires_gateway

pytestmark = [requires_postgres, requires_gateway]
```

### 方案 B：给 gateway 导入加超时保护

如果不想 skip，至少给 `_import_gateway_app()` 加超时：

```python
import signal

def _import_gateway_app(timeout: int = 5) -> object:
    def _handler(signum, frame):
        raise TimeoutError("Gateway app import timed out")
    
    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(timeout)
    try:
        # ... 原有导入逻辑 ...
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
```

### 推荐：两个都做

1. 加 `requires_gateway` skip 标记（服务不在就跳过）
2. 给 `_import_gateway_app()` 加超时保护（防止意外卡死）

## 验收标准

1. MCP Gateway 服务未启动时，该测试被 skip 而不是 hang
2. 全量 `pytest` 能正常跑完，不卡住
3. 现有测试不受影响
4. 当 gateway 服务可用时，该测试仍然能正常执行并通过
