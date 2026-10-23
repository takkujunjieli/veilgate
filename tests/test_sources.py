import os
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from veilgate.app import build_app
from veilgate.audit import AuditSink
from veilgate.config import Settings
from veilgate.errors import GatewayError, StartupError
from veilgate.files import FileStore

from .conftest import SECRET, TOKEN

URL = "/v1/resources/customers/read"


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"region,amount,region\nEast,100,West\n",
        b"region,\nEast,100\n",
        b"region\nEast\n",
        b"region,amount\nEast,100,extra\n",
        b"region,amount\nEast\n",
        b'region,amount\n"unterminated,100',
        b"region,amount\nEast,\xff\n",
        b"region,amount\nEast,\x00\n",
        b"region,amount\nEast,100\n\n",
        b"region,amount\nEast,100\nWest\n",
        b"region,amount\n" + b"x" * 140_000 + b",100\n",
    ],
)
def test_invalid_source_never_partially_released(
    client: TestClient, setup: dict[str, Any], raw: bytes
) -> None:
    setup["source"].write_bytes(raw)
    response = client.post(URL, json={})
    assert response.status_code == 422
    assert response.json() == {"error": {"code": "invalid_source"}}
    assert "East" not in response.text


def test_quoted_cells_and_utf8_bom(client: TestClient, setup: dict[str, Any]) -> None:
    setup["source"].write_bytes('\ufeffregion,amount,email\r\n"East,北",100,"x\ny"\r\n'.encode())
    response = client.post(URL, json={})
    assert response.status_code == 200
    assert response.json()["rows"] == [{"region": "East,北", "amount": "100"}]


@pytest.mark.parametrize("limit", ["max_file_bytes", "max_rows", "max_columns", "max_output_bytes"])
def test_resource_limits(setup: dict[str, Any], limit: str) -> None:
    setup["config"]["limits"] = {limit: 128 if limit == "max_output_bytes" else 1}
    app = build_app(Settings.model_validate(setup["config"]), AuditSink(setup["log"]))
    with TestClient(app) as client:
        response = client.post(URL, json={}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == (422 if limit == "max_columns" else 413)
    assert SECRET not in response.text + setup["log"].getvalue()


@pytest.mark.parametrize("kind", ["file_link", "directory", "hard_link", "fifo", "missing"])
def test_nonregular_or_linked_sources_denied(
    client: TestClient, setup: dict[str, Any], kind: str
) -> None:
    source = setup["source"]
    original = source.read_bytes()
    source.unlink()
    outside = setup["root"].parent / "private.csv"
    outside.write_bytes(original)
    if kind == "file_link":
        source.symlink_to(outside)
    elif kind == "directory":
        source.mkdir()
    elif kind == "hard_link":
        os.link(outside, source)
    elif kind == "fifo":
        os.mkfifo(source)
    response = client.post(URL, json={})
    assert response.status_code == 422
    assert SECRET not in response.text


def test_intermediate_symlink_denied(setup: dict[str, Any]) -> None:
    (setup["root"] / "link").symlink_to(setup["root"], target_is_directory=True)
    store = FileStore(str(setup["root"]), 10000)
    try:
        with pytest.raises(GatewayError):
            store.read("link/customers.csv")
    finally:
        store.close()


def test_symlink_root_denied(setup: dict[str, Any]) -> None:
    link = setup["root"].parent / "link"
    link.symlink_to(setup["root"], target_is_directory=True)
    with pytest.raises(StartupError, match="invalid_data_root"):
        FileStore(str(link), 1000)


@pytest.mark.parametrize(
    "path", ["../private.csv", "/etc/passwd", "x/../private.csv", "x\\secret.csv"]
)
def test_adapter_rejects_unsafe_paths(setup: dict[str, Any], path: str) -> None:
    store = FileStore(str(setup["root"]), 1000)
    try:
        with pytest.raises(GatewayError):
            store.read(path)
    finally:
        store.close()


def test_directory_swap_cannot_redirect_open(
    setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = setup["root"] / "nested"
    directory.mkdir()
    (directory / "data.csv").write_bytes(b"approved")
    outside = setup["root"].parent / "outside"
    outside.mkdir()
    (outside / "data.csv").write_bytes(SECRET.encode())
    store = FileStore(str(setup["root"]), 1000)
    real_open = os.open

    def swap(path: Any, flags: int, **kwargs: Any) -> int:
        fd = real_open(path, flags, **kwargs)
        if path == "nested":
            directory.rename(setup["root"] / "old")
            directory.symlink_to(outside, target_is_directory=True)
        return fd

    monkeypatch.setattr(os, "open", swap)
    try:
        assert store.read("nested/data.csv") == b"approved"
    finally:
        store.close()


def test_changed_source_rejected(setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    store = FileStore(str(setup["root"]), 1000)
    original = os.read
    changed = False

    def change(fd: int, size: int) -> bytes:
        nonlocal changed
        data = original(fd, size)
        if not changed:
            changed = True
            with setup["source"].open("ab") as file:
                file.write(b"extra,private,West,300\n")
        return data

    monkeypatch.setattr(os, "read", change)
    try:
        with pytest.raises(GatewayError, match="source_changed"):
            store.read("customers.csv")
    finally:
        store.close()


def test_root_descriptor_stays_pinned(setup: dict[str, Any]) -> None:
    store = FileStore(str(setup["root"]), 10000)
    expected = setup["source"].read_bytes()
    root: Path = setup["root"]
    root.rename(root.with_name("old-root"))
    root.mkdir()
    (root / "customers.csv").write_bytes(b"replacement")
    try:
        assert store.read("customers.csv") == expected
    finally:
        store.close()
        store.close()
