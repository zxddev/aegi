# Suggested Commands

## Run the app
```bash
cd /home/user/workspace/gitcode/aegi/code/aegi-core
.venv/bin/uvicorn aegi_core.api.main:app --reload --host 0.0.0.0 --port 8000
```

## Tests
```bash
cd /home/user/workspace/gitcode/aegi/code/aegi-core
.venv/bin/pytest tests/
```

## Lint / Format
```bash
cd /home/user/workspace/gitcode/aegi/code/aegi-core
.venv/bin/ruff check src/
.venv/bin/ruff format src/
```

## DB Migrations
```bash
cd /home/user/workspace/gitcode/aegi/code/aegi-core
.venv/bin/alembic upgrade head
```

## Install deps
```bash
cd /home/user/workspace/gitcode/aegi/code/aegi-core
uv sync
```

## Quick import test
```bash
cd /home/user/workspace/gitcode/aegi/code/aegi-core
.venv/bin/python -c "from aegi_core.settings import settings; print(settings)"
```
