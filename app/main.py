from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import create_chat_router, create_history_router, create_system_router, create_web_router
from app.bootstrap import build_rag_service
from app.config import get_settings
from app.history import ChatHistoryStore
from app.history.session_service import HistorySessionService


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    history_store = ChatHistoryStore(settings.chat_history_db_path)
    history_store.init_db()
    history_service = HistorySessionService(settings=settings, history_store=history_store)
    rag_service = build_rag_service(settings=settings)

    app.include_router(create_web_router())
    app.include_router(create_system_router(settings=settings))
    app.include_router(
        create_chat_router(
            rag_service=rag_service,
            history_service=history_service,
        )
    )
    app.include_router(
        create_history_router(
            history_service=history_service,
        )
    )
    return app


app = create_app()
