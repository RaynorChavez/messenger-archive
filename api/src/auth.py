from datetime import datetime, timedelta
from typing import Optional, Literal, List
import bcrypt
from jose import jwt, JWTError
from fastapi import HTTPException, status, Depends, Response, Request
from fastapi.security import HTTPBearer

from .config import get_settings

settings = get_settings()

ALGORITHM = "HS256"
TOKEN_COOKIE_NAME = "archive_session"

security = HTTPBearer(auto_error=False)

# Scope type definition
Scope = Literal["admin", "general", "immersion"]

# Map scopes to accessible room IDs
SCOPE_ROOM_ACCESS: dict[Scope, List[int]] = {
    "admin": [1, 2],      # Both rooms
    "general": [1],       # Room 1 (General Chat) only
    "immersion": [2],     # Room 2 (Immersion) only
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def verify_password_and_get_scope(password: str) -> Optional[Scope]:
    """Try each password hash, return matching scope or None."""
    if verify_password(password, settings.admin_password_hash):
        return "admin"
    if verify_password(password, settings.general_password_hash):
        return "general"
    if verify_password(password, settings.immersion_password_hash):
        return "immersion"
    # Fallback to legacy password for backward compat -> admin
    if verify_password(password, settings.archive_password_hash):
        return "admin"
    return None


def get_allowed_room_ids(scope: Scope) -> List[int]:
    """Get room IDs accessible to this scope."""
    return SCOPE_ROOM_ACCESS.get(scope, [])


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=12)
    ).decode("utf-8")


def create_session_token(scope: Scope, expires_delta: Optional[timedelta] = None) -> str:
    """Create a session JWT token with scope."""
    if expires_delta is None:
        expires_delta = timedelta(hours=settings.session_expire_hours)
    
    expire = datetime.utcnow() + expires_delta
    to_encode = {
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "session",
        "scope": scope
    }
    return jwt.encode(to_encode, settings.session_secret, algorithm=ALGORITHM)


def verify_session_token(token: str) -> bool:
    """Verify a session token is valid."""
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=[ALGORITHM])
        return payload.get("type") == "session"
    except JWTError:
        return False


def get_scope_from_token(token: str) -> Optional[Scope]:
    """Extract scope from JWT token."""
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=[ALGORITHM])
        if payload.get("type") != "session":
            return None
        # Default to admin for backward compat with old tokens
        scope = payload.get("scope", "admin")
        if scope in ("admin", "general", "immersion"):
            return scope  # type: ignore
        return "admin"
    except JWTError:
        return None


def set_session_cookie(response: Response, token: str) -> None:
    """Set the session cookie on a response."""
    response.set_cookie(
        key=TOKEN_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=settings.session_expire_hours * 3600
    )


def clear_session_cookie(response: Response) -> None:
    """Clear the session cookie."""
    response.delete_cookie(key=TOKEN_COOKIE_NAME)


async def get_current_session(request: Request) -> str:
    """
    Dependency that validates the session from cookie.
    Raises 401 if not authenticated.
    """
    token = request.cookies.get(TOKEN_COOKIE_NAME)
    
    if not token or not verify_session_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    return token


async def get_current_session_or_internal(request: Request) -> str:
    """
    Dependency that validates either a session cookie OR an internal API key.
    Used for endpoints that need to be called by internal services.
    """
    # Check for internal API key header first
    internal_key = request.headers.get("X-Internal-API-Key")
    if internal_key and internal_key == settings.internal_api_key:
        return "internal"
    
    # Fall back to session cookie
    token = request.cookies.get(TOKEN_COOKIE_NAME)
    
    if not token or not verify_session_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    return token


async def get_current_scope(request: Request) -> Scope:
    """
    Dependency that extracts the scope from the session token.
    Raises 401 if not authenticated.
    """
    token = request.cookies.get(TOKEN_COOKIE_NAME)
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    scope = get_scope_from_token(token)
    if not scope:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )
    
    return scope


def require_scope(*allowed_scopes: Scope):
    """
    Dependency factory: require one of the specified scopes.
    Usage: Depends(require_scope("admin")) or Depends(require_scope("admin", "general"))
    """
    async def check_scope(scope: Scope = Depends(get_current_scope)) -> Scope:
        if scope not in allowed_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return scope
    return check_scope
