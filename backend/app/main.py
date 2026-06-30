"""FastAPI entrypoint for sof-table-extract."""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import solutions  # noqa: F401 — side-effect: registers solutions
from app.config import settings
from app.routes.batches import router as batches_router
from app.routes.benchmarks import router as benchmarks_router
from app.routes.bpmn import router as bpmn_router
from app.routes.documents import router as docs_router
from app.routes.pii_benchmarks import router as pii_benchmarks_router
from app.routes.pii_dataset_benchmarks import router as pii_dataset_benchmarks_router
from app.routes.report import router as report_router
from app.routes.reviews import router as reviews_router
from app.routes.runs import router as runs_router
from app.routes.solutions import router as solutions_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)-26s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ote.main")

app = FastAPI(title="sof-table-extract", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(docs_router)
app.include_router(solutions_router)
app.include_router(bpmn_router)
app.include_router(runs_router)
app.include_router(batches_router)
app.include_router(report_router)
app.include_router(reviews_router)
app.include_router(benchmarks_router)
app.include_router(pii_benchmarks_router)
app.include_router(pii_dataset_benchmarks_router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = (time.time() - start) * 1000
    logger.info("%s %s [%d] %.0fms", request.method, request.url.path, response.status_code, elapsed)
    return response


@app.on_event("startup")
async def on_startup():
    from app.pipeline.base import registered
    from app.workflow import db as wfdb

    settings.runs_path.mkdir(parents=True, exist_ok=True)
    wfdb.init_db()
    logger.info("data dir   : %s", settings.data_path)
    logger.info("runs dir   : %s", settings.runs_path)
    logger.info("solutions  : %s", sorted(registered().keys()))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8002, reload=True)
