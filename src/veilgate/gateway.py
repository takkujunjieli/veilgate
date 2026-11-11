"""Shared tool boundary. Adapters return private records; only the publisher releases data."""

import csv
import hashlib
import http.client
import io
import json
import os
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from veilgate.config import Settings, Tool
from veilgate.errors import GatewayError, StartupError
from veilgate.files import FileStore
from veilgate.policy import Policy
from veilgate.publisher import publish_csv


def fetch_api(tool: Tool, credential: str | None, limit: int) -> bytes:
    """Fixed operator-owned HTTPS target. No redirects, proxies, or model-owned URL/header."""
    target = urlsplit(tool.endpoint or "")
    connection = http.client.HTTPSConnection(target.hostname or "", target.port, timeout=5)
    headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
    if credential is not None:
        headers["Authorization"] = f"Bearer {credential}"
    try:
        path = target.path or "/"
        if target.query:
            path += "?" + target.query
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        if (
            response.status != 200
            or response.getheader("Content-Type", "").split(";", 1)[0] != "application/json"
            or response.getheader("Content-Encoding", "identity") != "identity"
        ):
            raise GatewayError("source_unavailable", 422)
        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise GatewayError("source_limit_exceeded", 413)
        return raw
    except (OSError, ValueError, http.client.HTTPException):
        raise GatewayError("source_unavailable", 422) from None
    finally:
        connection.close()


def descend(value: Any, path: list[str]) -> Any:
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ValueError("missing field")
        value = value[key]
    return value


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


class Gateway:
    def __init__(self, settings: Settings, store: FileStore, policy: Policy) -> None:
        self.settings = settings
        self.store = store
        self.policy = policy
        self.tools = {tool.id: tool for tool in settings.tools}
        self._credentials: dict[str, str] = {}
        for tool in settings.tools:
            if tool.credential_env is not None:
                value = os.environ.get(tool.credential_env, "")
                if not value or any(ord(c) < 33 or ord(c) > 126 for c in value):
                    raise StartupError("invalid_upstream_credentials")
                self._credentials[tool.id] = value

    def discover(self, principal: str) -> dict[str, Any]:
        return {
            "policy_version": self.policy.version,
            "tools": [
                {
                    "id": t.id,
                    "description": t.description,
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            name: {"type": "string", "enum": values}
                            for name, values in t.arguments.items()
                        },
                        "required": list(t.arguments),
                        "additionalProperties": False,
                    },
                }
                for t in self.tools.values()
                if principal in t.allowed_principals
            ],
        }

    def read_resource(self, principal: str, resource_id: str, requested: list[str] | None) -> bytes:
        resource = self.policy.authorize(principal, resource_id)
        fields = self.policy.fields(resource, requested)
        return publish_csv(
            self.store.read(resource.path),
            fields,
            tuple(resource.published_fields),
            resource.id,
            self.policy.version,
            self.settings.limits,
        )

    def invoke(self, principal: str, tool_id: str, arguments: dict[str, str]) -> bytes:
        tool = self.tools.get(tool_id)
        if tool is None or principal not in tool.allowed_principals:
            raise GatewayError("resource_unavailable", 404)
        if set(arguments) != set(tool.arguments) or any(
            value not in tool.arguments[name] for name, value in arguments.items()
        ):
            raise GatewayError("arguments_not_allowed", 403)
        try:
            rows = self._read(tool)
            rows = [
                row
                for row in rows
                if all(
                    descend(row, [column]) == arguments[name]
                    for name, column in tool.argument_filters.items()
                )
            ]
            if tool.adapter == "csv_aggregate":
                rows = self._aggregate(tool, rows)
            # Reconstruct, never mutate and forward the upstream response.
            released = []
            for row in rows:
                output = {}
                for field in tool.published_fields:
                    value = descend(row, tool.field_paths.get(field, [field]))
                    if not isinstance(value, (str, int, bool)) and value is not None:
                        raise ValueError("only approved scalar values may be released")
                    output[field] = value
                released.append(output)
            result = {
                "tool_id": tool.id,
                "policy_version": self.policy.version,
                "rows": released,
            }
            if tool.snapshot_sha256:
                result["snapshot_id"] = tool.snapshot_sha256
            encoded = json.dumps(result, ensure_ascii=True, allow_nan=False).encode()
            if len(encoded) > self.settings.limits.max_output_bytes:
                raise GatewayError("output_limit_exceeded", 413)
            return encoded
        except (
            ValueError,
            TypeError,
            KeyError,
            UnicodeError,
            csv.Error,
            InvalidOperation,
            RecursionError,
        ):
            raise GatewayError("invalid_source", 422) from None

    def _read(self, tool: Tool) -> list[dict[str, Any]]:
        limits = self.settings.limits
        if tool.adapter == "api_read":
            raw = fetch_api(tool, self._credentials.get(tool.id), limits.max_file_bytes)
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
            rows = descend(data, tool.records_path)
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("invalid records")
        else:
            raw = self.store.read(tool.path or "")
            if tool.snapshot_sha256 and hashlib.sha256(raw).hexdigest() != tool.snapshot_sha256:
                raise GatewayError("source_changed", 409)
            text = raw.decode("utf-8-sig")
            if "\x00" in text:
                raise ValueError("invalid encoding")
            reader = csv.reader(io.StringIO(text, newline=""), strict=True)
            header = next(reader, [])
            if (
                not header
                or len(header) != len(set(header))
                or len(header) > limits.max_columns
                or any(not h for h in header)
            ):
                raise ValueError("invalid header")
            rows = []
            for values in reader:
                if len(values) != len(header):
                    raise ValueError("invalid row")
                rows.append(dict(zip(header, values, strict=True)))
                if len(rows) > limits.max_rows:
                    raise GatewayError("source_limit_exceeded", 413)
        if len(rows) > limits.max_rows:
            raise GatewayError("source_limit_exceeded", 413)
        return rows

    def _aggregate(self, tool: Tool, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[str, tuple[int, Decimal]] = {}
        for row in rows:
            group = row[tool.group_by or ""]
            amount = Decimal(row[tool.sum_field or ""])
            if not isinstance(group, str) or not group or not amount.is_finite():
                raise ValueError("invalid aggregate input")
            # Bound decimal arithmetic and avoid silent precision rounding.
            if amount.as_tuple().exponent not in (0, -1, -2) or abs(amount) > 10**12:
                raise ValueError("invalid amount")
            count, total = groups.get(group, (0, Decimal(0)))
            groups[group] = count + 1, total + amount
        if any(count < tool.min_group_rows for count, _ in groups.values()):
            raise GatewayError("release_denied", 403)
        return [
            {"group": group, "count": count, "total": format(total, ".2f")}
            for group, (count, total) in sorted(groups.items())
        ]
