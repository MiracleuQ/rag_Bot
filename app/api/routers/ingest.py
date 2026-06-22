import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.schemas import IngestRequest, IngestResponse
from app.security.rbac import require_permission

logger = logging.getLogger(__name__)


def create_ingest_router() -> APIRouter:
    router = APIRouter()

    @router.post("/ingest", response_model=IngestResponse)
    def ingest(
        req: IngestRequest,
        ctx=require_permission("ingest", "write"),
    ) -> IngestResponse:
        from app.ingest.batch_ingest import run_ingestion

        logger.info("Ingest request: input_dir=%s dry_run=%s full_reindex=%s role=%s", req.input_dir, req.dry_run, req.full_reindex, ctx.role)
        try:
            result = run_ingestion(
                input_dir=req.input_dir,
                dry_run=req.dry_run,
                full_reindex=req.full_reindex,
            )
            return IngestResponse(**result)
        except Exception as exc:
            logger.exception("Ingest failed")
            raise HTTPException(status_code=500, detail=f"ingest failed: {exc}") from exc

    return router
