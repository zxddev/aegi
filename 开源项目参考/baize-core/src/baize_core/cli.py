"""命令行入口。"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated

import httpx
import typer

from baize_core.schemas.entity_event import Entity, Event
from baize_core.schemas.policy import SensitivityLevel
from baize_core.schemas.storm import ReportConfig
from baize_core.schemas.task import TaskSpec

app = typer.Typer(help="baize-core CLI")


def _base_url(value: str | None) -> str:
    """解析服务地址。"""

    env_value = os.getenv("BAIZE_CORE_BASE_URL", "http://localhost:8000")
    return value or env_value


def _read_json(path: Path) -> object:
    """读取 JSON 文件。"""

    raw = path.read_text(encoding="utf-8")
    return json.loads(raw)


@app.command("toolchain-ingest")
def toolchain_ingest(
    task_id: Annotated[str, typer.Option(..., help="任务 ID")],
    query: Annotated[str, typer.Option(..., help="搜索关键词")],
    max_results: Annotated[int, typer.Option(help="最大结果数")] = 10,
    language: Annotated[str, typer.Option(help="语言")] = "auto",
    time_range: Annotated[str, typer.Option(help="时间范围")] = "all",
    max_depth: Annotated[int, typer.Option(help="抓取深度")] = 1,
    max_pages: Annotated[int, typer.Option(help="最大页面数")] = 10,
    obey_robots_txt: Annotated[bool, typer.Option(help="遵守 robots.txt")] = True,
    timeout_ms: Annotated[int, typer.Option(help="请求超时")] = 30000,
    chunk_size: Annotated[int, typer.Option(help="切分大小")] = 800,
    chunk_overlap: Annotated[int, typer.Option(help="切分重叠")] = 120,
    base_url: Annotated[str | None, typer.Option(help="API 地址")] = None,
) -> None:
    """运行 MCP 工具链并写入证据链。"""

    url = f"{_base_url(base_url).rstrip('/')}/toolchain/ingest"
    payload = {
        "task_id": task_id,
        "query": query,
        "max_results": max_results,
        "language": language,
        "time_range": time_range,
        "max_depth": max_depth,
        "max_pages": max_pages,
        "obey_robots_txt": obey_robots_txt,
        "timeout_ms": timeout_ms,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
    }
    response = httpx.post(url, json=payload, timeout=60.0)
    response.raise_for_status()
    typer.echo(response.json())


@app.command("entities-add")
def entities_add(
    file_path: Annotated[Path, typer.Argument(..., exists=True, help="实体 JSON 文件")],
    base_url: Annotated[str | None, typer.Option(help="API 地址")] = None,
) -> None:
    """批量写入实体。"""

    raw = _read_json(file_path)
    if not isinstance(raw, list):
        raise typer.BadParameter("实体文件必须是列表")
    entities = [Entity.model_validate(item) for item in raw]
    url = f"{_base_url(base_url).rstrip('/')}/entities"
    payload = {"entities": [entity.model_dump() for entity in entities]}
    response = httpx.post(url, json=payload, timeout=60.0)
    response.raise_for_status()
    typer.echo(response.json())


@app.command("events-add")
def events_add(
    file_path: Annotated[Path, typer.Argument(..., exists=True, help="事件 JSON 文件")],
    base_url: Annotated[str | None, typer.Option(help="API 地址")] = None,
) -> None:
    """批量写入事件。"""

    raw = _read_json(file_path)
    if not isinstance(raw, list):
        raise typer.BadParameter("事件文件必须是列表")
    events = [Event.model_validate(item) for item in raw]
    url = f"{_base_url(base_url).rstrip('/')}/events"
    payload = {"events": [event.model_dump() for event in events]}
    response = httpx.post(url, json=payload, timeout=60.0)
    response.raise_for_status()
    typer.echo(response.json())


@app.command("storm-run")
def storm_run(
    task_id: Annotated[str, typer.Option(..., help="任务 ID")],
    objective: Annotated[str, typer.Option(..., help="研究目标")],
    report_title: Annotated[str | None, typer.Option(help="报告标题")] = None,
    module_id: Annotated[list[str] | None, typer.Option(help="模块 ID（可重复）")] = None,
    custom: Annotated[list[str] | None, typer.Option(help="自由输入（可重复）")] = None,
    constraints: Annotated[list[str] | None, typer.Option(help="约束")] = None,
    time_window: Annotated[str | None, typer.Option(help="时间窗口")] = None,
    region: Annotated[str | None, typer.Option(help="区域")] = None,
    sensitivity: Annotated[
        SensitivityLevel, typer.Option(help="敏感级别")
    ] = SensitivityLevel.INTERNAL,
    base_url: Annotated[str | None, typer.Option(help="API 地址")] = None,
) -> None:
    """运行 STORM 研究。"""

    constraints = constraints or []
    module_id = module_id or []
    custom = custom or []
    task = TaskSpec(
        task_id=task_id,
        objective=objective,
        constraints=constraints,
        time_window=time_window,
        region=region,
        sensitivity=sensitivity,
    )
    url = f"{_base_url(base_url).rstrip('/')}/storm/run"
    report_config = ReportConfig(
        title=report_title,
        selected_modules=[
            {"module_id": mid, "title": mid} for mid in module_id if mid.strip()
        ],
        custom_sections=[{"content": text} for text in custom if text.strip()],
    )
    payload = {
        "task": task.model_dump(),
        "report_config": report_config.model_dump(),
    }
    response = httpx.post(url, json=payload, timeout=60.0)
    response.raise_for_status()
    typer.echo(response.json())


@app.command("evaluate")
def evaluate(
    suite: Annotated[str | None, typer.Option(help="套件名称 (strategic/operational)")] = None,
    parallel: Annotated[int, typer.Option(help="并行执行数")] = 1,
    output: Annotated[Path, typer.Option(help="输出目录")] = Path("./eval_report"),
    resume: Annotated[Path | None, typer.Option(help="从检查点恢复")] = None,
    dry_run: Annotated[bool, typer.Option(help="仅验证用例，不实际执行")] = False,
    list_suites: Annotated[
        bool, typer.Option("--list", is_flag=True, help="列出可用套件")
    ] = False,
) -> None:
    """运行评测套件。

    示例：
        baize-core evaluate --suite strategic --parallel 2
        baize-core evaluate --list
    """
    from baize_core.evaluation.report import generate_evaluation_report
    from baize_core.evaluation.runner import (
        EvaluationRunner,
        get_available_suites,
        get_suite_info,
    )

    # 列出可用套件
    if list_suites:
        suites = get_available_suites()
        if not suites:
            typer.echo("没有可用的评测套件")
            return
        typer.echo("可用的评测套件：")
        for s in suites:
            info = get_suite_info(s)
            typer.echo(f"  - {s}: {info['case_count']} 个用例")
        return

    # 检查必须提供 suite
    if suite is None:
        typer.echo("错误: 必须提供 --suite 参数，或使用 --list 查看可用套件")
        raise typer.Exit(1)

    # 验证套件名称
    available = get_available_suites()
    if suite not in available:
        typer.echo(f"错误: 套件 '{suite}' 不存在")
        typer.echo(f"可用套件: {', '.join(available)}")
        raise typer.Exit(1)

    # 进度回调
    def progress_callback(case_id: str, completed: int, total: int) -> None:
        typer.echo(f"[{completed}/{total}] 完成: {case_id}")

    # 初始化执行器
    runner = EvaluationRunner(
        context=None,  # 无上下文时使用 dry-run 模式
        checkpoint_dir=output / "checkpoints",
        progress_callback=progress_callback,
    )

    # 执行评测
    typer.echo(f"开始评测套件: {suite}")
    typer.echo(f"并行数: {parallel}")
    typer.echo(f"输出目录: {output}")
    if dry_run:
        typer.echo("模式: dry-run (仅验证用例)")
    typer.echo("-" * 40)

    result = asyncio.run(runner.run_suite(suite, parallel=parallel, dry_run=dry_run))

    # 输出结果摘要
    typer.echo("-" * 40)
    typer.echo(f"完成: {result.completed_cases}/{result.total_cases}")
    typer.echo(f"失败: {result.failed_cases}")
    typer.echo(f"通过率: {result.pass_rate:.1%}")
    typer.echo(f"平均耗时: {result.avg_elapsed_seconds:.1f}s")

    # 生成报告
    typer.echo("-" * 40)
    typer.echo("生成报告...")
    report_paths = generate_evaluation_report(result, output)
    for fmt, path in report_paths.items():
        typer.echo(f"  {fmt}: {path}")

    typer.echo("评测完成!")


@app.command("evaluate-info")
def evaluate_info(
    suite: str = typer.Argument(..., help="套件名称"),
) -> None:
    """查看评测套件详情。"""
    from baize_core.evaluation.runner import get_available_suites, get_suite_info

    available = get_available_suites()
    if suite not in available:
        typer.echo(f"错误: 套件 '{suite}' 不存在")
        typer.echo(f"可用套件: {', '.join(available)}")
        raise typer.Exit(1)

    info = get_suite_info(suite)
    typer.echo(f"套件: {info['name']}")
    typer.echo(f"用例数: {info['case_count']}")
    typer.echo("-" * 40)
    typer.echo("用例列表:")
    for case in info["cases"]:
        tags = ", ".join(case["tags"]) if case["tags"] else "无"
        typer.echo(f"  - {case['case_id']}: {case['name']}")
        typer.echo(f"    难度: {case['difficulty']}, 标签: {tags}")
