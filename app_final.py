import asyncio
import logging
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.applications import Starlette
from starlette.routing import Mount

from slaymusic.audio import FORMATS, Options, decode, process_audio
from slaymusic.config import Settings
from slaymusic.http import RequestGuard, read_audio


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

    api.add_middleware(RequestGuard, settings=settings)
    static = Path(__file__).parent / "static"

    @api.get("/", include_in_schema=False)
    async def index():
        return FileResponse(static / "index.html")

    @api.get("/api/formats", tags=["Audio"])
    async def formats():
        return {
            "formats": list(FORMATS),
            "max_upload_mb": settings.max_upload_mb,
            "max_duration_seconds": settings.max_duration_seconds,
            "sample_rates": [22050, 44100, 48000],
            "bitrates": [96, 128, 192, 256, 320],
        }

    audio_body = {
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    }

    @api.post("/api/audio/info", tags=["Audio"], openapi_extra=audio_body)
    async def audio_info(request: Request):
        data = await read_audio(request, settings)
        audio = await decode(data, settings)
        return await asyncio.to_thread(audio.info, len(data))

    async def transform(request: Request, options: Annotated[Options, Query()]):
        data = await read_audio(request, settings)
        audio = await decode(data, settings)
        output = await process_audio(audio, options, settings)
        logger.info(
            "audio_processed format=%s input_bytes=%d output_bytes=%d",
            options.format,
            len(data),
            len(output),
        )
        return Response(
            output,
            media_type=FORMATS[options.format][0],
            headers={
                "Content-Disposition": f'attachment; filename="slaymusic.{options.format}"',
            },
        )

    for route in ("process", "convert", "trim", "effects"):
        api.add_api_route(
            f"/api/{route}",
            transform,
            methods=["POST"],
            name=route,
            tags=["Audio"],
            openapi_extra=audio_body,
            response_class=Response,
        )

    api.mount("/static", StaticFiles(directory=static), name="static")

    if settings.base_path:
        return Starlette(routes=[Mount(settings.base_path, app=api)], lifespan=lifespan)
    return api


app = create_app()
