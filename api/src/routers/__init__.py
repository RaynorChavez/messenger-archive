from .auth import router as auth_router
from .messages import router as messages_router
from .people import router as people_router
from .threads import router as threads_router
from .stats import router as stats_router
from .settings import router as settings_router
from .database import router as database_router
from .discussions import router as discussions_router
from .search import router as search_router
from .virtual_chat import router as virtual_chat_router
from .rooms import router as rooms_router
from .media import router as media_router

__all__ = [
    "auth_router",
    "messages_router", 
    "people_router",
    "threads_router",
    "stats_router",
    "settings_router",
    "database_router",
    "discussions_router",
    "search_router",
    "virtual_chat_router",
    "rooms_router",
    "media_router",
]
