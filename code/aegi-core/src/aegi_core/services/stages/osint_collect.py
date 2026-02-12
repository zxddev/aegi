"""OSINT 采集流水线阶段。"""

from __future__ import annotations

from aegi_core.services.pipeline_orchestrator import StageResult
from aegi_core.services.stages.base import AnalysisStage, StageContext


class OSINTCollectStage(AnalysisStage):
    name = "osint_collect"

    def should_skip(self, ctx: StageContext) -> str | None:
        if not ctx.config.get("osint_query"):
            return "no osint_query in config"
        return None

    async def run(self, ctx: StageContext) -> StageResult:
        from time import monotonic_ns
        from aegi_core.services.osint_collector import OSINTCollector

        t = monotonic_ns()
        query = ctx.config["osint_query"]
        categories = ctx.config.get("categories", "general")
        max_results = ctx.config.get("max_results", 10)
        language = ctx.config.get("language", "zh-CN")
        extract_claims = ctx.config.get("extract_claims", True)

        # OSINTCollector 需要 searxng + llm + qdrant + db_session
        # 通过 ctx 字段注入
        searxng = ctx.config.get("searxng")
        db_session = ctx.config.get("db_session")
        qdrant = ctx.config.get("qdrant")

        if not searxng:
            return StageResult(
                stage=self.name,
                status="error",
                duration_ms=(monotonic_ns() - t) // 1_000_000,
                output=None,
                error="no searxng client in config",
            )

        collector = OSINTCollector(
            searxng=searxng,
            llm=ctx.llm,
            qdrant=qdrant,
            db_session=db_session,
        )
        try:
            result = await collector.collect(
                query,
                ctx.case_uid,
                categories=categories,
                language=language,
                max_results=max_results,
                extract_claims=extract_claims,
            )
        finally:
            await collector.close()

        # 将新 source claims 合并到上下文，供下游阶段使用
        if result.source_claim_uids:
            ctx.config["osint_claim_uids"] = result.source_claim_uids
            # 加载 SourceClaimV1 对象，让 assertion_fuse 等阶段可以使用
            if db_session:
                loaded = await self._load_claims(db_session, result.source_claim_uids)
                ctx.source_claims.extend(loaded)

        duration = (monotonic_ns() - t) // 1_000_000

        # ── emit osint.collected event ──
        from aegi_core.services.event_bus import get_event_bus, AegiEvent

        bus = get_event_bus()
        await bus.emit(
            AegiEvent(
                event_type="osint.collected",
                case_uid=ctx.case_uid,
                payload={
                    "summary": f"OSINT collected: {result.urls_ingested} URLs, "
                    f"{result.claims_extracted} claims for query '{query}'",
                    "query": query,
                    "urls_found": result.urls_found,
                    "urls_ingested": result.urls_ingested,
                    "claims_extracted": result.claims_extracted,
                },
                severity="low",
                source_event_uid=f"osint:{ctx.case_uid}:{query[:64]}:{result.urls_ingested}",
            )
        )

        return StageResult(
            stage=self.name,
            status="success",
            duration_ms=duration,
            output={
                "urls_found": result.urls_found,
                "urls_ingested": result.urls_ingested,
                "urls_deduped": result.urls_deduped,
                "claims_extracted": result.claims_extracted,
                "claims_loaded": len(ctx.source_claims),
                "errors": result.errors,
            },
        )

    @staticmethod
    async def _load_claims(db_session, uids: list[str]) -> list:
        """按 UID 加载 SourceClaim 行并转为 SourceClaimV1。"""
        import sqlalchemy as sa
        from aegi_core.db.models.source_claim import SourceClaim
        from aegi_core.contracts.schemas import SourceClaimV1

        rows = (
            (
                await db_session.execute(
                    sa.select(SourceClaim).where(SourceClaim.uid.in_(uids))
                )
            )
            .scalars()
            .all()
        )

        return [
            SourceClaimV1(
                uid=r.uid,
                case_uid=r.case_uid,
                artifact_version_uid=r.artifact_version_uid,
                chunk_uid=r.chunk_uid,
                evidence_uid=r.evidence_uid,
                quote=r.quote,
                selectors=r.selectors or [],
                attributed_to=r.attributed_to,
                modality=r.modality,
                language=r.language,
                original_quote=r.original_quote,
                translation=r.translation,
                translation_meta=r.translation_meta,
                created_at=r.created_at,
            )
            for r in rows
        ]
