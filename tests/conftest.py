import io
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app_final import create_app
from slaymusic.config import Settings


def make_wav(duration=2, frequency=440, amplitude=0.25, rate=44100, channels=2):
    time = np.arange(round(duration * rate)) / rate
    signal = (np.sin(2 * np.pi * frequency * time) * amplitude * 32767).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(np.repeat(signal[:, None], channels, axis=1).tobytes())
    return output.getvalue()


@pytest.fixture
def tone():
    return make_wav()


@pytest.fixture
def client():
    with TestClient(create_app(Settings())) as client:
        yield client


@pytest.fixture
def upload(client, tone):
    def send(route="/api/process", data=None, **params):
        return client.post(
            route,
            params=params,
            content=tone if data is None else data,
            headers={"Content-Type": "application/octet-stream"},
        )

    return send


def read_wav(data):
    with wave.open(io.BytesIO(data)) as wav:
        rate = wav.getframerate()
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").reshape(
            -1, wav.getnchannels()
        )
        return rate, samples


def frequency(data):
    rate, samples = read_wav(data)
    signal = samples[:, 0].astype(float)
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
    return np.fft.rfftfreq(len(signal), 1 / rate)[np.argmax(spectrum)]
