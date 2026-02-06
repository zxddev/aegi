"""模块注册表。

从数据库读取/写入预设模块，并将模块配置解析为 STORM 章节结构。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from baize_core.schemas.storm import (
    CoverageItem,
    DepthPolicy,
    ReportConfig,
    ReportModuleSpec,
    SectionType,
    StormSectionSpec,
)
from baize_core.storage import models


def _is_default_depth_policy(policy: DepthPolicy) -> bool:
    """判断用户是否显式覆盖 depth_policy。

    约定：若 policy 等于默认 DepthPolicy()，视为未覆盖。
    """

    return policy == DepthPolicy()


def _safe_section_type(value: object) -> SectionType:
    if isinstance(value, str):
        try:
            return SectionType(value)
        except Exception:
            return SectionType.DEFAULT
    return SectionType.DEFAULT


@dataclass
class ModuleRegistry:
    """模块注册表 - 从数据库加载预设模块。"""

    session_factory: async_sessionmaker[AsyncSession]

    def _to_spec(self, row: models.ReportModuleModel) -> ReportModuleSpec:
        template = row.section_template or {}
        depth_raw = template.get("depth_policy")
        prompt_profile = template.get("prompt_profile")
        question = template.get("question")
        section_type_raw = template.get("section_type")

        depth_policy = DepthPolicy()
        if isinstance(depth_raw, dict):
            depth_policy = DepthPolicy.model_validate(depth_raw)

        return ReportModuleSpec(
            module_id=row.module_id,
            parent_id=row.parent_id,
            title=row.title,
            description=row.description,
            icon=row.icon,
            sort_order=row.sort_order,
            is_active=row.is_active,
            question=question if isinstance(question, str) else None,
            depth_policy=depth_policy,
            prompt_profile=prompt_profile if isinstance(prompt_profile, str) else "default",
            section_type=_safe_section_type(section_type_raw),
            coverage_questions=list(row.coverage_questions or []),
        )

    async def list_modules(
        self, parent_id: str | None = None, *, include_inactive: bool = False
    ) -> list[ReportModuleSpec]:
        """获取模块列表（支持层级）。"""

        async with self.session_factory() as session:
            stmt = select(models.ReportModuleModel)
            if parent_id is None:
                stmt = stmt.where(models.ReportModuleModel.parent_id.is_(None))
            else:
                stmt = stmt.where(models.ReportModuleModel.parent_id == parent_id)
            if not include_inactive:
                stmt = stmt.where(models.ReportModuleModel.is_active.is_(True))
            stmt = stmt.order_by(
                models.ReportModuleModel.sort_order.asc(),
                models.ReportModuleModel.module_id.asc(),
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_spec(row) for row in rows]

    async def get_module(
        self, module_id: str, *, include_inactive: bool = False
    ) -> ReportModuleSpec | None:
        """获取单个模块。"""

        async with self.session_factory() as session:
            stmt = select(models.ReportModuleModel).where(
                models.ReportModuleModel.module_id == module_id
            )
            if not include_inactive:
                stmt = stmt.where(models.ReportModuleModel.is_active.is_(True))
            row = (await session.execute(stmt)).scalars().first()
            if row is None:
                return None
            return self._to_spec(row)

    async def upsert_module(self, module: ReportModuleSpec) -> None:
        """创建或更新模块（最小能力，供管理 API 使用）。"""

        now = datetime.now(UTC)
        async with self.session_factory() as session:
            existing = (
                await session.execute(
                    select(models.ReportModuleModel).where(
                        models.ReportModuleModel.module_id == module.module_id
                    )
                )
            ).scalars().first()
            template = {
                "question": module.question,
                "depth_policy": module.depth_policy.model_dump(),
                "prompt_profile": module.prompt_profile,
                "section_type": module.section_type.value,
            }
            if existing is None:
                session.add(
                    models.ReportModuleModel(
                        module_id=module.module_id,
                        parent_id=module.parent_id,
                        title=module.title,
                        description=module.description,
                        icon=module.icon,
                        sort_order=module.sort_order,
                        is_active=module.is_active,
                        section_template=template,
                        coverage_questions=list(module.coverage_questions),
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                existing.parent_id = module.parent_id
                existing.title = module.title
                existing.description = module.description
                existing.icon = module.icon
                existing.sort_order = module.sort_order
                existing.is_active = module.is_active
                existing.section_template = template
                existing.coverage_questions = list(module.coverage_questions)
                existing.updated_at = now
            await session.commit()

    async def resolve_config(
        self, report_config: ReportConfig
    ) -> tuple[list[StormSectionSpec], list[CoverageItem]]:
        """将 ReportConfig 解析为章节列表与覆盖清单（仅处理 selected_modules）。"""

        sections: list[StormSectionSpec] = []
        coverage_items: list[CoverageItem] = []

        for selected in report_config.selected_modules:
            module_def = await self.get_module(selected.module_id, include_inactive=True)
            if module_def is None:
                raise ValueError(f"模块不存在: {selected.module_id}")

            # 允许用户覆盖 question/prompt_profile/depth_policy
            question = selected.question or module_def.question or selected.title
            prompt_profile = selected.prompt_profile or module_def.prompt_profile

            depth_policy = module_def.depth_policy
            if not _is_default_depth_policy(selected.depth_policy):
                depth_policy = selected.depth_policy

            sections.append(
                StormSectionSpec(
                    title=selected.title or module_def.title,
                    question=question,
                    section_type=module_def.section_type,
                    module_id=selected.module_id,
                    prompt_profile=prompt_profile,
                    coverage_item_ids=[],
                    depth_policy=depth_policy,
                )
            )

            for q in module_def.coverage_questions:
                if isinstance(q, str) and q.strip():
                    coverage_items.append(CoverageItem(question=q.strip()))

        return sections, coverage_items

