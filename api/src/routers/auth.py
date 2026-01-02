from fastapi import APIRouter, Response, Depends, HTTPException, status, Request

from ..auth import (
    verify_password,
    verify_password_and_get_scope,
    hash_password,
    create_session_token,
    set_session_cookie,
    clear_session_cookie,
    get_current_session,
    get_scope_from_token,
)
from ..config import get_settings
from ..schemas.auth import LoginRequest, LoginResponse, AuthStatus

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, response: Response):
    """Login with scoped password."""
    scope = verify_password_and_get_scope(request.password)
    if not scope:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password"
        )
    
    token = create_session_token(scope=scope)
    set_session_cookie(response, token)
    
    return LoginResponse(message="Login successful", scope=scope)


@router.post("/logout")
async def logout(response: Response):
    """Clear the session cookie."""
    clear_session_cookie(response)
    return {"message": "Logged out"}


@router.get("/me", response_model=AuthStatus)
async def get_auth_status(session: str = Depends(get_current_session)):
    """Check if the current session is valid and return scope."""
    scope = get_scope_from_token(session)
    return AuthStatus(authenticated=True, scope=scope)


@router.post("/change-password")
async def change_password(
    request: LoginRequest,
    session: str = Depends(get_current_session)
):
    """Change the archive password. Requires current session."""
    # In a real app, you'd also verify the old password
    new_hash = hash_password(request.password)
    # Note: This would need to persist the new hash to env/config
    # For now, just return the hash for manual update
    return {
        "message": "Password hash generated. Update ARCHIVE_PASSWORD_HASH in .env",
        "hash": new_hash
    }
