import argparse
import asyncio
import json
import subprocess
import time
from collections import Counter

import httpx


async def check(base_url: str, duration: int):
    payload = await asyncio.to_thread(
        subprocess.check_output,
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            str(duration),
            "-ac",
            "2",
            "-c:a",
            "flac",
            "-f",
            "flac",
            "pipe:1",
        ],
        timeout=30,
    )
    headers = {"Content-Type": "application/octet-stream"}
    async with httpx.AsyncClient(base_url=base_url.rstrip("/") + "/", timeout=180) as client:
        info = await client.post("api/audio/info", content=payload, headers=headers)
        assert info.status_code == 200, info.text
        assert abs(info.json()["duration"] - duration) < 0.1
        release = asyncio.Event()
        entered = asyncio.Event()

        async def slow_body():
            yield payload[:64]
            entered.set()
            await release.wait()
            yield payload[64:]

        held = asyncio.create_task(
            client.post("api/audio/info", content=slow_body(), headers=headers)
        )
        await entered.wait()
        await asyncio.sleep(0.15)
        started = time.monotonic()
        responses = await asyncio.gather(
            *[client.post("api/audio/info", content=b"invalid", headers=headers) for _ in range(24)]
        )
        statuses = Counter(response.status_code for response in responses)
        assert statuses == {429: 24}, statuses
        health = await client.get("health")
        assert health.status_code == 200
        release.set()
        assert (await held).status_code == 200
        print(
            json.dumps(
                {
                    "parallel_rejections": dict(statuses),
                    "burst_seconds": round(time.monotonic() - started, 2),
                    "health": health.json(),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        for params in [
            {"format": "wav", "speed": 0.5, "sample_rate": 48000},
            {"format": "wav", "reverse": "true"},
            {"format": "mp3", "normalize": "true", "effect": "echo"},
            {
                "format": "wav",
                "reverse": "true",
                "normalize": "true",
                "speed": 0.5,
                "pitch": -12,
                "reverb": 0.75,
                "sample_rate": 48000,
            },
        ]:
            start = time.monotonic()
            async with client.stream(
                "POST", "api/process", params=params, content=payload, headers=headers
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise AssertionError((params, response.status_code, response.text))
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
            print(
                json.dumps(
                    {
                        "settings": params,
                        "output_bytes": total,
                        "seconds": round(time.monotonic() - start, 2),
                    }
                ),
                flush=True,
            )
        for bad in [
            b"#EXTM3U\nhttp://127.0.0.1:8000/private\n",
            b"ffconcat version 1.0\nfile /etc/passwd\n",
            b"x" * 4096,
        ]:
            response = await client.post("api/audio/info", content=bad, headers=headers)
            assert response.status_code == 422
        assert (await client.get("health")).status_code == 200
        print("Malformed inputs rejected; health remains available.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8094/slaymusic/")
    parser.add_argument("--duration", type=int, default=300)
    args = parser.parse_args()
    asyncio.run(check(args.base_url, args.duration))
