from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from jose import jwt, JWTError
from fastapi import HTTPException, status, Depends, Response, Request
from fastapi.security import HTTPBearer

from .config import get_settings

settings = get_settings()

ALGORITHM = "HS256"
TOKEN_COOKIE_NAME = "archive_session"

security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    if not hashed_password:
        return False
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8")
    )


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=12)
    ).decode("utf-8")


def create_session_token(expires_delta: Optional[timedelta] = None) -> str:
    """Create a session JWT token."""
    if expires_delta is None:
        expires_delta = timedelta(hours=settings.session_expire_hours)
    
    expire = datetime.utcnow() + expires_delta
    to_encode = {
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "session"
    }
    return jwt.encode(to_encode, settings.session_secret, algorithm=ALGORITHM)


def verify_session_token(token: str) -> bool:
    """Verify a session token is valid."""
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=[ALGORITHM])
        return payload.get("type") == "session"
    except JWTError:
        return False


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
