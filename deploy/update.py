import fcntl
import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("/opt/slaymusic")
REPOSITORY = ROOT / "repository"
RELEASES = ROOT / "releases"
CURRENT = ROOT / "current"
API = "https://api.github.com/repos/ResetPlease/slaymu5ic/actions/workflows/ci.yml/runs"
HEALTH = "http://127.0.0.1:8093/slaymusic/health"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def command(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True, timeout=300).strip()


def successful_ci(commit):
    request = urllib.request.Request(
        f"{API}?branch=main&event=push&head_sha={commit}&per_page=10",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "slaymusic-deploy"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        runs = json.load(response)["workflow_runs"]
    matching = [
        run
        for run in runs
        if run["head_sha"] == commit and run["head_branch"] == "main" and run["event"] == "push"
    ]
    if not matching:
        return False
    latest = max(matching, key=lambda run: (run["run_number"], run.get("run_attempt", 1)))
    return latest["status"] == "completed" and latest["conclusion"] == "success"


def healthy(commit):
    try:
        with urllib.request.urlopen(HEALTH, timeout=3) as response:
            if json.load(response).get("status") != "ok":
                return False
        with urllib.request.urlopen(HEALTH.replace("/health", "/version"), timeout=3) as response:
            return json.load(response).get("version") == f"1.0.0+{commit[:7]}"
    except (OSError, ValueError):
        return False


def switch(release):
    temporary = ROOT / "current.next"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(release)
    os.replace(temporary, CURRENT)


def deploy():
    command("git", "fetch", "--quiet", "origin", "main", cwd=REPOSITORY)
    commit = command("git", "rev-parse", "origin/main", cwd=REPOSITORY)
    if not re.fullmatch("[a-f0-9]{40}", commit):
        raise RuntimeError("Invalid commit SHA")
    previous = CURRENT.resolve() if CURRENT.is_symlink() else None
    if previous and previous.name == commit:
        return
    if not successful_ci(commit):
        logging.info("Waiting for successful CI commit=%s", commit[:7])
        return
    if (ROOT / "failed-release").exists() and (
        ROOT / "failed-release"
    ).read_text().strip() == commit:
        logging.error("Release is blocked after failed health check commit=%s", commit[:7])
        return
    release = RELEASES / commit
    if release.exists():
        shutil.rmtree(release)
    release.mkdir(parents=True)
    archive = subprocess.Popen(["git", "archive", commit], cwd=REPOSITORY, stdout=subprocess.PIPE)
    try:
        subprocess.run(
            ["tar", "-x", "-C", str(release)], stdin=archive.stdout, check=True, timeout=30
        )
    finally:
        archive.stdout.close()
        archive.wait(timeout=30)
    if archive.returncode:
        raise RuntimeError("Cannot export release")
    command("python3", "-m", "venv", str(release / ".venv"))
    command(
        str(release / ".venv/bin/python"),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-cache-dir",
        "-r",
        str(release / "requirements.txt"),
    )
    (release / "release.env").write_text(f"APP_VERSION=1.0.0+{commit[:7]}\n")
    switch(release)
    try:
        command("systemctl", "restart", "slaymusic")
        for _ in range(30):
            if healthy(commit):
                command("git", "merge", "--ff-only", "origin/main", cwd=REPOSITORY)
                (ROOT / "failed-release").unlink(missing_ok=True)
                logging.info("Deployed commit=%s", commit)
                return
            time.sleep(1)
        raise RuntimeError(f"Release failed health check: {commit}")
    except Exception:
        (ROOT / "failed-release").write_text(commit + "\n")
        if previous:
            switch(previous)
            command("systemctl", "restart", "slaymusic")
            logging.error("Rolled back to %s", previous.name)
        else:
            command("systemctl", "stop", "slaymusic")
        raise


if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / "update.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(0) from None
        deploy()
