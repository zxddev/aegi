# Task Completion Checklist

1. Run `ruff check` and fix any lint errors
2. Run `ruff format` to ensure consistent formatting
3. Run quick import test to verify no circular imports
4. If DB models changed, create alembic migration
5. If pyproject.toml changed, run `uv sync`
