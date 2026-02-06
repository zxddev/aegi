"""补充更多预设报告模块数据（便于测试）。

在 0013_report_modules 已创建表并插入少量模块的基础上，继续补齐一批常见模块。
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_report_modules_more"
down_revision = "0013_report_modules"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
            # ========= 军情解码（补齐子模块） =========
            {
                "module_id": "junqing_sheshi",
                "parent_id": "junqing",
                "title": "军事设施",
                "description": "基地/港口/机场/阵地等设施变化",
                "icon": None,
                "sort_order": 30,
                "is_active": True,
                "section_template": {
                    "question": "相关军事设施（基地、机场、港口、阵地、雷达站等）有哪些可验证变化？这些变化对行动能力与预警/反介入意味着什么？",
                    "depth_policy": {"min_sources": 3, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "background",
                },
                "coverage_questions": [
                    "设施建设/扩建/启用的证据是什么？",
                    "这些设施支撑哪些作战/保障能力？",
                    "信息缺口与验证路径是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "junqing_zhihui",
                "parent_id": "junqing",
                "title": "军事指挥",
                "description": "指挥控制与体系协同迹象",
                "icon": None,
                "sort_order": 40,
                "is_active": True,
                "section_template": {
                    "question": "指挥控制（C2）、联合指挥、指挥通信保障有哪些可验证迹象？这些迹象如何影响升级管理与跨域联动？",
                    "depth_policy": {"min_sources": 3, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "assessment",
                },
                "coverage_questions": [
                    "是否出现新的指挥架构/口径/演训科目？",
                    "体系协同证据是什么？",
                    "有哪些矛盾证据/口径差？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "junqing_xunlian",
                "parent_id": "junqing",
                "title": "演习训练",
                "description": "演训活动与战术样式变化",
                "icon": None,
                "sort_order": 50,
                "is_active": True,
                "section_template": {
                    "question": "近期演习训练的频次、规模、科目与战术样式有哪些变化？这些变化与现实态势/行动假设的对应关系是什么？",
                    "depth_policy": {"min_sources": 3, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "timeline",
                },
                "coverage_questions": [
                    "演训的时间线与关键窗口是什么？",
                    "演训科目是否指向特定行动样式？",
                    "是否存在对外叙事与行动不一致的证据？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "junqing_zhichi",
                "parent_id": "junqing",
                "title": "作战支援",
                "description": "情报/侦察/通信/电子等支援要素",
                "icon": None,
                "sort_order": 60,
                "is_active": True,
                "section_template": {
                    "question": "作战支援要素（ISR、通信、电子战、网络等）有哪些可验证变化？对态势感知、压制与反制意味着什么？",
                    "depth_policy": {"min_sources": 3, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "assessment",
                },
                "coverage_questions": [
                    "支援要素部署/活动的证据是什么？",
                    "对关键链路（通信/导航/侦察）的影响是什么？",
                    "证据缺口与需要补齐的数据是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "junqing_houqin",
                "parent_id": "junqing",
                "title": "后勤保障",
                "description": "补给、运输、维修、动员等保障迹象",
                "icon": None,
                "sort_order": 70,
                "is_active": True,
                "section_template": {
                    "question": "后勤保障（补给、运输、维修、动员、医疗等）有哪些可验证迹象？这些迹象对持续行动能力与风险意味着什么？",
                    "depth_policy": {"min_sources": 3, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "default",
                },
                "coverage_questions": [
                    "保障活动/动员迹象的证据是什么？",
                    "保障瓶颈与脆弱点可能在哪里？",
                    "需要进一步验证的关键问题是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            # ========= 兵棋推演（补齐子模块） =========
            {
                "module_id": "bingqi_zhanlue",
                "parent_id": "bingqi",
                "title": "战略推演",
                "description": "战略层情景推演与触发条件",
                "icon": None,
                "sort_order": 10,
                "is_active": True,
                "section_template": {
                    "question": "在证据约束下构建战略层 2-3 个情景分支，明确触发条件、关键假设与升级风险。",
                    "depth_policy": {"min_sources": 3, "max_iterations": 1, "max_results": 8},
                    "prompt_profile": "wargame",
                    "section_type": "assessment",
                },
                "coverage_questions": [
                    "关键假设与约束是什么？",
                    "情景分支与触发条件是什么？",
                    "主要风险点与信息缺口是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "bingqi_lukong",
                "parent_id": "bingqi",
                "title": "陆空作战推演",
                "description": "陆空域行动分支与窗口",
                "icon": None,
                "sort_order": 20,
                "is_active": True,
                "section_template": {
                    "question": "构建陆空域行动的 2-3 条分支，给出关键窗口、约束条件、风险点与预警指标（基于证据）。",
                    "depth_policy": {"min_sources": 3, "max_iterations": 1, "max_results": 8},
                    "prompt_profile": "wargame",
                    "section_type": "timeline",
                },
                "coverage_questions": [
                    "关键窗口与约束是什么？",
                    "行动分支与触发条件是什么？",
                    "预警指标与证据来源是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "bingqi_haikong",
                "parent_id": "bingqi",
                "title": "海空作战推演",
                "description": "海空域行动分支与风险",
                "icon": None,
                "sort_order": 30,
                "is_active": True,
                "section_template": {
                    "question": "构建海空域行动的 2-3 条分支，明确关键节点、支援要素、风险点与触发条件（基于证据）。",
                    "depth_policy": {"min_sources": 3, "max_iterations": 1, "max_results": 8},
                    "prompt_profile": "wargame",
                    "section_type": "assessment",
                },
                "coverage_questions": [
                    "关键节点/航道/基地约束是什么？",
                    "支援要素与脆弱点是什么？",
                    "触发条件与升级风险是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "bingqi_taikong",
                "parent_id": "bingqi",
                "title": "太空作战推演",
                "description": "太空域对抗与关键链路",
                "icon": None,
                "sort_order": 40,
                "is_active": True,
                "section_template": {
                    "question": "基于证据梳理太空域关键链路（侦察/通信/导航），构建对抗分支与风险点，并列出验证缺口。",
                    "depth_policy": {"min_sources": 3, "max_iterations": 1, "max_results": 8},
                    "prompt_profile": "wargame",
                    "section_type": "assessment",
                },
                "coverage_questions": [
                    "关键链路与平台是什么？",
                    "对抗方式的证据是什么？",
                    "不确定性与缺口是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "bingqi_renzhi",
                "parent_id": "bingqi",
                "title": "认知作战推演",
                "description": "叙事与信息操作分支",
                "icon": None,
                "sort_order": 50,
                "is_active": True,
                "section_template": {
                    "question": "基于证据梳理认知作战/信息操作的手段与目标，构建可能分支与触发条件，并指出可观测指标。",
                    "depth_policy": {"min_sources": 3, "max_iterations": 1, "max_results": 8},
                    "prompt_profile": "wargame",
                    "section_type": "assessment",
                },
                "coverage_questions": [
                    "主要叙事与受众是什么？",
                    "信息操作手段与证据是什么？",
                    "可观测指标与反制点是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            # ========= 武备透视（补齐子模块） =========
            {
                "module_id": "wubei_country_search",
                "parent_id": "wubei",
                "title": "相关国家（搜索）",
                "description": "按国家维度快速聚合装备体系线索（可由用户覆盖问题）",
                "icon": None,
                "sort_order": 10,
                "is_active": True,
                "section_template": {
                    "question": "针对用户指定国家/地区，梳理其重点装备体系与近期更新动向，并指出证据缺口与验证路径。",
                    "depth_policy": {"min_sources": 3, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "background",
                },
                "coverage_questions": [
                    "涉及哪些装备体系与关键平台？",
                    "近期更新/列装证据是什么？",
                    "信息缺口与验证路径是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "wubei_land",
                "parent_id": "wubei",
                "title": "陆上装备",
                "description": "坦克装甲、火炮、防空、导弹等",
                "icon": None,
                "sort_order": 20,
                "is_active": True,
                "section_template": {
                    "question": "围绕任务目标，梳理陆上装备体系（装甲、火炮、防空、导弹等）及其演进趋势，并标注证据。",
                    "depth_policy": {"min_sources": 3, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "background",
                },
                "coverage_questions": [
                    "关键平台/型号有哪些？",
                    "部署/列装/演训证据是什么？",
                    "缺口与不确定性是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "wubei_sea",
                "parent_id": "wubei",
                "title": "海上装备",
                "description": "舰艇、潜艇、反舰与海上支援体系",
                "icon": None,
                "sort_order": 30,
                "is_active": True,
                "section_template": {
                    "question": "围绕任务目标，梳理海上装备（舰艇/潜艇/反舰体系）及其演进趋势，并指出关键证据。",
                    "depth_policy": {"min_sources": 3, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "background",
                },
                "coverage_questions": [
                    "关键舰艇/编队/能力要素是什么？",
                    "活动与部署证据是什么？",
                    "信息缺口与验证路径是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "wubei_air",
                "parent_id": "wubei",
                "title": "空中装备",
                "description": "战斗机、轰炸机、预警机、无人机等",
                "icon": None,
                "sort_order": 40,
                "is_active": True,
                "section_template": {
                    "question": "围绕任务目标，梳理空中装备（有人/无人、预警与加油）体系及其演进趋势，并给出证据链。",
                    "depth_policy": {"min_sources": 3, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "background",
                },
                "coverage_questions": [
                    "关键平台/型号与能力要素是什么？",
                    "列装/训练/部署证据是什么？",
                    "缺口与不确定性是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "wubei_space",
                "parent_id": "wubei",
                "title": "太空装备",
                "description": "侦察、通信、导航与反制能力",
                "icon": None,
                "sort_order": 50,
                "is_active": True,
                "section_template": {
                    "question": "围绕任务目标，梳理太空装备与关键链路（侦察/通信/导航/反制）及其演进趋势，标注证据与缺口。",
                    "depth_policy": {"min_sources": 3, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "background",
                },
                "coverage_questions": [
                    "关键链路与平台是什么？",
                    "演进/部署证据是什么？",
                    "缺口与验证路径是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "wubei_cyber",
                "parent_id": "wubei",
                "title": "网电装备",
                "description": "网络与电子对抗相关装备与体系",
                "icon": None,
                "sort_order": 60,
                "is_active": True,
                "section_template": {
                    "question": "围绕任务目标，梳理网电相关装备/体系（电子侦察、干扰、网络能力等）及其活动证据，并指出缺口。",
                    "depth_policy": {"min_sources": 3, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "assessment",
                },
                "coverage_questions": [
                    "关键能力要素与平台是什么？",
                    "活动/演训证据是什么？",
                    "缺口与不确定性是什么？",
                ],
                "created_at": now,
                "updated_at": now,
            },
            {
                "module_id": "wubei_cbrn",
                "parent_id": "wubei",
                "title": "核化生装备",
                "description": "核/化学/生物相关体系与防护",
                "icon": None,
                "sort_order": 70,
                "is_active": True,
                "section_template": {
                    "question": "围绕任务目标，梳理核化生相关能力要素与公开证据，并标注高不确定点与验证路径。",
                    "depth_policy": {"min_sources": 3, "max_iterations": 2, "max_results": 8},
                    "prompt_profile": "military_intel",
                    "section_type": "assessment",
                },
                "coverage_questions": [
                    "公开证据能支持哪些判断？",
                    "最关键的不确定性是什么？",
                    "需要补齐哪些一手信息？",
                ],
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    # 仅删除本迁移插入的 module_id
    op.execute(
        """
        DELETE FROM baize_core.report_modules
        WHERE module_id IN (
          'junqing_sheshi','junqing_zhihui','junqing_xunlian','junqing_zhichi','junqing_houqin',
          'bingqi_zhanlue','bingqi_lukong','bingqi_haikong','bingqi_taikong','bingqi_renzhi',
          'wubei_country_search','wubei_land','wubei_sea','wubei_air','wubei_space','wubei_cyber','wubei_cbrn'
        )
        """
    )

