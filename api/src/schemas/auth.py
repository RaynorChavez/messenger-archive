from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Login request with password."""
    password: str


class AuthStatus(BaseModel):
    """Authentication status response."""
    authenticated: bool
