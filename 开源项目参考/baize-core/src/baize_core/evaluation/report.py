"""评测报告生成。

支持 HTML 和 Markdown 两种格式的评测报告。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from baize_core.evaluation.datasets.schema import SuiteResult


class ReportGenerator:
    """评测报告生成器。"""

    def generate_html(self, result: SuiteResult) -> str:
        """生成 HTML 格式的评测报告。

        Args:
            result: 评测结果

        Returns:
            HTML 字符串
        """
        html_parts = [
            self._html_head(result.suite_name),
            self._html_summary(result),
            self._html_metrics_dashboard(result),
            self._html_case_table(result),
            self._html_footer(),
        ]
        return "\n".join(html_parts)

    def generate_markdown(self, result: SuiteResult) -> str:
        """生成 Markdown 格式的评测报告。

        Args:
            result: 评测结果

        Returns:
            Markdown 字符串
        """
        lines = [
            f"# 评测报告：{result.suite_name}",
            "",
            f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "---",
            "",
            "## 摘要",
            "",
            f"- **总用例数**: {result.total_cases}",
            f"- **完成用例数**: {result.completed_cases}",
            f"- **失败用例数**: {result.failed_cases}",
            f"- **通过率**: {result.pass_rate:.1%}",
            f"- **平均耗时**: {result.avg_elapsed_seconds:.1f} 秒",
            "",
        ]

        # 汇总指标
        if result.aggregated_metrics:
            lines.extend(
                [
                    "## 汇总指标",
                    "",
                    "| 指标 | 值 |",
                    "|------|-----|",
                ]
            )
            for key, value in result.aggregated_metrics.items():
                if isinstance(value, float):
                    lines.append(f"| {key} | {value:.3f} |")
                else:
                    lines.append(f"| {key} | {value} |")
            lines.append("")

        # 用例详情
        lines.extend(
            [
                "## 用例详情",
                "",
                "| 用例 ID | 状态 | 耗时(秒) | 错误信息 |",
                "|---------|------|----------|----------|",
            ]
        )
        for case_result in result.case_results:
            status = "✓ 通过" if case_result.success else "✗ 失败"
            error = case_result.error_message or "-"
            if len(error) > 50:
                error = error[:47] + "..."
            lines.append(
                f"| {case_result.case_id} | {status} | "
                f"{case_result.elapsed_seconds:.1f} | {error} |"
            )

        lines.extend(
            [
                "",
                "---",
                "",
                f"检查点路径：`{result.checkpoint_path or 'N/A'}`",
            ]
        )

        return "\n".join(lines)

    def save_html(self, result: SuiteResult, output_path: Path) -> None:
        """保存 HTML 报告到文件。

        Args:
            result: 评测结果
            output_path: 输出路径
        """
        html = self.generate_html(result)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")

    def save_markdown(self, result: SuiteResult, output_path: Path) -> None:
        """保存 Markdown 报告到文件。

        Args:
            result: 评测结果
            output_path: 输出路径
        """
        md = self.generate_markdown(result)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md, encoding="utf-8")

    def _html_head(self, suite_name: str) -> str:
        """生成 HTML 头部。"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>评测报告 - {suite_name}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f5f7fa;
            color: #333;
            line-height: 1.6;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        h1 {{
            color: #1a1a2e;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #4a69bd;
        }}
        h2 {{
            color: #4a69bd;
            margin: 30px 0 15px 0;
        }}
        .summary-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .card {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .card-title {{
            font-size: 0.9em;
            color: #666;
            margin-bottom: 5px;
        }}
        .card-value {{
            font-size: 2em;
            font-weight: bold;
            color: #1a1a2e;
        }}
        .card-value.success {{
            color: #27ae60;
        }}
        .card-value.warning {{
            color: #f39c12;
        }}
        .card-value.danger {{
            color: #e74c3c;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{
            background: #4a69bd;
            color: white;
            font-weight: 600;
        }}
        tr:hover {{
            background: #f8f9fa;
        }}
        .status-pass {{
            color: #27ae60;
            font-weight: bold;
        }}
        .status-fail {{
            color: #e74c3c;
            font-weight: bold;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .metrics-section {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metrics-section h3 {{
            color: #4a69bd;
            margin-bottom: 15px;
            font-size: 1.1em;
        }}
        .metric-row {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }}
        .metric-row:last-child {{
            border-bottom: none;
        }}
        .metric-name {{
            color: #666;
        }}
        .metric-value {{
            font-weight: bold;
            color: #1a1a2e;
        }}
        footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            color: #666;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>评测报告：{suite_name}</h1>
"""

    def _html_summary(self, result: SuiteResult) -> str:
        """生成摘要卡片。"""
        pass_rate_class = (
            "success"
            if result.pass_rate >= 0.8
            else "warning"
            if result.pass_rate >= 0.5
            else "danger"
        )
        return f"""
        <div class="summary-cards">
            <div class="card">
                <div class="card-title">总用例数</div>
                <div class="card-value">{result.total_cases}</div>
            </div>
            <div class="card">
                <div class="card-title">完成用例</div>
                <div class="card-value">{result.completed_cases}</div>
            </div>
            <div class="card">
                <div class="card-title">失败用例</div>
                <div class="card-value {"danger" if result.failed_cases > 0 else ""}">{result.failed_cases}</div>
            </div>
            <div class="card">
                <div class="card-title">通过率</div>
                <div class="card-value {pass_rate_class}">{result.pass_rate:.1%}</div>
            </div>
            <div class="card">
                <div class="card-title">平均耗时</div>
                <div class="card-value">{result.avg_elapsed_seconds:.1f}s</div>
            </div>
        </div>
"""

    def _html_metrics_dashboard(self, result: SuiteResult) -> str:
        """生成指标仪表盘。"""
        if not result.aggregated_metrics:
            return ""

        # 分组指标
        extraction_metrics = {}
        evidence_metrics = {}
        operation_metrics = {}

        for key, value in result.aggregated_metrics.items():
            if (
                key.startswith("entity_")
                or key.startswith("event_")
                or "geolocation" in key
            ):
                extraction_metrics[key] = value
            elif key in (
                "citation_hit_rate",
                "coverage_score",
                "source_diversity",
                "fact_consistency",
                "timeline_consistency",
                "conflict_table_coverage",
            ):
                evidence_metrics[key] = value
            else:
                operation_metrics[key] = value

        html = '<h2>汇总指标</h2><div class="metrics-grid">'

        if extraction_metrics:
            html += self._html_metrics_section("抽取质量", extraction_metrics)
        if evidence_metrics:
            html += self._html_metrics_section("证据与一致性", evidence_metrics)
        if operation_metrics:
            html += self._html_metrics_section("运维与成本", operation_metrics)

        html += "</div>"
        return html

    def _html_metrics_section(self, title: str, metrics: dict[str, Any]) -> str:
        """生成指标区域。"""
        html = f'<div class="metrics-section"><h3>{title}</h3>'
        for key, value in metrics.items():
            formatted = f"{value:.3f}" if isinstance(value, float) else str(value)
            html += f"""
            <div class="metric-row">
                <span class="metric-name">{key}</span>
                <span class="metric-value">{formatted}</span>
            </div>
            """
        html += "</div>"
        return html

    def _html_case_table(self, result: SuiteResult) -> str:
        """生成用例表格。"""
        rows = []
        for case_result in result.case_results:
            status_class = "status-pass" if case_result.success else "status-fail"
            status_text = "✓ 通过" if case_result.success else "✗ 失败"
            error = case_result.error_message or "-"
            if len(error) > 80:
                error = error[:77] + "..."
            rows.append(f"""
                <tr>
                    <td>{case_result.case_id}</td>
                    <td class="{status_class}">{status_text}</td>
                    <td>{case_result.elapsed_seconds:.1f}s</td>
                    <td>{case_result.evidence_count}</td>
                    <td>{case_result.source_count}</td>
                    <td>{error}</td>
                </tr>
            """)

        return f"""
        <h2>用例详情</h2>
        <table>
            <thead>
                <tr>
                    <th>用例 ID</th>
                    <th>状态</th>
                    <th>耗时</th>
                    <th>证据数</th>
                    <th>来源数</th>
                    <th>错误信息</th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows)}
            </tbody>
        </table>
"""

    def _html_footer(self) -> str:
        """生成页脚。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"""
        <footer>
            <p>报告生成时间：{now}</p>
            <p>Baize Core Evaluation Suite</p>
        </footer>
    </div>
</body>
</html>
"""


def generate_evaluation_report(
    result: SuiteResult,
    output_dir: Path,
    formats: list[str] | None = None,
) -> dict[str, Path]:
    """生成评测报告到指定目录。

    Args:
        result: 评测结果
        output_dir: 输出目录
        formats: 输出格式列表，默认 ["html", "md"]

    Returns:
        格式到路径的映射
    """
    if formats is None:
        formats = ["html", "md"]

    output_dir.mkdir(parents=True, exist_ok=True)
    generator = ReportGenerator()
    paths: dict[str, Path] = {}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{result.suite_name}_{timestamp}"

    if "html" in formats:
        html_path = output_dir / f"{base_name}.html"
        generator.save_html(result, html_path)
        paths["html"] = html_path

    if "md" in formats:
        md_path = output_dir / f"{base_name}.md"
        generator.save_markdown(result, md_path)
        paths["md"] = md_path

    return paths
