from app.api.routers.chat import create_chat_router
from app.api.routers.history import create_history_router
from app.api.routers.ingest import create_ingest_router
from app.api.routers.system import create_system_router
from app.api.routers.web import create_web_router

__all__ = ["create_chat_router", "create_history_router", "create_ingest_router", "create_system_router", "create_web_router"]
