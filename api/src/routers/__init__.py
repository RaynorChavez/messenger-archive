from .auth import router as auth_router
from .messages import router as messages_router
from .people import router as people_router
from .threads import router as threads_router
from .stats import router as stats_router
from .settings import router as settings_router
from .database import router as database_router

__all__ = [
    "auth_router",
    "messages_router", 
    "people_router",
    "threads_router",
    "stats_router",
    "settings_router",
    "database_router",
]
