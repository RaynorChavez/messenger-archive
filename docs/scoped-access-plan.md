# Scoped Access Control Implementation Plan

## Overview

Implement role-based access control with three scopes, each mapped to specific chat rooms.

| Scope | Rooms | Virtual Chat | Analysis | Other Pages |
|-------|-------|--------------|----------|-------------|
| `admin` | Both (1 & 2) | All personas | Can trigger | Full access |
| `general` | Room 1 only | Room 1 personas | View only | Filtered |
| `immersion` | Room 2 only | Room 2 personas | View only | Filtered |

### Room Mapping
- **Room 1**: General Chat - Manila Dialectics Society
- **Room 2**: Immersion - Manila Dialectics Society

---

## Phase 1: Backend Core Auth Changes

### 1. `api/src/config.py`
Add new password hash settings:
```python
admin_password_hash: str = ""
general_password_hash: str = ""  
immersion_password_hash: str = ""
```

### 2. `api/src/auth.py`
Add scope support:
```python
from typing import Literal, List

Scope = Literal["admin", "general", "immersion"]

# Map scopes to room IDs
SCOPE_ROOM_ACCESS = {
    "admin": [1, 2],      # Both rooms
    "general": [1],       # Room 1 only
    "immersion": [2],     # Room 2 only
}

def verify_password_and_get_scope(password: str) -> Scope | None:
    """Try each password hash, return matching scope or None."""
    if verify_password(password, settings.admin_password_hash):
        return "admin"
    if verify_password(password, settings.general_password_hash):
        return "general"
    if verify_password(password, settings.immersion_password_hash):
        return "immersion"
    # Fallback to old password for backward compat -> admin
    if verify_password(password, settings.archive_password_hash):
        return "admin"
    return None

def create_session_token(scope: Scope, ...) -> str:
    """Add scope to JWT payload."""
    to_encode = {
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "session",
        "scope": scope  # NEW
    }
    ...

def get_scope_from_token(token: str) -> Scope | None:
    """Extract scope from JWT."""
    payload = jwt.decode(...)
    return payload.get("scope", "admin")  # Default admin for old tokens

async def get_current_scope(request: Request) -> Scope:
    """Dependency: get scope from session token."""
    token = request.cookies.get(TOKEN_COOKIE_NAME)
    if not token:
        raise HTTPException(401)
    scope = get_scope_from_token(token)
    if not scope:
        raise HTTPException(401)
    return scope

def get_allowed_room_ids(scope: Scope) -> List[int]:
    """Get room IDs accessible to this scope."""
    return SCOPE_ROOM_ACCESS.get(scope, [])

def require_scope(*allowed_scopes: Scope):
    """Dependency factory: require one of the specified scopes."""
    async def check_scope(scope: Scope = Depends(get_current_scope)):
        if scope not in allowed_scopes:
            raise HTTPException(403, "Insufficient permissions")
        return scope
    return check_scope
```

### 3. `api/src/schemas/auth.py`
Update schemas:
```python
from typing import Literal, Optional

Scope = Literal["admin", "general", "immersion"]

class AuthStatus(BaseModel):
    authenticated: bool
    scope: Optional[Scope] = None  # NEW

class LoginResponse(BaseModel):  # NEW
    message: str
    scope: Scope
```

### 4. `api/src/routers/auth.py`
Update endpoints:
```python
@router.post("/login")
async def login(request: LoginRequest, response: Response):
    scope = verify_password_and_get_scope(request.password)
    if not scope:
        raise HTTPException(401, "Invalid password")
    
    token = create_session_token(scope=scope)
    set_session_cookie(response, token)
    
    return {"message": "Login successful", "scope": scope}

@router.get("/me", response_model=AuthStatus)
async def get_auth_status(
    request: Request,
    session: str = Depends(get_current_session)
):
    scope = get_scope_from_token(session)
    return AuthStatus(authenticated=True, scope=scope)
```

---

## Phase 2: Backend Route Protection

### 5. `api/src/routers/rooms.py`
Filter rooms by scope:
```python
from ..auth import get_current_scope, get_allowed_room_ids

@router.get("")
async def list_rooms(
    db: Session = Depends(get_db),
    scope: str = Depends(get_current_scope),
):
    allowed_rooms = get_allowed_room_ids(scope)
    # Filter query by Room.id.in_(allowed_rooms)
    ...

@router.get("/{room_id}")
async def get_room(room_id: int, ...):
    allowed_rooms = get_allowed_room_ids(scope)
    if room_id not in allowed_rooms:
        raise HTTPException(403, "No access to this room")
    ...
```

### 6. `api/src/routers/messages.py`
- Add scope dependency
- Filter by allowed rooms
- If room_id param provided, check it's allowed
- If no room_id, filter to only allowed rooms

### 7. `api/src/routers/discussions.py`
Protect analysis endpoints:
```python
from ..auth import require_scope

@router.post("/analyze")
async def start_analysis(
    ...,
    scope: str = Depends(require_scope("admin")),  # Admin only
):
    ...

@router.post("/classify-topics")
async def start_topic_classification(
    ...,
    scope: str = Depends(require_scope("admin")),  # Admin only
):
    ...
```

### 8. `api/src/routers/people.py`
- Filter by room membership
- Only show people who have messages in allowed rooms

### 9. `api/src/routers/virtual_chat.py`
- Validate participant person_ids belong to people with messages in allowed rooms

---

## Phase 3: Frontend Changes

### 10. `web/src/lib/api.ts`
Add scope types:
```typescript
export type Scope = "admin" | "general" | "immersion";

export const auth = {
  login: (password: string) =>
    fetchAPI<{ message: string; scope: Scope }>("/auth/login", {...}),
  
  me: () => fetchAPI<{ authenticated: boolean; scope: Scope }>("/auth/me"),
};
```

### 11. `web/src/contexts/auth-context.tsx` (NEW)
```typescript
"use client";
import { createContext, useContext, useState, useEffect } from "react";
import { auth, Scope } from "@/lib/api";

interface AuthContextType {
  scope: Scope | null;
  isLoading: boolean;
  refetch: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>(...);

export function AuthProvider({ children }) {
  const [scope, setScope] = useState<Scope | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  
  const fetchScope = async () => {
    try {
      const data = await auth.me();
      setScope(data.scope);
    } catch {
      setScope(null);
    } finally {
      setIsLoading(false);
    }
  };
  
  useEffect(() => { fetchScope(); }, []);
  
  return (
    <AuthContext.Provider value={{ scope, isLoading, refetch: fetchScope }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
```

### 12. `web/src/app/login/page.tsx`
Scope-based redirect:
```typescript
const handleSubmit = async (e: React.FormEvent) => {
  const result = await auth.login(password);
  
  if (result.scope === "admin") {
    router.push("/");
  } else {
    router.push("/virtual-chat");  // Both general & immersion
  }
};
```

### 13. `web/src/components/layout/sidebar.tsx`
Conditional navigation:
```typescript
const scopeNavAccess: Record<Scope, string[]> = {
  admin: ["Dashboard", "Search", "Messages", "Threads", "Discussions", "Virtual Chat", "People", "Database", "Settings"],
  general: ["Virtual Chat", "People"],
  immersion: ["Virtual Chat", "People"],
};

// Filter navigation based on scope
```

### 14. `web/src/components/layout/header.tsx`
- Filter rooms dropdown by scope
- Admin sees both, general sees room 1, immersion sees room 2

### 15. `web/src/components/no-access.tsx` (NEW)
```typescript
export function NoAccess({ message = "You don't have access to this feature" }) {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="text-center">
        <h2 className="text-xl font-semibold">Access Denied</h2>
        <p className="text-muted-foreground mt-2">{message}</p>
      </div>
    </div>
  );
}
```

### 16-17. Page-level scope checks
```typescript
// In protected pages:
const { scope } = useAuth();
if (scope !== "admin") {
  return <NoAccess message="Admin access required" />;
}

// In discussions page, conditionally show Analyze button:
{scope === "admin" && <button>Analyze</button>}
```

---

## Phase 4: Environment & Deployment

### 18. `.env` updates
```bash
# New password hashes (generate with bcrypt)
ADMIN_PASSWORD_HASH=...
GENERAL_PASSWORD_HASH=...
IMMERSION_PASSWORD_HASH=...

# Keep old one for backward compat (optional)
ARCHIVE_PASSWORD_HASH=...
```

### 19. Testing Checklist
- [ ] Login with each password, verify correct scope
- [ ] Verify room access filtering
- [ ] Verify virtual chat participant filtering
- [ ] Verify admin-only buttons hidden for other scopes
- [ ] Verify 403 responses for unauthorized API calls

---

## Files to Modify

### Backend
| File | Changes |
|------|---------|
| `api/src/config.py` | Add 3 password hash settings |
| `api/src/auth.py` | Scope in JWT, new dependencies |
| `api/src/schemas/auth.py` | Add scope to responses |
| `api/src/routers/auth.py` | Return scope on login/me |
| `api/src/routers/rooms.py` | Filter by scope |
| `api/src/routers/messages.py` | Filter by allowed rooms |
| `api/src/routers/discussions.py` | Admin-only analyze/classify |
| `api/src/routers/people.py` | Filter by room membership |
| `api/src/routers/virtual_chat.py` | Filter participants |

### Frontend
| File | Changes |
|------|---------|
| `web/src/lib/api.ts` | Add Scope type, update auth methods |
| `web/src/contexts/auth-context.tsx` | NEW - global scope state |
| `web/src/app/login/page.tsx` | Scope-based redirect |
| `web/src/components/layout/sidebar.tsx` | Conditional nav |
| `web/src/components/layout/header.tsx` | Filter room dropdown |
| `web/src/components/no-access.tsx` | NEW - access denied component |
| Various pages | Scope checks |
