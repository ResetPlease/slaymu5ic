import logging
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.applications import Starlette
from starlette.routing import Mount

from slaymusic.config import Settings


def create_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("slaymusic")

    @asynccontextmanager
    async def lifespan(app):
        logger.info(
            "service_started version=%s base_path=%s", settings.version, settings.base_path or "/"
        )
        yield
        logger.info("service_stopped")

    api = FastAPI(title="Slaymusic API", version=settings.version, lifespan=lifespan)
    api.state.settings = settings

    @api.get("/health", tags=["Service"])
    async def health():
        ready = shutil.which(settings.ffmpeg_binary) is not None
        return JSONResponse(
            {"status": "ok" if ready else "unavailable", "ffmpeg": ready},
            status_code=200 if ready else 503,
        )

    @api.get("/version", tags=["Service"])
    async def version():
        return {"version": settings.version}

    if settings.base_path:
        return Starlette(routes=[Mount(settings.base_path, app=api)], lifespan=lifespan)
    return api


app = create_app()
