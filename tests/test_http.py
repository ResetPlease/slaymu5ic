import asyncio

from slaymusic.config import Settings
from slaymusic.http import RequestGuard


def test_busy_requests_rejected_before_reading_body():
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        messages = []

        async def app(scope, receive, send):
            started.set()
            await release.wait()

        async def receive():
            raise AssertionError("Rejected upload body must not be read")

        async def send(message):
            messages.append(message)

        guard = RequestGuard(app, Settings(max_concurrent_jobs=1))
        scope = {
            "type": "http",
            "path": "/slaymusic/api/process",
            "root_path": "/slaymusic",
            "method": "POST",
        }
        first = asyncio.create_task(guard(scope, receive, send))
        await started.wait()
        await guard(scope, receive, send)
        assert messages[0]["status"] == 429
        assert (b"retry-after", b"5") in messages[0]["headers"]
        release.set()
        await first
        assert guard.active == 0

    asyncio.run(scenario())


def test_many_uploads_are_rejected_without_buffering_and_health_is_available():
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def app(scope, receive, send):
            nonlocal calls
            calls += 1
            if scope["method"] == "POST":
                started.set()
                await release.wait()
            else:
                await send({"type": "http.response.start", "status": 200, "headers": []})

        async def receive():
            raise AssertionError("Excess upload must never be buffered")

        async def send(message):
            pass

        guard = RequestGuard(app, Settings(max_concurrent_jobs=1))
        scope = {"type": "http", "path": "/api/process", "method": "POST"}
        first = asyncio.create_task(guard(scope, receive, send))
        await started.wait()
        statuses = []

        async def reject():
            async def collect(message):
                if message["type"] == "http.response.start":
                    statuses.append(message["status"])

            await guard(scope, receive, collect)

        await asyncio.gather(*(reject() for _ in range(100)))
        assert statuses == [429] * 100
        assert calls == 1
        await guard({**scope, "path": "/health", "method": "GET"}, receive, send)
        assert calls == 2
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        assert guard.active == 0

    asyncio.run(scenario())


def test_upload_disconnect_and_deadline_release_slots():
    import pytest
    from fastapi import HTTPException, Request

    from slaymusic.http import read_audio

    async def scenario():
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/process",
            "headers": [(b"content-type", b"application/octet-stream")],
        }

        async def disconnected():
            return {"type": "http.disconnect"}

        with pytest.raises(HTTPException) as error:
            await read_audio(Request(scope, disconnected), Settings())
        assert error.value.status_code == 400

        async def slow():
            await asyncio.sleep(10)

        with pytest.raises(HTTPException) as error:
            await read_audio(Request(scope, slow), Settings(process_timeout_seconds=0.01))
        assert error.value.status_code == 408

    asyncio.run(scenario())
