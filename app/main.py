"""FastAPI server: chat API + static widget.

Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import os

# Pin compute threads BEFORE numpy/torch get imported: on a big host node a
# 1-core-limited container otherwise spawns dozens of OpenMP threads and the
# resulting contention makes startup look frozen.
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import asyncio
import json
import logging
import threading
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import config
from .ratelimit import SlidingWindowLimiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ul-chatbot")

limiter = SlidingWindowLimiter(config.RATE_LIMIT_PER_MIN, 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pipeline = None
    app.state.pipeline_ready = False
    watcher_task = None

    def _load_pipeline():
        # Loads in a background thread so the HTTP server never blocks on the
        # (slow) embedder/model load; /api/health and / stay reachable and
        # /api/chat answers "not ready" until the pipeline is up.
        try:
            from .pipeline import RagPipeline

            app.state.pipeline = RagPipeline.from_disk()
            log.info("Pipeline ready: %d chunks", len(app.state.pipeline.index.chunks))
        except FileNotFoundError:
            log.warning("Index not found. Run: python -m app.crawler && python -m app.ingest")
        except Exception:
            log.exception("Could not start the pipeline")
        finally:
            app.state.pipeline_ready = True

    def _dump_all_threads():
        import sys
        import traceback

        for tid, frame in sys._current_frames().items():
            th = next((t for t in threading.enumerate() if t.ident == tid), None)
            if th and th.name != "pipeline-load-watchdog":
                log.warning(
                    "Startup watchdog - thread %s stuck stack:\n%s",
                    th.name,
                    "".join(traceback.format_stack(frame)),
                )

    def _loader_watchdog():
        # If the pipeline cannot load within 30s, dump every thread's stack to
        # the logs so the exact hang point is visible instead of a silent stall.
        import time

        dumps = 0
        while not app.state.pipeline_ready and dumps < 10:
            time.sleep(30)
            if app.state.pipeline_ready:
                return
            dumps += 1
            log.warning("Startup watchdog - pipeline still not ready after %ds", dumps * 30)
            _dump_all_threads()

    threading.Thread(target=_load_pipeline, name="pipeline-loader", daemon=True).start()
    threading.Thread(target=_loader_watchdog, name="pipeline-load-watchdog", daemon=True).start()

    if config.AUTO_SYNC_ENABLED:
        from .watcher import watcher_agent

        async def _periodic_watcher():
            try:
                await asyncio.sleep(20)
                if app.state.pipeline:
                    log.info("Running initial background watcher sync...")
                    await asyncio.to_thread(watcher_agent.sync, app.state.pipeline)
            except asyncio.CancelledError:
                return
            except Exception:
                log.exception("Initial background watcher sync encountered an error")

            while True:
                try:
                    await asyncio.sleep(config.AUTO_SYNC_INTERVAL_MINUTES * 60)
                    if app.state.pipeline:
                        log.info("Running scheduled background watcher sync...")
                        await asyncio.to_thread(watcher_agent.sync, app.state.pipeline)
                except asyncio.CancelledError:
                    break
                except Exception:
                    log.exception("Scheduled watcher sync encountered an error")

        watcher_task = asyncio.create_task(_periodic_watcher())
        log.info("Autonomous watcher agent scheduled (interval: %d min)", config.AUTO_SYNC_INTERVAL_MINUTES)

    try:
        yield
    finally:
        if watcher_task:
            watcher_task.cancel()


app = FastAPI(title="University of Layyah Chatbot", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class Turn(BaseModel):
    role: str = "user"
    content: str = ""

    @field_validator("role", mode="before")
    @classmethod
    def sanitize_role(cls, v) -> str:
        return "assistant" if str(v).lower() == "assistant" else "user"

    @field_validator("content", mode="before")
    @classmethod
    def sanitize_content(cls, v) -> str:
        return str(v or "")[:4000]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=config.MAX_MESSAGE_CHARS)
    history: list[Turn] = Field(default_factory=list)
    stream: bool = False


class Source(BaseModel):
    title: str
    url: str


class ActionButton(BaseModel):
    label: str
    url: str
    icon: str = "portal"


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    actions: list[ActionButton] = []


def client_ip(request: Request) -> str:
    if config.TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.get("/api/health")
def health():
    p = app.state.pipeline
    unanswered_count = 0
    if config.UNANSWERED_LOG.exists():
        try:
            with config.UNANSWERED_LOG.open("r", encoding="utf-8") as f:
                unanswered_count = sum(1 for line in f if line.strip())
        except Exception:
            pass

    from .watcher import watcher_agent
    ready = getattr(app.state, "pipeline_ready", True)
    return {
        "status": "ok" if p else ("loading" if not ready else "index_missing"),
        "chunks": len(p.index.chunks) if p else 0,
        "unanswered_count": unanswered_count,
        "watcher": {
            "is_syncing": watcher_agent.is_syncing,
            "last_sync": watcher_agent.last_sync_time,
            "tracked_pages": len(watcher_agent.seen),
        },
    }


@app.get("/api/admin/unanswered")
def get_unanswered(limit: int = 50):
    """Return recently logged unanswered questions for university admin insights."""
    if not config.UNANSWERED_LOG.exists():
        return {"total": 0, "queries": []}
    queries = []
    try:
        with config.UNANSWERED_LOG.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    queries.append(json.loads(line))
    except Exception:
        log.exception("Failed to read unanswered queries")
    return {"total": len(queries), "queries": queries[-limit:][::-1]}


@app.post("/api/admin/sync")
async def trigger_sync(wait: bool = False):
    """Trigger an on-demand sync cycle to discover, parse, and index new notices and PDFs."""
    pipeline = app.state.pipeline
    if pipeline is None:
        raise HTTPException(503, "Chatbot pipeline is not ready yet.")

    from .watcher import watcher_agent

    if watcher_agent.is_syncing:
        return {"status": "in_progress", "message": "Watcher sync is already running."}

    if wait:
        stats = await asyncio.to_thread(watcher_agent.sync, pipeline)
        return {
            "status": "completed",
            "stats": stats,
            "total_chunks": len(pipeline.index.chunks),
        }

    asyncio.create_task(asyncio.to_thread(watcher_agent.sync, pipeline))
    return {"status": "started", "message": "Watcher agent sync started in background."}


@app.get("/api/admin/sync-status")
def sync_status():
    """Get real-time status and telemetry of the autonomous website watcher."""
    from .watcher import watcher_agent
    return watcher_agent.get_status(app.state.pipeline)


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    if not limiter.allow(client_ip(request)):
        raise HTTPException(429, "Bohat zyada sawal. Thori dair baad dobara koshish karein.")
    pipeline = app.state.pipeline
    if pipeline is None:
        raise HTTPException(503, "Chatbot abhi tayyar nahi hai. Admin ko index banana hoga.")

    if req.stream:
        def event_generator():
            try:
                for chunk in pipeline.chat_stream(req.message.strip(), [t.model_dump() for t in req.history]):
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            except Exception:
                log.exception("streaming chat failed")
                yield f'data: {json.dumps({"type": "error", "message": "Jawab banane mein masla aaya."}, ensure_ascii=False)}\n\n'

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        result = pipeline.chat(req.message.strip(), [t.model_dump() for t in req.history])
    except Exception:
        log.exception("chat failed")
        raise HTTPException(502, "Jawab banane mein masla aaya. Dobara koshish karein.")
    return ChatResponse(
        answer=result["answer"],
        sources=result["sources"],
        actions=result.get("actions", []),
    )


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(config.STATIC_DIR / "logo.png")


@app.get("/", include_in_schema=False)
@app.get("/demo", include_in_schema=False)
def demo():
    return FileResponse(config.STATIC_DIR / "demo.html")
