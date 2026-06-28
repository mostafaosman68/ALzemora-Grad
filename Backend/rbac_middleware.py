"""
RBAC middleware for FastAPI.

Usage — add `Depends(require_edit)` to any route that mutates data:

    @app.post("/update-user")
    async def update_user(body: UpdateUserBody, _=Depends(require_edit)):
        ...

    @app.post("/register-person")
    async def register_person(user_id: int = Form(...), _=Depends(require_edit)):
        ...
"""

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel

# Roles that are permitted to perform write / edit operations.
_CAN_EDIT_ROLES = {"Guardian", "CareGiver"}


def _get_role_from_body(body: dict) -> str | None:
    """Extract the 'role' field sent in the request body."""
    return body.get("role")


class RoleBody(BaseModel):
    """Minimal model used solely to read the role field off the request body."""
    role: str


async def require_edit(body: RoleBody) -> None:
    """
    FastAPI dependency that rejects the request with 403 Forbidden
    if the role in the request body is not an edit-permitted role.

    NOTE: This is a defence-in-depth check. For stronger security, derive
    the role server-side from a signed JWT or a database lookup by user_id
    rather than trusting the value sent by the client.
    """
    if body.role not in _CAN_EDIT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Patient accounts do not have permission to perform this action.",
        )
