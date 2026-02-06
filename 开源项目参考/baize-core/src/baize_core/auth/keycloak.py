"""Keycloak IAM/SSO 集成模块。

提供以下功能：
- JWT 令牌验证
- 用户信息获取
- 角色权限检查
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated, Any

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KeycloakConfig:
    """Keycloak 配置。"""

    server_url: str  # Keycloak 服务器地址
    realm: str  # Realm 名称
    client_id: str  # 客户端 ID
    client_secret: str  # 客户端密钥
    verify_ssl: bool = True


@dataclass
class TokenInfo:
    """令牌信息。"""

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None = None
    id_token: str | None = None


@dataclass
class UserInfo:
    """用户信息。"""

    sub: str  # 用户 ID
    preferred_username: str
    email: str | None = None
    email_verified: bool = False
    name: str | None = None
    roles: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.roles is None:
            self.roles = []

    def has_role(self, role: str) -> bool:
        """检查是否有指定角色。"""
        return role in self.roles


class KeycloakClient:
    """Keycloak 客户端。"""

    def __init__(self, config: KeycloakConfig) -> None:
        """初始化 Keycloak 客户端。

        Args:
            config: Keycloak 配置
        """
        self._config = config
        self._base_url = f"{config.server_url}/realms/{config.realm}"

    async def get_token(
        self,
        username: str,
        password: str,
    ) -> TokenInfo:
        """获取访问令牌（密码授权）。

        Args:
            username: 用户名
            password: 密码

        Returns:
            令牌信息
        """
        url = f"{self._base_url}/protocol/openid-connect/token"
        data = {
            "grant_type": "password",
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
            "username": username,
            "password": password,
        }
        async with httpx.AsyncClient(verify=self._config.verify_ssl) as client:
            response = await client.post(url, data=data)
            response.raise_for_status()
            result = response.json()
            return TokenInfo(
                access_token=result["access_token"],
                token_type=result["token_type"],
                expires_in=result["expires_in"],
                refresh_token=result.get("refresh_token"),
                id_token=result.get("id_token"),
            )

    async def refresh_token(self, refresh_token: str) -> TokenInfo:
        """刷新访问令牌。

        Args:
            refresh_token: 刷新令牌

        Returns:
            新的令牌信息
        """
        url = f"{self._base_url}/protocol/openid-connect/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
            "refresh_token": refresh_token,
        }
        async with httpx.AsyncClient(verify=self._config.verify_ssl) as client:
            response = await client.post(url, data=data)
            response.raise_for_status()
            result = response.json()
            return TokenInfo(
                access_token=result["access_token"],
                token_type=result["token_type"],
                expires_in=result["expires_in"],
                refresh_token=result.get("refresh_token"),
                id_token=result.get("id_token"),
            )

    async def get_user_info(self, access_token: str) -> UserInfo:
        """获取用户信息。

        Args:
            access_token: 访问令牌

        Returns:
            用户信息
        """
        url = f"{self._base_url}/protocol/openid-connect/userinfo"
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(verify=self._config.verify_ssl) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            result = response.json()
            # 提取角色
            roles = self._extract_roles(result)
            return UserInfo(
                sub=result["sub"],
                preferred_username=result.get("preferred_username", ""),
                email=result.get("email"),
                email_verified=result.get("email_verified", False),
                name=result.get("name"),
                roles=roles,
            )

    async def introspect_token(self, access_token: str) -> dict[str, Any]:
        """验证并内省令牌。

        Args:
            access_token: 访问令牌

        Returns:
            令牌内省结果
        """
        url = f"{self._base_url}/protocol/openid-connect/token/introspect"
        data = {
            "token": access_token,
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
        }
        async with httpx.AsyncClient(verify=self._config.verify_ssl) as client:
            response = await client.post(url, data=data)
            response.raise_for_status()
            return response.json()

    async def logout(self, refresh_token: str) -> None:
        """登出（撤销令牌）。

        Args:
            refresh_token: 刷新令牌
        """
        url = f"{self._base_url}/protocol/openid-connect/logout"
        data = {
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
            "refresh_token": refresh_token,
        }
        async with httpx.AsyncClient(verify=self._config.verify_ssl) as client:
            response = await client.post(url, data=data)
            response.raise_for_status()

    def _extract_roles(self, user_info: dict[str, Any]) -> list[str]:
        """从用户信息中提取角色。"""
        roles: list[str] = []
        # Realm 角色
        realm_access = user_info.get("realm_access", {})
        roles.extend(realm_access.get("roles", []))
        # 客户端角色
        resource_access = user_info.get("resource_access", {})
        client_roles = resource_access.get(self._config.client_id, {})
        roles.extend(client_roles.get("roles", []))
        return roles


class KeycloakAuthMiddleware:
    """Keycloak 认证中间件。

    用于 FastAPI 路由保护。
    """

    def __init__(self, client: KeycloakClient) -> None:
        """初始化中间件。

        Args:
            client: Keycloak 客户端
        """
        self._client = client

    async def verify_token(self, token: str) -> UserInfo:
        """验证令牌并返回用户信息。

        Args:
            token: Bearer 令牌

        Returns:
            用户信息

        Raises:
            ValueError: 令牌无效
        """
        # 内省令牌
        introspection = await self._client.introspect_token(token)
        if not introspection.get("active", False):
            raise ValueError("令牌无效或已过期")
        # 获取用户信息
        return await self._client.get_user_info(token)

    async def require_role(self, token: str, role: str) -> UserInfo:
        """要求特定角色。

        Args:
            token: Bearer 令牌
            role: 必需角色

        Returns:
            用户信息

        Raises:
            ValueError: 无权限
        """
        user = await self.verify_token(token)
        if not user.has_role(role):
            raise ValueError(f"用户没有 '{role}' 角色权限")
        return user


# ============ FastAPI 依赖注入 ============


# 预定义角色
class Role:
    """预定义角色。"""

    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


def get_keycloak_config_from_env() -> KeycloakConfig:
    """从环境变量获取 Keycloak 配置。"""
    import os

    return KeycloakConfig(
        server_url=os.getenv("KEYCLOAK_SERVER_URL", "http://localhost:8080"),
        realm=os.getenv("KEYCLOAK_REALM", "baize-core"),
        client_id=os.getenv("KEYCLOAK_CLIENT_ID", "baize-core-api"),
        client_secret=os.getenv("KEYCLOAK_CLIENT_SECRET", ""),
        verify_ssl=os.getenv("KEYCLOAK_VERIFY_SSL", "true").lower() == "true",
    )


# 全局客户端实例（延迟初始化）
_keycloak_client: KeycloakClient | None = None
_auth_middleware: KeycloakAuthMiddleware | None = None


def get_keycloak_client() -> KeycloakClient:
    """获取 Keycloak 客户端单例。"""
    global _keycloak_client
    if _keycloak_client is None:
        config = get_keycloak_config_from_env()
        _keycloak_client = KeycloakClient(config)
    return _keycloak_client


def get_auth_middleware() -> KeycloakAuthMiddleware:
    """获取认证中间件单例。"""
    global _auth_middleware
    if _auth_middleware is None:
        _auth_middleware = KeycloakAuthMiddleware(get_keycloak_client())
    return _auth_middleware


def create_auth_dependency(required_roles: list[str] | None = None) -> Any:
    """创建 FastAPI 认证依赖。

    Args:
        required_roles: 必需角色列表（任一匹配即可）

    Returns:
        FastAPI 依赖函数
    """
    from fastapi import Depends, HTTPException, status
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

    security = HTTPBearer()

    async def auth_dependency(
        credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    ) -> UserInfo:
        """认证依赖函数。"""
        token = credentials.credentials
        middleware = get_auth_middleware()

        try:
            user = await middleware.verify_token(token)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except Exception as exc:
            logger.error("认证错误: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="认证失败",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        # 检查角色
        if required_roles:
            has_role = any(user.has_role(role) for role in required_roles)
            if not has_role:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"需要以下角色之一: {required_roles}",
                )

        return user

    return auth_dependency


# 预定义依赖
def get_current_user() -> Any:
    """获取当前用户（任意已认证用户）。"""
    return create_auth_dependency()


def require_admin() -> Any:
    """要求管理员角色。"""
    return create_auth_dependency([Role.ADMIN])


def require_analyst() -> Any:
    """要求分析员角色（或更高）。"""
    return create_auth_dependency([Role.ADMIN, Role.ANALYST])


def require_viewer() -> Any:
    """要求查看者角色（或更高）。"""
    return create_auth_dependency([Role.ADMIN, Role.ANALYST, Role.VIEWER])
