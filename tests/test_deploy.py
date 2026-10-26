import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy import update


def test_ci_requires_latest_successful_push_for_exact_commit(monkeypatch):
    commit = "a" * 40
    runs = [
        {
            "head_sha": commit,
            "head_branch": "main",
            "event": "push",
            "run_number": 1,
            "status": "completed",
            "conclusion": "success",
        },
        {
            "head_sha": commit,
            "head_branch": "main",
            "event": "push",
            "run_number": 2,
            "status": "in_progress",
            "conclusion": None,
        },
    ]
    monkeypatch.setattr(
        update.urllib.request,
        "urlopen",
        lambda *a, **k: io.BytesIO(json.dumps({"workflow_runs": runs}).encode()),
    )
    assert not update.successful_ci(commit)
    runs[1].update(status="completed", conclusion="success")
    assert update.successful_ci(commit)
    assert not update.successful_ci("b" * 40)
    runs[1]["event"] = "pull_request"
    runs[0]["head_branch"] = "feature"
    assert not update.successful_ci(commit)


@pytest.fixture
def release_environment(tmp_path, monkeypatch):
    commit = "b" * 40
    previous = tmp_path / "releases" / ("a" * 40)
    previous.mkdir(parents=True)
    current = tmp_path / "current"
    current.symlink_to(previous)
    monkeypatch.setattr(update, "ROOT", tmp_path)
    monkeypatch.setattr(update, "CURRENT", current)
    monkeypatch.setattr(update, "RELEASES", tmp_path / "releases")
    monkeypatch.setattr(update, "REPOSITORY", tmp_path / "repository")
    monkeypatch.setattr(update.time, "sleep", lambda *a: None)
    calls = []

    def command(*args, **kwargs):
        calls.append(args)
        return commit if args[:2] == ("git", "rev-parse") else ""

    monkeypatch.setattr(update, "command", command)
    monkeypatch.setattr(
        update.subprocess,
        "Popen",
        lambda *a, **k: SimpleNamespace(stdout=io.BytesIO(), wait=lambda **k: None, returncode=0),
    )
    monkeypatch.setattr(update.subprocess, "run", lambda *a, **k: None)
    return SimpleNamespace(
        commit=commit, previous=previous, current=current, calls=calls, root=tmp_path
    )


def test_deployment_waits_for_ci(release_environment, monkeypatch):
    monkeypatch.setattr(update, "successful_ci", lambda commit: False)
    update.deploy()
    assert release_environment.current.resolve() == release_environment.previous
    assert not any(call[0] == "systemctl" for call in release_environment.calls)


def test_deployment_switches_to_healthy_release(release_environment, monkeypatch):
    monkeypatch.setattr(update, "successful_ci", lambda commit: True)
    monkeypatch.setattr(update, "healthy", lambda commit: True)
    update.deploy()
    assert release_environment.current.resolve().name == release_environment.commit
    assert ("systemctl", "restart", "slaymusic") in release_environment.calls
    assert ("git", "merge", "--ff-only", "origin/main") in release_environment.calls


def test_deployment_rolls_back_and_blocks_bad_release(release_environment, monkeypatch):
    monkeypatch.setattr(update, "successful_ci", lambda commit: True)
    monkeypatch.setattr(update, "healthy", lambda commit: False)
    with pytest.raises(RuntimeError, match="health check"):
        update.deploy()
    assert release_environment.current.resolve() == release_environment.previous
    assert (
        release_environment.root / "failed-release"
    ).read_text().strip() == release_environment.commit
    count = len(release_environment.calls)
    update.deploy()
    assert not any(call[0] == "systemctl" for call in release_environment.calls[count:])


def test_deployment_rolls_back_when_restart_fails(release_environment, monkeypatch):
    monkeypatch.setattr(update, "successful_ci", lambda commit: True)
    original_command = update.command
    restarts = 0

    def command(*args, **kwargs):
        nonlocal restarts
        if args == ("systemctl", "restart", "slaymusic"):
            restarts += 1
            if restarts == 1:
                raise RuntimeError("restart failed")
        return original_command(*args, **kwargs)

    monkeypatch.setattr(update, "command", command)
    with pytest.raises(RuntimeError, match="restart failed"):
        update.deploy()
    assert release_environment.current.resolve() == release_environment.previous
    assert restarts == 2


def test_health_requires_deployed_version(monkeypatch):
    def response(request, **kwargs):
        return io.BytesIO(
            json.dumps(
                {"status": "ok"} if request.endswith("health") else {"version": "1.0.0+aaaaaaa"}
            ).encode()
        )

    monkeypatch.setattr(update.urllib.request, "urlopen", response)
    assert update.healthy("a" * 40)
    assert not update.healthy("b" * 40)


def test_nginx_does_not_buffer_audio_to_disk():
    config = Path("deploy/nginx-location.conf").read_text()
    assert "proxy_request_buffering off;" in config
    assert "proxy_buffering off;" in config
    assert "proxy_max_temp_file_size 0;" in config
    assert "proxy_http_version 1.1;" in config
