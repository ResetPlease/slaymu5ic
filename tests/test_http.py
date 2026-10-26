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
