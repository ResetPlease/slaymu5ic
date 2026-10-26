import pytest
from fastapi.testclient import TestClient

from app_final import create_app
from slaymusic.config import Settings


@pytest.fixture
def client():
    with TestClient(create_app(Settings())) as client:
        yield client


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "ffmpeg": True}


def test_version_comes_from_environment(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "2.3.4")
    with TestClient(create_app()) as client:
        assert client.get("/version").json() == {"version": "2.3.4"}


def test_missing_engine_is_unhealthy():
    with TestClient(create_app(Settings(ffmpeg_binary="/nonexistent/ffmpeg"))) as client:
        assert client.get("/health").status_code == 503


def test_prefix_routes_and_docs():
    with TestClient(create_app(Settings(base_path="/slaymusic"))) as client:
        assert client.get("/slaymusic/health").status_code == 200
        assert client.get("/slaymusic/").status_code == 200
        assert client.get("/slaymusic/static/app.js").status_code == 200
        assert "/slaymusic/openapi.json" in client.get("/slaymusic/docs").text
        assert client.get("/slaymusic/openapi.json").json()["servers"] == [{"url": "/slaymusic"}]
        assert client.get("/health").status_code == 404


def test_formats_and_privacy_notice(client):
    response = client.get("/api/formats")
    assert response.json()["formats"] == ["wav", "mp3", "flac", "ogg", "aac"]
    assert response.headers["cache-control"] == "no-store"
    assert "не сохраняются на сервере" in client.get("/").text


@pytest.mark.parametrize(
    "key,value", [("MAX_UPLOAD_MB", "0"), ("MAX_CONCURRENT_JOBS", "-1"), ("APP_BASE_PATH", "bad")]
)
def test_invalid_environment_fails_early(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        Settings.from_env()
