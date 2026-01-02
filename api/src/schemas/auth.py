from pydantic import BaseModel
from typing import Literal, Optional


# Scope type
Scope = Literal["admin", "general", "immersion"]


class LoginRequest(BaseModel):
    """Login request with password."""
    password: str


class LoginResponse(BaseModel):
    """Login response with scope."""
    message: str
    scope: Scope


class AuthStatus(BaseModel):
    """Authentication status response."""
    authenticated: bool
    scope: Optional[Scope] = None
