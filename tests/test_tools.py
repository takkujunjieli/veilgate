import hashlib
import io
import json
from typing import Any

import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from veilgate import gateway as module
from veilgate.app import build_app
from veilgate.audit import AuditSink
from veilgate.config import Settings, Tool
from veilgate.errors import GatewayError

from .conftest import OTHER_TOKEN, SECRET, TOKEN


def configured(setup: dict[str, Any], adapter: str = "csv_read") -> dict[str, Any]:
    tool = {
        "id": "report",
        "description": "Approved report",
        "adapter": adapter,
        "allowed_principals": ["alice"],
        "published_fields": ["region", "amount"],
        "path": "customers.csv",
    }
    if adapter == "csv_aggregate":
        tool.update(
            published_fields=["group", "count", "total"],
            group_by="region",
            sum_field="amount",
            snapshot_sha256=hashlib.sha256(setup["source"].read_bytes()).hexdigest(),
        )
    elif adapter == "api_read":
        del tool["path"]
        tool.update(
            endpoint="https://orders.example.test/orders",
            records_path=["data"],
            published_fields=["id", "status"],
            field_paths={"status": ["shipping", "status"]},
        )
    setup["config"]["tools"] = [tool]
    return tool


def client_for(setup: dict[str, Any]) -> TestClient:
    client = TestClient(
        build_app(Settings.model_validate(setup["config"]), AuditSink(setup["log"]))
    )
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    return client


def test_discovery_and_shared_authorization(setup: dict[str, Any]) -> None:
    tool = configured(setup)
    tool["arguments"] = {"region": ["East", "West"]}
    tool["argument_filters"] = {"region": "region"}
    with client_for(setup) as client:
        listed = client.get("/v1/tools")
        assert "path" not in listed.text and SECRET not in listed.text
        assert listed.json()["tools"][0]["input_schema"]["properties"]["region"]["enum"] == [
            "East",
            "West",
        ]
        result = client.post("/v1/tools/report/invoke", json={"arguments": {"region": "East"}})
        assert result.json()["rows"] == [{"region": "East", "amount": "100"}]
        assert SECRET not in result.text
        client.headers["Authorization"] = f"Bearer {OTHER_TOKEN}"
        assert client.get("/v1/tools").json()["tools"] == []
        assert client.post("/v1/tools/report/invoke", json={}).status_code == 404
    events = [json.loads(line) for line in setup["log"].getvalue().splitlines()]
    assert any(e["tool_id"] == "report" for e in events)
    assert SECRET not in setup["log"].getvalue()


@pytest.mark.parametrize(
    "arguments", [{}, {"region": "secret"}, {"region": "East", "role": "admin"}]
)
def test_invalid_arguments_never_read_source(
    setup: dict[str, Any], arguments: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = configured(setup)
    tool["arguments"] = {"region": ["East"]}

    def forbidden(*args: Any) -> Any:
        pytest.fail("adapter must not run")

    monkeypatch.setattr(module.Gateway, "_read", forbidden)
    with client_for(setup) as client:
        response = client.post("/v1/tools/report/invoke", json={"arguments": arguments})
        assert response.status_code == 403


def test_two_agents_and_second_resource_reuse_policy(setup: dict[str, Any]) -> None:
    tool = configured(setup)
    tool["allowed_principals"] = ["alice", "bob"]
    setup["config"]["tools"].append({**tool, "id": "second"})
    with client_for(setup) as client:
        first = client.post("/v1/tools/report/invoke", json={}).json()["rows"]
        client.headers["Authorization"] = f"Bearer {OTHER_TOKEN}"
        assert client.post("/v1/tools/second/invoke", json={}).json()["rows"] == first
    setup["config"]["policy_version"] = "test-v2"
    for registered in setup["config"]["tools"]:
        registered["published_fields"] = ["region"]
    with client_for(setup) as client:
        for token in (TOKEN, OTHER_TOKEN):
            client.headers["Authorization"] = f"Bearer {token}"
            result = client.post("/v1/tools/report/invoke", json={}).json()
            assert result["policy_version"] == "test-v2"
            assert all(set(row) == {"region"} for row in result["rows"])


def test_aggregate_snapshot_and_whole_report_denial(setup: dict[str, Any]) -> None:
    configured(setup, "csv_aggregate")
    with client_for(setup) as client:
        result = client.post("/v1/tools/report/invoke", json={})
        assert result.json()["rows"] == [
            {"group": "East", "count": 1, "total": "100.00"},
            {"group": "West", "count": 1, "total": "200.00"},
        ]
        assert SECRET not in result.text
        assert client.post("/v1/tools/report/invoke", json={}).content == result.content
        setup["source"].write_text("region,amount\nEast,999\n")
        assert client.post("/v1/tools/report/invoke", json={}).status_code == 409
    # The final group fails after an earlier eligible group was computed.
    setup["source"].write_text("region,amount\nEast,10\nEast,20\nWest,99\n")
    configured(setup, "csv_aggregate")["min_group_rows"] = 2
    with client_for(setup) as client:
        result = client.post("/v1/tools/report/invoke", json={})
        assert result.status_code == 403
        assert result.json() == {"error": {"code": "release_denied"}}
        assert "East" not in result.text and "30" not in result.text


@pytest.mark.parametrize("value", ["NaN", "Infinity", "0.001", "1000000000001", "bad"])
def test_invalid_aggregate_rejected(setup: dict[str, Any], value: str) -> None:
    setup["source"].write_text(f"region,amount\nEast,{value}\n")
    configured(setup, "csv_aggregate")
    with client_for(setup) as client:
        assert client.post("/v1/tools/report/invoke", json={}).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"data": [{"id": "o1", "shipping": {"status": "pending"}, "secret": SECRET}]},
        {
            "data": [{"id": "o1", "shipping": {"status": "pending", "notes": SECRET}}],
            "debug": SECRET,
        },
    ],
)
def test_nested_api_reconstruction(
    setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    configured(setup, "api_read")
    monkeypatch.setattr(module, "fetch_api", lambda *args: json.dumps(payload).encode())
    with client_for(setup) as client:
        result = client.post("/v1/tools/report/invoke", json={})
        assert result.json()["rows"] == [{"id": "o1", "status": "pending"}]
        assert SECRET not in result.text


@pytest.mark.parametrize(
    "raw",
    [
        b'{"data": [], "data": []}',
        b'{"data": {}}',
        json.dumps({"data": [{"id": "o1", "shipping": {"status": {"secret": SECRET}}}]}).encode(),
        json.dumps({"error": SECRET}).encode(),
        b"invalid json",
    ],
)
def test_api_invalid_sources_safe_failure(
    setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch, raw: bytes
) -> None:
    configured(setup, "api_read")
    monkeypatch.setattr(module, "fetch_api", lambda *args: raw)
    with client_for(setup) as client:
        result = client.post("/v1/tools/report/invoke", json={})
        assert result.status_code == 422
        assert SECRET not in result.text + setup["log"].getvalue()


@pytest.mark.parametrize(
    "endpoint", ["http://example.test", "https://u:p@example.test", "/x", "https://x/#fragment"]
)
def test_api_config_rejects_unsafe_targets(setup: dict[str, Any], endpoint: str) -> None:
    configured(setup, "api_read")["endpoint"] = endpoint
    with pytest.raises(ValidationError):
        Settings.model_validate(setup["config"])


@pytest.mark.parametrize(
    "status,kind,encoding,body,code",
    [
        (302, "application/json", "identity", b"secret", "source_unavailable"),
        (500, "application/json", "identity", b"secret", "source_unavailable"),
        (200, "text/html", "identity", b"secret", "source_unavailable"),
        (200, "application/json", "gzip", b"secret", "source_unavailable"),
        (200, "application/json", "identity", b"123456", "source_limit_exceeded"),
    ],
)
def test_https_boundary(
    monkeypatch: pytest.MonkeyPatch, status: int, kind: str, encoding: str, body: bytes, code: str
) -> None:
    response = io.BytesIO(body)
    response.status = status  # type: ignore[attr-defined]
    response.getheader = lambda k, default: {  # type: ignore[attr-defined]
        "Content-Type": kind,
        "Content-Encoding": encoding,
    }.get(k, default)

    class Connection:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def request(self, *args: Any, **kwargs: Any) -> None:
            assert args[0] == "GET"

        def getresponse(self) -> Any:
            return response

        def close(self) -> None:
            pass

    monkeypatch.setattr(module.http.client, "HTTPSConnection", Connection)
    tool = Tool(
        id="api",
        description="test",
        adapter="api_read",
        allowed_principals=["alice"],
        published_fields=["id"],
        endpoint="https://example.test/data",
    )
    with pytest.raises(GatewayError) as exc:
        module.fetch_api(tool, None, 5)
    assert exc.value.code == code
