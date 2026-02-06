"""API 路由模块。"""

from __future__ import annotations

from baize_core.api.routes.artifacts import get_router as artifacts_router
from baize_core.api.routes.audit import get_router as audit_router
from baize_core.api.routes.entities import get_router as entities_router
from baize_core.api.routes.events import get_router as events_router
from baize_core.api.routes.modules import get_router as modules_router
from baize_core.api.routes.reports import get_router as reports_router
from baize_core.api.routes.reviews import get_router as reviews_router
from baize_core.api.routes.storm import get_router as storm_router
from baize_core.api.routes.system import get_router as system_router
from baize_core.api.routes.tasks import get_router as tasks_router
from baize_core.api.routes.toolchain import get_router as toolchain_router

__all__ = [
    "audit_router",
    "artifacts_router",
    "entities_router",
    "events_router",
    "modules_router",
    "reports_router",
    "reviews_router",
    "storm_router",
    "system_router",
    "tasks_router",
    "toolchain_router",
]
