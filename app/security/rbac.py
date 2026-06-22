import hmac
from enum import Enum
from typing import Optional

from fastapi import Depends, Header, HTTPException


class Role(str, Enum):
    VIEWER = "viewer"
    EDITOR = "editor"
    ADMIN = "admin"


# admin > editor > viewer
_ROLE_HIERARCHY: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.EDITOR: 1,
    Role.ADMIN: 2,
}

# resource -> role -> allowed actions
_PERMISSION_MATRIX: dict[str, dict[Role, set[str]]] = {
    "chat": {
        Role.VIEWER: {"read"},
        Role.EDITOR: {"read"},
        Role.ADMIN: {"read"},
    },
    "ingest": {
        Role.VIEWER: set(),
        Role.EDITOR: {"write"},
        Role.ADMIN: {"write", "delete"},
    },
    "history": {
        Role.VIEWER: {"read_own"},
        Role.EDITOR: {"read_own"},
        Role.ADMIN: {"read_all", "delete"},
    },
    "user": {
        Role.VIEWER: set(),
        Role.EDITOR: set(),
        Role.ADMIN: {"manage"},
    },
}


class RBACContext:
    def __init__(self, role: Role, user_id: str):
        self.role = role
        self.user_id = user_id

    def has_permission(self, resource: str, action: str) -> bool:
        resource_perms = _PERMISSION_MATRIX.get(resource, {})
        allowed_actions = resource_perms.get(self.role, set())
        return action in allowed_actions

    def require_permission(self, resource: str, action: str) -> None:
        if not self.has_permission(resource, action):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions: role={self.role.value} resource={resource} action={action}",
            )


def _resolve_role(
    x_role: Optional[str],
    x_user_id: Optional[str],
    x_admin_token: Optional[str],
    settings,
) -> tuple[Role, str]:
    role = Role.VIEWER
    user_id = ""

    if x_user_id:
        user_id = x_user_id.strip()

    if x_role:
        try:
            role = Role(x_role.strip().lower())
        except ValueError:
            role = Role.VIEWER

    if settings.rbac_admin_token and x_admin_token:
        if hmac.compare_digest(x_admin_token.strip(), settings.rbac_admin_token):
            role = Role.ADMIN

    return role, user_id


def require_role(min_role: Role = Role.VIEWER):
    def dependency(
        x_role: Optional[str] = Header(default=None, alias="X-Role"),
        x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
    ):
        from app.config import get_settings
        settings = get_settings()

        if not settings.rbac_enabled:
            return RBACContext(role=Role.ADMIN, user_id=x_user_id or "anonymous")

        role, user_id = _resolve_role(x_role, x_user_id, x_admin_token, settings)

        if _ROLE_HIERARCHY[role] < _ROLE_HIERARCHY[min_role]:
            raise HTTPException(
                status_code=403,
                detail=f"Minimum role required: {min_role.value}, your role: {role.value}",
            )

        return RBACContext(role=role, user_id=user_id)

    return Depends(dependency)


def require_permission(resource: str, action: str):
    def dependency(
        x_role: Optional[str] = Header(default=None, alias="X-Role"),
        x_user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
    ):
        from app.config import get_settings
        settings = get_settings()

        if not settings.rbac_enabled:
            return RBACContext(role=Role.ADMIN, user_id=x_user_id or "anonymous")

        role, user_id = _resolve_role(x_role, x_user_id, x_admin_token, settings)
        ctx = RBACContext(role=role, user_id=user_id)
        ctx.require_permission(resource, action)
        return ctx

    return Depends(dependency)
