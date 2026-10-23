"""A deliberately small audit schema: never accept raw request or source objects."""

import json
import threading
from datetime import UTC, datetime
from typing import TextIO


class AuditSink:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._lock = threading.Lock()

    def record(
        self,
        *,
        request_id: str,
        principal: str | None,
        resource_id: str | None,
        policy_version: str,
        status: int,
        code: str,
        duration_ms: int,
    ) -> None:
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": "gateway_request",
            "request_id": request_id,
            "principal": principal,
            "resource_id": resource_id,
            "policy_version": policy_version,
            "status": status,
            "code": code,
            "duration_ms": duration_ms,
        }
        with self._lock:
            self._stream.write(json.dumps(event, separators=(",", ":")) + "\n")
            self._stream.flush()
