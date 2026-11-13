"""Validate the complete source before releasing any row; reconstruct allowed fields."""

import csv
import io
import json
from typing import Any

from veilgate.config import Limits
from veilgate.errors import GatewayError


def publish_csv(
    raw: bytes,
    fields: tuple[str, ...],
    required_fields: tuple[str, ...],
    resource_id: str,
    policy_version: str,
    limits: Limits,
) -> bytes:
    try:
        text = raw.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("invalid encoding")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader)
        if (
            not header
            or len(header) > limits.max_columns
            or len(header) != len(set(header))
            or any(not field or len(field) > 128 for field in header)
            or any(any(ord(char) < 32 or ord(char) == 127 for char in field) for field in header)
            or not set(required_fields).issubset(header)
        ):
            raise ValueError("invalid schema")
        indexes = [(field, header.index(field)) for field in fields]
        rows: list[dict[str, str]] = []
        for row in reader:
            if len(row) != len(header):
                raise ValueError("invalid row")
            if len(rows) >= limits.max_rows:
                raise GatewayError("source_limit_exceeded", 413)
            rows.append({field: row[index] for field, index in indexes})
        result: dict[str, Any] = {
            "resource_id": resource_id,
            "policy_version": policy_version,
            "fields": list(fields),
            "rows": rows,
        }
        encoded = json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        if len(encoded) > limits.max_output_bytes:
            raise GatewayError("output_limit_exceeded", 413)
        return encoded
    except (UnicodeError, ValueError, csv.Error, StopIteration):
        raise GatewayError("invalid_source", 422) from None
