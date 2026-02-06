# Author: msq
from __future__ import annotations

from aegi_core.contracts.errors import ProblemDetail


class AegiHTTPError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str, details: dict) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details

    def to_problem_detail(self) -> ProblemDetail:
        """转换为 RFC 9457 ProblemDetail。"""
        return ProblemDetail(
            type=f"urn:aegi:error:{self.error_code}",
            title=self.message,
            status=self.status_code,
            detail=self.message,
            error_code=self.error_code,
            extensions=self.details,
        )


def not_found(resource: str, uid: str) -> AegiHTTPError:
    return AegiHTTPError(
        404, "not_found", f"{resource} not found", {"uid": uid, "resource": resource}
    )
