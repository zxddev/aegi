"""运行时审查子 agent。"""

from __future__ import annotations

from baize_core.evidence.validator import EvidenceValidator
from baize_core.schemas.evidence import Artifact, Chunk, Claim, Evidence, Report
from baize_core.schemas.review import ReviewResult


class ReviewAgent:
    """审查子 agent（Critic/Judge）。"""

    def __init__(self) -> None:
        self._validator = EvidenceValidator()

    def review(
        self,
        *,
        claims: list[Claim],
        evidence: list[Evidence],
        chunks: list[Chunk],
        artifacts: list[Artifact],
        report: Report | None = None,
    ) -> ReviewResult:
        """执行证据链审查。"""

        result = self._validator.validate(
            claims=claims,
            evidence=evidence,
            chunks=chunks,
            artifacts=artifacts,
            report=report,
        )
        if not result.is_valid:
            missing = [error.message for error in result.errors]
            return ReviewResult(
                ok=False,
                insufficient_evidence=True,
                missing_evidence=missing,
                violations=[],
            )
        # 对 WARNING 不阻断（但仍返回给上层用于展示/追踪）
        if result.warning_count:
            warnings = [error.message for error in result.errors]
            return ReviewResult(
                ok=True,
                insufficient_evidence=False,
                missing_evidence=[],
                violations=warnings,
            )
        return ReviewResult(ok=True)
