"""新增报告模块表。

为动态报告结构提供可配置的预设模块（数据库驱动）。
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_report_modules"
down_revision = "0012_add_query_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_modules",
        sa.Column("module_id", sa.Text(), primary_key=True),
        sa.Column(
            "parent_id",
            sa.Text(),
            sa.ForeignKey("baize_core.report_modules.module_id"),
            nullable=True,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("icon", sa.Text()),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "section_template",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "coverage_questions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        schema="baize_core",
    )
    op.create_index(
        "report_modules_parent_id_idx",
        "report_modules",
        ["parent_id"],
        schema="baize_core",
    )
    op.create_index(
        "report_modules_is_active_idx",
        "report_modules",
        ["is_active"],
        schema="baize_core",
    )

    # 预置一组“快捷模块”（可随时通过 API 增删改）
    now = datetime.now(UTC)
    table = sa.Table(
        "report_modules",
        sa.MetaData(schema="baize_core"),
        sa.Column("module_id", sa.Text()),
        sa.Column("parent_id", sa.Text()),
        sa.Column("title", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("icon", sa.Text()),
        sa.Column("sort_order", sa.Integer()),
        sa.Column("is_active", sa.Boolean()),
        sa.Column("section_template", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("coverage_questions", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True)),
    )
    op.bulk_insert(
        table,
        [
            {
                "module_id": "junqing",
                "parent_id": None,
                "title": "军情解码（综合）",
                "description": "从多维度解码军情态势",
                "icon": "radar",
                "sort_order": 0,
                "is_active": True,
                "section_template": {
                    "question": "从武装力量、编成部署、军事设施、指挥控制、训练演习、作战支援、后勤保障等维度，综合解码当前军情态势与关键变化。",
                    "depth_policy": {"min_sources": 4, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "default",
                },
                "coverage_questions": [
                    "有哪些关键参与方/部队？",
                    "近期关键事件与时间线是什么？",
                    "能力与意图变化的证据是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "junqing_wuzhuang",
                "parent_id": "junqing",
                "title": "武装力量",
                "description": "兵力结构与能力要素",
                "icon": None,
                "sort_order": 10,
                "is_active": True,
                "section_template": {
                    "question": "关键参与方的部队编成、装备能力、训练水平与作战样式有哪些可验证变化？",
                    "depth_policy": {"min_sources": 4, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "key_actors",
                },
                "coverage_questions": [
                    "主要部队与编成要素有哪些？",
                    "关键装备/平台与作战能力证据是什么？",
                    "训练/演训是否反映新的战术样式？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "junqing_bushu",
                "parent_id": "junqing",
                "title": "编成部署",
                "description": "力量部署与编组变化",
                "icon": None,
                "sort_order": 20,
                "is_active": True,
                "section_template": {
                    "question": "近期力量部署、编组与前沿存在发生了哪些变化？这些变化对威慑与升级管理意味着什么？",
                    "depth_policy": {"min_sources": 4, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "force_posture",
                },
                "coverage_questions": [
                    "部署地点/频次/规模的证据是什么？",
                    "部署变化与时间线如何对应关键事件？",
                    "部署对危机升级梯度的影响是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "bingqi",
                "parent_id": None,
                "title": "兵棋推演（综合）",
                "description": "将证据约束下的态势转为可推演分支",
                "icon": "chess",
                "sort_order": 100,
                "is_active": True,
                "section_template": {
                    "question": "基于证据抽取关键假设与约束，构建 2-3 条行动分支，并给出触发条件与风险点。",
                    "depth_policy": {"min_sources": 3, "max_iterations": 1, "max_results": 8},
                    "prompt_profile": "wargame",
                    "section_type": "assessment",
                },
                "coverage_questions": [
                    "核心假设与约束是什么？",
                    "行动分支与触发条件是什么？",
                    "关键风险点与不确定性是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "wubei",
                "parent_id": None,
                "title": "武备透视（综合）",
                "description": "装备体系与技术要素透视",
                "icon": "tank",
                "sort_order": 200,
                "is_active": True,
                "section_template": {
                    "question": "围绕任务目标，梳理相关装备体系、关键平台/弹药/传感器/指挥通信要素及其演进趋势，并指出证据缺口。",
                    "depth_policy": {"min_sources": 4, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "background",
                },
                "coverage_questions": [
                    "涉及哪些装备体系与关键平台？",
                    "技术演进与部署证据是什么？",
                    "信息缺口与验证路径是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "report_modules_is_active_idx",
        table_name="report_modules",
        schema="baize_core",
    )
    op.drop_index(
        "report_modules_parent_id_idx",
        table_name="report_modules",
        schema="baize_core",
    )
    op.drop_table("report_modules", schema="baize_core")

