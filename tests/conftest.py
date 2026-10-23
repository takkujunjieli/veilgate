import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from veilgate.app import build_app
from veilgate.audit import AuditSink
from veilgate.config import Settings

TOKEN = "a" * 43
OTHER_TOKEN = "b" * 43
SECRET = "PRIVATE-SOURCE-SENTINEL"


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    root = tmp_path.resolve() / "data"
    root.mkdir()
    source = root / "customers.csv"
    source.write_text(
        f"name,email,region,amount\n{SECRET},private@example.com,East,100\nBob,b@x.test,West,200\n"
    )
    monkeypatch.setenv("TEST_TOKEN", TOKEN)
    monkeypatch.setenv("OTHER_TOKEN", OTHER_TOKEN)
    config = {
        "schema_version": 1,
        "policy_version": "test-v1",
        "data_root": str(root),
        "principals": [
            {"id": "alice", "token_env": "TEST_TOKEN"},
            {"id": "bob", "token_env": "OTHER_TOKEN"},
        ],
        "resources": [
            {
                "id": "customers",
                "path": "customers.csv",
                "allowed_principals": ["alice"],
                "published_fields": ["region", "amount"],
            }
        ],
    }
    return {"root": root, "source": source, "config": config, "log": io.StringIO()}


@pytest.fixture
def client(setup: dict[str, Any]) -> Iterator[TestClient]:
    app = build_app(Settings.model_validate(setup["config"]), AuditSink(setup["log"]))
    with TestClient(app) as client:
        client.headers["Authorization"] = f"Bearer {TOKEN}"
        yield client
