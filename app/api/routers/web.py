from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse


def create_web_router() -> APIRouter:
    router = APIRouter(include_in_schema=False)
    web_root = Path(__file__).resolve().parents[2] / "web"
    index_file = web_root / "index.html"

    @router.get("/")
    def index() -> FileResponse:
        if not index_file.exists():
            raise HTTPException(status_code=404, detail="Web page not found.")
        return FileResponse(index_file)

    return router
