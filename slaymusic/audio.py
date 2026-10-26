import asyncio
import io
import math
import shutil
import sys
import wave
from dataclasses import dataclass
from typing import Literal

import numpy as np
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from slaymusic.config import Settings

RATE = 44100
CHANNELS = 2
FRAME_BYTES = 4
FORMATS = {
    "wav": ("audio/wav", ["-c:a", "pcm_s16le", "-f", "wav"]),
    "mp3": ("audio/mpeg", ["-c:a", "libmp3lame", "-f", "mp3"]),
    "flac": ("audio/flac", ["-c:a", "flac", "-f", "flac"]),
    "ogg": ("audio/ogg", ["-c:a", "libvorbis", "-f", "ogg"]),
    "aac": ("audio/aac", ["-c:a", "aac", "-f", "adts"]),
}


class Options(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    format: Literal["wav", "mp3", "flac", "ogg", "aac"] = "wav"
    start: float = Field(default=0, ge=0)
    end: float | None = Field(default=None, gt=0)
    mode: Literal["keep", "remove"] = "keep"
    speed: float = Field(default=1, ge=0.5, le=2)
    pitch: float = Field(default=0, ge=-12, le=12)
    volume: float = Field(default=1, ge=0, le=2)
    fade_in: float = Field(default=0, ge=0, le=30)
    fade_out: float = Field(default=0, ge=0, le=30)
    bass: float = Field(default=0, ge=-12, le=12)
    treble: float = Field(default=0, ge=-12, le=12)
    effect: Literal["none", "echo", "telephone", "lofi", "distortion", "tremolo"] = "none"
    reverb: float = Field(default=0, ge=0, le=0.75)
    reverb_room: Literal["room", "hall"] = "hall"
    reverse: bool = False
    normalize: bool = False
    sample_rate: Literal[22050, 44100, 48000] = 44100
    channels: Literal[1, 2] = 2
    bitrate: Literal[64, 96, 128, 192, 256, 320] = 192

    @field_validator("sample_rate", "channels", "bitrate", mode="before")
    @classmethod
    def parse_integer_option(cls, value):
        return (
            int(value) if isinstance(value, str) and value.isascii() and value.isdigit() else value
        )

    @model_validator(mode="after")
    def validate_bitrate(self):
        maximum = 320
        if self.format == "ogg":
            maximum = (
                (64 if self.channels == 1 else 128)
                if self.sample_rate == 22050
                else (192 if self.channels == 1 else 320)
            )
        elif self.format == "mp3" and self.sample_rate == 22050:
            maximum = 128
        if self.bitrate > maximum:
            raise ValueError(
                f"Для этого формата, частоты и числа каналов выберите битрейт не выше {maximum} кбит/с."
            )
        return self


@dataclass
class Audio:
    pcm: bytes

    @property
    def duration(self):
        return len(self.pcm) / (RATE * FRAME_BYTES)

    def info(self, input_size: int):
        samples = np.frombuffer(self.pcm, dtype="<i2").reshape(-1, CHANNELS)
        blocks = np.array_split(samples, min(600, len(samples)))
        peaks = [
            round(float(np.max(np.abs(block.astype(np.int32)))) / 32768, 4) for block in blocks
        ]
        power = np.einsum("ij,ij->", samples, samples, dtype=np.float64)
        rms = float(np.sqrt(power / samples.size)) / 32768
        peak = max(abs(int(samples.min())), abs(int(samples.max()))) / 32768
        return {
            "duration": round(self.duration, 4),
            "sample_rate": RATE,
            "channels": CHANNELS,
            "size": input_size,
            "bitrate_kbps": round(input_size * 8 / self.duration / 1000),
            "peak_db": round(20 * math.log10(peak), 2) if peak else None,
            "rms_db": round(20 * math.log10(rms), 2) if rms else None,
            "waveform": peaks,
        }


async def run_ffmpeg(data: bytes, args: list[str], settings: Settings, limit: int):
    if shutil.which(settings.ffmpeg_binary) is None:
        raise HTTPException(503, "Аудиодвижок недоступен. Попробуйте позже.")
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "slaymusic.worker",
            str(settings.ffmpeg_memory_mb),
            str(settings.process_timeout_seconds),
            settings.ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-max_alloc",
            "33554432",
            "-threads",
            "1",
            "-filter_threads",
            "1",
            *args,
            "-threads",
            "1",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise HTTPException(503, "Аудиодвижок недоступен. Попробуйте позже.") from exc

    async def feed():
        try:
            for offset in range(0, len(data), 65536):
                process.stdin.write(data[offset : offset + 65536])
                await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            process.stdin.close()

    async def read_output():
        result = io.BytesIO()
        while chunk := await process.stdout.read(65536):
            if result.tell() + len(chunk) > limit:
                raise HTTPException(
                    413, "Аудио превышает допустимую длительность или размер результата."
                )
            result.write(chunk)
        return result.getvalue()

    async def drain_errors():
        while await process.stderr.read(65536):
            pass

    tasks = [
        asyncio.create_task(feed()),
        asyncio.create_task(read_output()),
        asyncio.create_task(drain_errors()),
    ]
    try:
        async with asyncio.timeout(settings.process_timeout_seconds):
            results = await asyncio.gather(*tasks)
            await process.wait()
        if process.returncode or not results[1]:
            raise HTTPException(
                422, "Не удалось прочитать аудио. Используйте WAV, MP3, FLAC, OGG или AAC."
            )
        return results[1]
    except TimeoutError as exc:
        raise HTTPException(504, "Время обработки истекло. Попробуйте файл короче.") from exc
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(process.stdout.read(), process.stderr.read())
        await process.wait()


async def decode(data: bytes, settings: Settings):
    pcm = await run_ffmpeg(
        data,
        [
            "-protocol_whitelist",
            "pipe",
            "-format_whitelist",
            "wav,mp3,flac,ogg,aac",
            "-i",
            "pipe:0",
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-t",
            str(settings.max_duration_seconds + 1),
            "-ar",
            str(RATE),
            "-ac",
            str(CHANNELS),
            "-f",
            "s16le",
            "-c:a",
            "pcm_s16le",
        ],
        settings,
        settings.max_duration_seconds * RATE * FRAME_BYTES,
    )
    if len(pcm) < FRAME_BYTES:
        raise HTTPException(422, "В файле нет аудиосэмплов.")
    return Audio(pcm)


def select_audio(audio: Audio, options: Options):
    end = audio.duration if options.end is None else options.end
    if options.start >= end or options.start >= audio.duration or end > audio.duration + 0.025:
        raise HTTPException(
            422, "Границы фрагмента должны находиться внутри дорожки; начало меньше конца."
        )
    start_frame = round(options.start * RATE) * FRAME_BYTES
    end_frame = min(round(end * RATE) * FRAME_BYTES, len(audio.pcm))
    pcm = (
        audio.pcm[start_frame:end_frame]
        if options.mode == "keep"
        else audio.pcm[:start_frame] + audio.pcm[end_frame:]
    )
    if len(pcm) < FRAME_BYTES:
        raise HTTPException(422, "Нельзя удалить всю дорожку.")
    return Audio(pcm)


def filters(options: Options, duration: float):
    chain = []
    if options.reverse:
        chain.append("areverse")
    if options.pitch:
        factor = 2 ** (options.pitch / 12)
        chain.extend(
            [f"asetrate={RATE * factor:.8f}", f"aresample={RATE}", f"atempo={1 / factor:.8f}"]
        )
    if options.speed != 1:
        chain.append(f"atempo={options.speed}")
    if options.bass:
        chain.append(f"bass=g={options.bass}")
    if options.treble:
        chain.append(f"treble=g={options.treble}")
    if options.effect == "echo":
        chain.append("aecho=0.8:0.7:180|360:0.35|0.2")
    elif options.effect == "telephone":
        chain.extend(["highpass=f=400", "lowpass=f=3400"])
    elif options.effect == "lofi":
        chain.extend(["lowpass=f=3500", "acrusher=bits=8:mix=0.6"])
    elif options.effect == "distortion":
        chain.append("asoftclip=type=tanh:threshold=0.4:output=0.7:oversample=2")
    elif options.effect == "tremolo":
        chain.append("tremolo=f=5:d=0.6")
    if options.normalize:
        chain.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    if options.volume != 1:
        chain.append(f"volume={options.volume}")
    output_duration = duration / options.speed + (0.36 if options.effect == "echo" else 0)
    if max(options.fade_in, options.fade_out) > output_duration:
        raise HTTPException(422, "Плавное появление и затухание не могут быть длиннее результата.")
    if options.fade_in:
        chain.append(f"afade=t=in:d={options.fade_in}")
    if options.fade_out:
        chain.append(
            f"afade=t=out:st={max(0, output_duration - options.fade_out):.6f}:d={options.fade_out}"
        )
    return chain


async def process_audio(audio: Audio, options: Options, settings: Settings):
    selected = select_audio(audio, options)
    chain = filters(options, selected.duration)
    args = [
        "-protocol_whitelist",
        "pipe",
        "-f",
        "s16le",
        "-ar",
        str(RATE),
        "-ac",
        str(CHANNELS),
        "-i",
        "pipe:0",
    ]
    if options.reverb:
        tail = 0.65 if options.reverb_room == "room" else 1.6
        impulses = []
        impulse_gain = 0.0
        positions = np.arange(round(tail * RATE), dtype=np.float64)
        for seed in (1, 101):
            values = np.sin((positions + seed) * 12.9898) * 43758.5453
            impulse = (
                0.018 * (2 * (values - np.floor(values)) - 1) * np.exp(-5 * positions / RATE / tail)
            )
            impulse_gain = max(impulse_gain, float(np.abs(impulse).sum()))
            noise = f"sin((n+{seed})*12.9898)*43758.5453"
            impulses.append(f"0.018*(2*({noise}-floor({noise}))-1)*exp(-5*t/{tail})")
        graph = (
            f"[0:a]{','.join(chain) or 'anull'},aresample={RATE},apad=pad_dur={tail},asplit=2[dry][send];"
            f"aevalsrc='{'|'.join(impulses)}':s={RATE}:d={tail},atrim=duration={tail}[ir];"
            f"[send][ir]afir=dry=1:wet=1:maxir=2:precision=float,volume={impulse_gain}[wet];"
            f"[dry][wet]amix=inputs=2:weights='{1 - options.reverb} {options.reverb}':"
            "normalize=0:duration=first[out]"
        )
        args += ["-filter_complex_threads", "1", "-filter_complex", graph, "-map", "[out]"]
    elif chain:
        args += ["-af", ",".join(chain)]
    args += ["-map_metadata", "-1", "-ar", str(options.sample_rate), "-ac", str(options.channels)]
    if options.format in ("mp3", "ogg", "aac"):
        args += ["-b:a", f"{options.bitrate}k"]
    args += (
        ["-c:a", "pcm_s16le", "-f", "s16le"]
        if options.format == "wav"
        else FORMATS[options.format][1]
    )
    result = await run_ffmpeg(
        selected.pcm, args, settings, (settings.max_duration_seconds * 2 + 4) * 48000 * FRAME_BYTES
    )
    if options.format == "wav":
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as output:
            output.setnchannels(options.channels)
            output.setsampwidth(2)
            output.setframerate(options.sample_rate)
            output.writeframes(result)
        return buffer.getvalue()
    return result
