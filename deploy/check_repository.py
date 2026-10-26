import pathlib
import subprocess

paths = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
for name in filter(None, paths):
    path = pathlib.Path(name)
    if (
        path.name == "secret.txt"
        or (path.name.startswith(".env") and path.name != ".env.example")
        or path.suffix in {".pem", ".key"}
    ):
        raise SystemExit(f"Forbidden tracked file: {name}")
    content = path.read_bytes()
    markers = [b"-----BEGIN " + kind + b" PRIVATE KEY-----" for kind in (b"RSA", b"OPENSSH", b"EC")]
    if any(marker in content for marker in markers):
        raise SystemExit(f"Private key found: {name}")
print("Repository contains no forbidden secret files or private keys.")
