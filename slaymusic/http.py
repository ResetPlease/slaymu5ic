import asyncio
import io
import logging
import time

from fastapi import HTTPException, Request
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse

from slaymusic.config import Settings

logger = logging.getLogger("slaymusic")


class RequestGuard:
    def __init__(self, app, settings: Settings):
        self.app = app
        self.settings = settings
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = time.monotonic()
        path = scope["path"].removeprefix(scope.get("root_path", ""))
        guarded = scope["method"] == "POST" and path.startswith("/api/")
        status = 500

        async def send_headers(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] += [
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                ]
            await send(message)

        if guarded and self.active >= self.settings.max_concurrent_jobs:
            return await JSONResponse(
                {"detail": "Сервис занят. Повторите через несколько секунд."},
                429,
                headers={"Retry-After": "5"},
            )(scope, receive, send_headers)
        if guarded:
            self.active += 1
        try:
            await self.app(scope, receive, send_headers)
        finally:
            if guarded:
                self.active -= 1
            logger.info(
                "request method=%s path=%s status=%s duration_ms=%.0f",
                scope["method"],
                path,
                status,
                (time.monotonic() - started) * 1000,
            )


async def read_audio(request: Request, settings: Settings):
    if request.headers.get("content-type", "").split(";")[0] not in (
        "application/octet-stream",
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/flac",
        "audio/ogg",
        "audio/aac",
    ):
        raise HTTPException(
            415, "Отправьте аудиофайл телом запроса с Content-Type: application/octet-stream."
        )
    limit = settings.max_upload_mb * 1024 * 1024
    length = request.headers.get("content-length")
    if length:
        try:
            size = int(length)
        except ValueError as exc:
            raise HTTPException(400, "Некорректный Content-Length.") from exc
        if size < 0:
            raise HTTPException(400, "Некорректный Content-Length.")
        if size > limit:
            raise HTTPException(413, f"Размер файла превышает {settings.max_upload_mb} МБ.")
    data = io.BytesIO()
    try:
        async with asyncio.timeout(settings.process_timeout_seconds):
            async for chunk in request.stream():
                if data.tell() + len(chunk) > limit:
                    raise HTTPException(413, f"Размер файла превышает {settings.max_upload_mb} МБ.")
                data.write(chunk)
    except ClientDisconnect as exc:
        raise HTTPException(400, "Загрузка прервана.") from exc
    except TimeoutError as exc:
        raise HTTPException(408, "Загрузка заняла слишком много времени.") from exc
    if not data.tell():
        raise HTTPException(422, "Выберите непустой аудиофайл.")
    return data.getvalue()
