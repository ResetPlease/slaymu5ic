import asyncio
import io
import tempfile
import wave

import numpy as np
import pytest
from conftest import frequency, make_wav, read_wav
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app_final import create_app
from slaymusic.audio import run_ffmpeg
from slaymusic.config import Settings


def test_info_reports_real_audio(upload):
    result = upload("/api/audio/info").json()
    assert result["duration"] == pytest.approx(2, abs=0.01)
    assert result["peak_db"] == pytest.approx(-12.04, abs=0.05)
    assert result["rms_db"] == pytest.approx(-15.05, abs=0.05)
    assert len(result["waveform"]) == 600
    assert max(result["waveform"]) == pytest.approx(0.25, abs=0.001)


def test_silence_has_no_infinite_json(upload):
    result = upload("/api/audio/info", data=make_wav(amplitude=0)).json()
    assert result["rms_db"] is None
    assert result["peak_db"] is None
    assert max(result["waveform"]) == 0


@pytest.mark.parametrize(
    "format,magic",
    [("wav", b"RIFF"), ("mp3", b"ID3"), ("flac", b"fLaC"), ("ogg", b"OggS"), ("aac", b"\xff")],
)
def test_convert_and_decode_each_format(upload, format, magic):
    response = upload("/api/convert", format=format)
    assert response.status_code == 200, response.text[:200] if response.status_code != 200 else ""
    assert response.content.startswith(magic)
    assert response.headers["content-disposition"].endswith(f'slaymusic.{format}"')
    info = upload("/api/audio/info", data=response.content)
    assert info.status_code == 200
    assert info.json()["duration"] == pytest.approx(2, abs=0.15)


@pytest.mark.parametrize(
    "mode,start,end,expected",
    [
        ("keep", 0.25, 1.25, 1),
        ("remove", 0.25, 1.25, 1),
        ("remove", 0, 0.5, 1.5),
        ("remove", 1.5, 2, 1.5),
    ],
)
def test_trim_and_remove_duration(upload, mode, start, end, expected):
    result = upload("/api/trim", mode=mode, start=start, end=end)
    assert result.status_code == 200
    rate, samples = read_wav(result.content)
    assert len(samples) / rate == pytest.approx(expected, abs=0.01)


def test_remove_preserves_both_sides(upload):
    _, source = read_wav(make_wav())
    result = upload("/api/trim", start=0.5, end=1.5, mode="remove")
    _, samples = read_wav(result.content)
    np.testing.assert_array_equal(samples, np.concatenate([source[:22050], source[66150:]]))


@pytest.mark.parametrize("speed", [0.5, 1.5, 2])
def test_speed_changes_duration_without_pitch(upload, speed):
    result = upload("/api/effects", speed=speed)
    rate, samples = read_wav(result.content)
    assert len(samples) / rate == pytest.approx(2 / speed, abs=0.07)
    assert frequency(result.content) == pytest.approx(440, abs=3)


@pytest.mark.parametrize("pitch,expected", [(-12, 220), (7, 659.25), (12, 880)])
def test_pitch_preserves_duration(upload, pitch, expected):
    result = upload("/api/effects", pitch=pitch)
    assert result.status_code == 200
    rate, samples = read_wav(result.content)
    assert len(samples) / rate == pytest.approx(2, abs=0.1)
    assert frequency(result.content) == pytest.approx(expected, abs=5)


def test_volume_and_fades_change_amplitude(upload):
    result = upload(volume=0.5, fade_in=0.5, fade_out=0.5)
    rate, samples = read_wav(result.content)
    middle = np.abs(samples[rate // 2 : rate]).mean()
    assert middle == pytest.approx(32767 * 0.25 * 0.5 * 2 / np.pi, rel=0.02)
    assert np.abs(samples[:1000]).mean() < middle * 0.1
    assert np.abs(samples[-1000:]).mean() < middle * 0.1


def test_reverse_sample_order(upload, tone):
    result = upload(reverse=True)
    _, original = read_wav(tone)
    _, reversed_audio = read_wav(result.content)
    np.testing.assert_array_equal(reversed_audio, original[::-1])


def test_output_rate_and_channels(upload):
    result = upload(sample_rate=22050, channels=1)
    with wave.open(io.BytesIO(result.content)) as wav:
        assert wav.getframerate() == 22050
        assert wav.getnchannels() == 1
        assert wav.getnframes() == 44100


@pytest.mark.parametrize(
    "params",
    [
        {"effect": "echo"},
        {"effect": "telephone"},
        {"effect": "lofi"},
        {"bass": 6, "treble": -3},
        {"normalize": True},
    ],
)
def test_effects_modify_audio(upload, tone, params):
    response = upload("/api/effects", **params)
    assert response.status_code == 200
    assert response.content != tone
    rate, samples = read_wav(response.content)
    assert len(samples) / rate >= 1.9
    assert np.max(np.abs(samples)) > 0


@pytest.mark.parametrize(
    "params",
    [
        {"start": 2, "end": 1},
        {"start": -1},
        {"end": 5},
        {"speed": 0},
        {"pitch": 13},
        {"volume": 3},
        {"format": "exe"},
        {"effect": "movie=/etc/passwd"},
        {"speed": "nan"},
        {"end": "inf"},
        {"mode": "remove"},
        {"fade_in": 3},
        {"unknown": 1},
    ],
)
def test_invalid_parameters(upload, params):
    assert upload(**params).status_code == 422


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not audio",
        b"#EXTM3U\nhttp://127.0.0.1:80/private\n",
        b"ffconcat version 1.0\nfile /etc/passwd\n",
    ],
)
def test_invalid_audio_and_external_sources_rejected(upload, data):
    assert upload(data=data).status_code == 422


def test_multipart_not_accepted(client, tone):
    assert client.post("/api/process", files={"file": ("tone.wav", tone)}).status_code == 415


def test_upload_limit_with_and_without_length(tone):
    with TestClient(create_app(Settings(max_upload_mb=1))) as client:
        response = client.post(
            "/api/audio/info",
            content=tone,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(2 * 1024 * 1024),
            },
        )
        assert response.status_code == 413
        response = client.post(
            "/api/audio/info",
            content=iter([b"x" * 600000, b"y" * 600000]),
            headers={"Content-Type": "application/octet-stream"},
        )
        assert response.status_code == 413


def test_decoded_duration_limit(tone):
    with TestClient(create_app(Settings(max_duration_seconds=1))) as client:
        response = client.post(
            "/api/audio/info", content=tone, headers={"Content-Type": "application/octet-stream"}
        )
        assert response.status_code == 413


def test_no_temporary_files(upload, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Audio must never be written to a temporary file")

    monkeypatch.setattr(tempfile, "TemporaryFile", forbidden)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", forbidden)
    monkeypatch.setattr(tempfile, "SpooledTemporaryFile", forbidden)
    assert upload("/api/audio/info").status_code == 200
    assert upload().status_code == 200


def test_ffmpeg_timeout_reaps_child(tone):
    async def run():
        with pytest.raises(HTTPException) as error:
            await run_ffmpeg(
                tone,
                ["-re", "-i", "pipe:0", "-f", "s16le"],
                Settings(process_timeout_seconds=0.01),
                1000000,
            )
        assert error.value.status_code == 504

    asyncio.run(run())


def test_ffmpeg_output_is_bounded(tone):
    async def run():
        with pytest.raises(HTTPException) as error:
            await run_ffmpeg(tone, ["-i", "pipe:0", "-f", "s16le"], Settings(), 100)
        assert error.value.status_code == 413

    asyncio.run(run())


@pytest.mark.parametrize(
    "format,rate,channels,bitrate",
    [("ogg", 22050, 1, 64), ("ogg", 22050, 2, 128), ("ogg", 44100, 1, 192), ("mp3", 22050, 1, 128)],
)
def test_codec_specific_export_combinations(upload, format, rate, channels, bitrate):
    assert (
        upload(format=format, sample_rate=rate, channels=channels, bitrate=bitrate).status_code
        == 200
    )


@pytest.mark.parametrize(
    "format,rate,channels,bitrate",
    [("ogg", 22050, 1, 192), ("ogg", 44100, 1, 320), ("mp3", 22050, 2, 320)],
)
def test_unsupported_bitrate_rejected_before_processing(upload, format, rate, channels, bitrate):
    assert (
        upload(format=format, sample_rate=rate, channels=channels, bitrate=bitrate).status_code
        == 422
    )
