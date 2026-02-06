from __future__ import annotations


class AegiHTTPError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str, details: dict) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details


def not_found(resource: str, uid: str) -> AegiHTTPError:
    return AegiHTTPError(
        404, "not_found", f"{resource} not found", {"uid": uid, "resource": resource}
    )
