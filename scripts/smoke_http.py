"""Exercise the installed CLI over real loopback HTTP using only synthetic data."""

import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    token = secrets.token_urlsafe(32)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "VEILGATE_CONFIG": str(root / "examples/policy.toml"),
        "VEILGATE_DATA_ROOT": str((root / "examples/data").resolve()),
        "VEILGATE_DEMO_TOKEN": token,
    }
    base = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(
            [str(root / ".venv/bin/veilgate"), "--port", str(port)],
            env=env,
            stdout=output,
            stderr=output,
        )
        try:
            for _ in range(100):
                if process.poll() is not None:
                    output.seek(0)
                    diagnostic = output.read().decode("utf-8", errors="replace")
                    raise RuntimeError(
                        "synthetic smoke startup failed: " + diagnostic.replace(token, "[REDACTED]")
                    )
                try:
                    with urllib.request.urlopen(base + "/readyz", timeout=1) as response:
                        assert response.status == 200
                    break
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(0.05)
            else:
                raise RuntimeError("service did not become ready")
            for fields, expected in [(None, 200), (["email"], 403)]:
                body = {} if fields is None else {"fields": fields}
                request = urllib.request.Request(
                    base + "/v1/resources/customers/read",
                    data=json.dumps(body).encode(),
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
                try:
                    with urllib.request.urlopen(request, timeout=2) as response:
                        assert response.status == expected
                        result = json.load(response)
                        assert result["rows"] == [
                            {"region": "East", "amount": "100"},
                            {"region": "West", "amount": "200"},
                        ]
                except urllib.error.HTTPError as exc:
                    assert exc.code == expected
                    assert json.load(exc) == {"error": {"code": "fields_not_allowed"}}
            print("HTTP smoke passed: startup, health, approved publication, forbidden field.")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
