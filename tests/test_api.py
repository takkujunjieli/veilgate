import asyncio
import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from starlette.testclient import TestClient

from veilgate.app import Boundary, build_app
from veilgate.audit import AuditSink
from veilgate.auth import Authenticator
from veilgate.config import Settings
from veilgate.files import FileStore

from .conftest import OTHER_TOKEN, SECRET, TOKEN

URL = "/v1/resources/customers/read"


def test_allowlisted_output(client: TestClient, setup: dict[str, Any]) -> None:
    response = client.post(URL, json={})
    assert response.status_code == 200
    assert response.json() == {
        "resource_id": "customers",
        "policy_version": "test-v1",
        "fields": ["region", "amount"],
        "rows": [{"region": "East", "amount": "100"}, {"region": "West", "amount": "200"}],
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    event = json.loads(setup["log"].getvalue())
    assert event["request_id"] == response.headers["x-request-id"]
    assert event["principal"] == "alice"
    assert event["code"] == "ok"
    for value in [SECRET, TOKEN, "private@example.com", str(setup["root"]), "East", "100"]:
        assert value not in setup["log"].getvalue()
    assert SECRET not in response.text


def test_select_subset(client: TestClient) -> None:
    response = client.post(URL, json={"fields": ["amount"]})
    assert response.status_code == 200
    assert response.json()["rows"] == [{"amount": "100"}, {"amount": "200"}]


@pytest.mark.parametrize("fields", [["email"], ["region", "name"], ["region", "region"]])
def test_forbidden_fields(client: TestClient, fields: list[str]) -> None:
    assert client.post(URL, json={"fields": fields}).status_code == 403


@pytest.mark.parametrize(
    "payload",
    [
        {"fields": []},
        {"fields": "region"},
        {"fields": [1]},
        {"role": "admin"},
        {"principal": "alice"},
        {"path": "/etc/passwd"},
        {"operation": "execute"},
        [],
        None,
    ],
)
def test_strict_body(client: TestClient, payload: Any) -> None:
    response = client.post(
        URL, content=json.dumps(payload), headers={"content-type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json() == {"error": {"code": "invalid_request"}}


@pytest.mark.parametrize(
    "body", [b'{"fields": [], "fields": ["region"]}', b'{"secret":', b"\xff", b"[" * 2000]
)
def test_malformed_body(client: TestClient, body: bytes) -> None:
    assert (
        client.post(URL, content=body, headers={"content-type": "application/json"}).status_code
        == 400
    )


def test_bounded_request_even_without_content_length(client: TestClient) -> None:
    response = client.post(URL, content=iter([b"x" * 3000, b"x" * 3000]))
    assert response.status_code == 413


def test_content_type_and_encoding(client: TestClient) -> None:
    assert client.post(URL, content="{}").status_code == 415
    assert client.post(URL, json={}, headers={"content-encoding": "gzip"}).status_code == 415


@pytest.mark.parametrize(
    "credential", [None, "Bearer wrong", f"Basic {TOKEN}", "Bearer " + "x" * 1000]
)
def test_authentication(client: TestClient, credential: str | None) -> None:
    client.headers.pop("Authorization")
    headers = {"Authorization": credential} if credential is not None else {}
    response = client.post(URL, json={}, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_duplicate_auth_headers_rejected(client: TestClient) -> None:
    response = client.post(
        URL,
        json={},
        headers=[("Authorization", f"Bearer {TOKEN}"), ("Authorization", f"Bearer {TOKEN}")],
    )
    assert response.status_code == 401


def test_auth_before_parsing(client: TestClient) -> None:
    response = client.post(URL, content=SECRET, headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


def test_resource_existence_hidden_and_identity_not_spoofable(client: TestClient) -> None:
    denied = client.post(
        URL, json={"principal": "alice"}, headers={"Authorization": f"Bearer {OTHER_TOKEN}"}
    )
    unknown = client.post("/v1/resources/missing/read", json={})
    assert denied.status_code == unknown.status_code == 404
    assert denied.json() == unknown.json()


def test_unknown_fields_never_auto_published(client: TestClient, setup: dict[str, Any]) -> None:
    setup["source"].write_text(f"region,amount,new_secret\nEast,100,{SECRET}\n")
    response = client.post(URL, json={})
    assert response.status_code == 200
    assert response.json()["rows"] == [{"region": "East", "amount": "100"}]


@pytest.mark.parametrize(
    "path", ["/v1/resources/%2e%2e%2fsecret/read", "/docs", "/openapi.json", "/" + SECRET]
)
def test_unknown_paths_are_sanitized(client: TestClient, setup: dict[str, Any], path: str) -> None:
    response = client.post(path, json={})
    assert response.status_code == 404
    assert SECRET not in response.text + setup["log"].getvalue()


def test_query_parameters_rejected_and_not_logged(
    client: TestClient, setup: dict[str, Any]
) -> None:
    response = client.post(URL + "?token=" + SECRET, json={})
    assert response.status_code == 400
    assert SECRET not in response.text + setup["log"].getvalue()


def test_health_and_method_contract(client: TestClient) -> None:
    client.headers.pop("Authorization")
    for path in ("/healthz", "/readyz"):
        assert client.get(path).json() == {"status": "ok"}
    assert client.request("GET", "/healthz", content="body").status_code == 400
    assert client.post("/healthz", json={}).status_code == 401
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    assert client.get(URL).status_code == 405


def test_unexpected_error_has_no_sensitive_trace(
    client: TestClient, setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    def fail(*_: Any) -> bytes:
        raise RuntimeError(f"{SECRET} {setup['root']}")

    monkeypatch.setattr(FileStore, "read", fail)
    response = client.post(URL, json={})
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "internal_error"}}
    captured = capsys.readouterr()
    assert SECRET not in response.text + setup["log"].getvalue() + captured.out + captured.err


def test_audit_failure_prevents_data_release(setup: dict[str, Any]) -> None:
    class BrokenSink(AuditSink):
        def record(self, **kwargs: Any) -> None:
            raise OSError(SECRET)

    app = build_app(Settings.model_validate(setup["config"]), BrokenSink(io.StringIO()))
    with TestClient(app) as client:
        response = client.post(URL, json={}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 503
    assert "East" not in response.text
    assert SECRET not in response.text


def test_saturation_fails_closed(setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    setup["config"]["limits"] = {"max_concurrent_requests": 1}
    started, release = threading.Event(), threading.Event()
    original = FileStore.read

    def slow(store: FileStore, path: str) -> bytes:
        started.set()
        assert release.wait(timeout=5)
        return original(store, path)

    monkeypatch.setattr(FileStore, "read", slow)
    app = build_app(Settings.model_validate(setup["config"]), AuditSink(setup["log"]))
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        client.headers["Authorization"] = f"Bearer {TOKEN}"
        pending = pool.submit(client.post, URL, json={})
        try:
            assert started.wait(timeout=5)
            assert client.post(URL, json={}).status_code == 503
        finally:
            release.set()
        assert pending.result().status_code == 200


def test_boundary_disconnect_and_timeout(setup: dict[str, Any]) -> None:
    async def unused(*_: Any) -> None:
        raise AssertionError("must not reach app")

    for error in (None, TimeoutError()):
        messages: list[Any] = []

        async def receive(error: Exception | None = error) -> Any:
            if error is not None:
                raise error
            return {"type": "http.disconnect"}

        async def send(message: Any, messages: list[Any] = messages) -> None:
            messages.append(message)

        app = Boundary(
            unused,
            Authenticator({"alice": TOKEN}),
            AuditSink(setup["log"]),
            Settings.model_validate(setup["config"]),
        )
        scope = {
            "type": "http",
            "path": URL,
            "method": "POST",
            "headers": [(b"authorization", f"Bearer {TOKEN}".encode())],
        }
        asyncio.run(app(scope, receive, send))
        assert messages[0]["status"] == (504 if error else 400)
