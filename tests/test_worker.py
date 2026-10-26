import json
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform != "linux", reason="Linux production resource limits")
def test_worker_enforces_memory_cpu_and_file_limits():
    code = 'import json,resource; print(json.dumps({name: resource.getrlimit(getattr(resource,name)) for name in ["RLIMIT_AS","RLIMIT_CPU","RLIMIT_FSIZE","RLIMIT_CORE","RLIMIT_NOFILE"]}))'
    response = subprocess.run(
        [sys.executable, "-m", "slaymusic.worker", "128", "3", sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    limits = json.loads(response.stdout)
    assert limits["RLIMIT_AS"] == [128 * 1024 * 1024] * 2
    assert limits["RLIMIT_CPU"] == [5, 5]
    assert limits["RLIMIT_FSIZE"] == [0, 0]
    assert limits["RLIMIT_CORE"] == [0, 0]
    assert limits["RLIMIT_NOFILE"] == [32, 32]


@pytest.mark.skipif(sys.platform != "linux", reason="Linux production resource limits")
def test_worker_refuses_oversized_allocation():
    response = subprocess.run(
        [
            sys.executable,
            "-m",
            "slaymusic.worker",
            "96",
            "3",
            sys.executable,
            "-c",
            "bytearray(200 * 1024 * 1024)",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert response.returncode != 0
    assert "MemoryError" in response.stderr
