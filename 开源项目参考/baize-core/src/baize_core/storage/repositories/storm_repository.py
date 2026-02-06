"""STORM 研究 Repository。

负责 STORM 大纲、章节、迭代的数据库操作。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from baize_core.schemas.storm import StormIteration, StormOutline, StormSectionSpec
from baize_core.storage import models


def _storm_section_record(
    outline_uid: str, section: StormSectionSpec
) -> models.StormSectionModel:
    """构建 STORM 章节记录。"""
    return models.StormSectionModel(
        section_uid=section.section_id,
        outline_uid=outline_uid,
        title=section.title,
        question=section.question,
        coverage_item_ids=section.coverage_item_ids,
        depth_policy=section.depth_policy.model_dump(),
        created_at=datetime.now(UTC),
    )


@dataclass
class StormRepository:
    """STORM 研究 Repository。

    Attributes:
        session_factory: SQLAlchemy 异步会话工厂
    """

    session_factory: async_sessionmaker[AsyncSession]

    async def store_outline(self, outline: StormOutline) -> None:
        """写入 STORM 大纲与章节。

        Args:
            outline: STORM 大纲
        """
        async with self.session_factory() as session:
            session.add(
                models.StormOutlineModel(
                    outline_uid=outline.outline_uid,
                    task_id=outline.task_id,
                    task_type=outline.task_type.value,
                    objective=outline.objective,
                    coverage_checklist=[
                        item.model_dump() for item in outline.coverage_checklist
                    ],
                    created_at=outline.created_at,
                )
            )
            for section in outline.sections:
                session.add(_storm_section_record(outline.outline_uid, section))
            await session.commit()

    async def store_sections(
        self, outline_uid: str, sections: list[StormSectionSpec]
    ) -> None:
        """补充写入章节。

        Args:
            outline_uid: 大纲 UID
            sections: 章节列表
        """
        if not sections:
            return
        async with self.session_factory() as session:
            for section in sections:
                session.add(_storm_section_record(outline_uid, section))
            await session.commit()

    async def store_iterations(self, iterations: list[StormIteration]) -> None:
        """写入章节研究迭代。

        Args:
            iterations: 迭代列表
        """
        if not iterations:
            return
        async with self.session_factory() as session:
            for iteration in iterations:
                session.add(
                    models.StormSectionIterationModel(
                        section_uid=iteration.section_id,
                        iteration_index=iteration.iteration_index,
                        query=iteration.query,
                        created_at=iteration.created_at,
                    )
                )
            await session.commit()

    async def store_section_evidence(
        self, *, section_uid: str, evidence_uids: list[str]
    ) -> None:
        """写入章节证据关联。

        Args:
            section_uid: 章节 UID
            evidence_uids: 证据 UID 列表
        """
        if not evidence_uids:
            return
        async with self.session_factory() as session:
            for evidence_uid in evidence_uids:
                session.add(
                    models.StormSectionEvidenceModel(
                        section_uid=section_uid,
                        evidence_uid=evidence_uid,
                    )
                )
            await session.commit()
