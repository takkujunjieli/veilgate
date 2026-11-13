"""External demo agent: only Gateway HTTP tools, no resource access or upstream credentials.

Uses the Responses function calling protocol. All outbound model bodies are recorded
before transmission. Run in a separate environment without protected data mounts.
"""

import argparse
import http.client
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

Json = dict[str, Any]


def exchange(url: str, token: str, body: bytes | None) -> Json:
    target = urlsplit(url)
    if target.scheme == "https":
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            target.hostname or "", target.port, timeout=60
        )
    elif target.scheme == "http" and target.hostname in ("127.0.0.1", "localhost", "veilgate"):
        connection = http.client.HTTPConnection(target.hostname, target.port, timeout=15)
    else:
        raise ValueError("HTTPS required outside the local demo network")
    try:
        connection.request(
            "POST" if body is not None else "GET",
            target.path or "/",
            body=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise RuntimeError("response too large")
        if response.status != 200:
            # Never forward transport errors or provider response bodies to the model/log.
            raise RuntimeError(f"remote request failed: HTTP {response.status}")
        value: Json = json.loads(raw)
        return value
    finally:
        connection.close()


def run_agent(
    model: str,
    task: str,
    gateway: Callable[[str, Json | None], Json],
    complete: Callable[[Json], Json],
) -> Json:
    catalog = gateway("/v1/tools", None)["tools"]
    tools = [
        {
            "type": "function",
            "name": t["id"],
            "description": t["description"],
            "parameters": t["input_schema"],
            "strict": True,
        }
        for t in catalog
    ]
    names = {t["id"] for t in catalog}
    history: list[Json] = [{"role": "user", "content": task}]
    for _ in range(8):
        response = complete(
            {
                "model": model,
                "input": history,
                "tools": tools,
                "store": False,
                "max_output_tokens": 2000,
            }
        )
        output = response["output"]
        history.extend(output)
        calls = [item for item in output if item["type"] == "function_call"]
        if not calls:
            if not any(item["type"] == "message" for item in output):
                raise RuntimeError("model returned neither calls nor final message")
            return response
        for call in calls:
            if call["name"] not in names:
                result: Json = {"error": {"code": "unknown_tool"}}
            else:
                try:
                    arguments = json.loads(call["arguments"])
                    result = gateway(f"/v1/tools/{call['name']}/invoke", {"arguments": arguments})
                except (ValueError, RuntimeError):
                    result = {"error": {"code": "tool_unavailable"}}
            history.append(
                {
                    "type": "function_call_output",
                    "call_id": call["call_id"],
                    "output": json.dumps(result),
                }
            )
    raise RuntimeError("model call budget exhausted")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", default="http://127.0.0.1:8000")
    parser.add_argument("--model", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--trace", type=Path, required=True)
    args = parser.parse_args()
    key = os.environ["OPENAI_API_KEY"]
    gateway_token = os.environ["VEILGATE_AGENT_TOKEN"]
    # Fail on existing file; private, append-only for this process's request recording.
    fd = os.open(args.trace, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as trace:

        def complete(body: Json) -> Json:
            wire = json.dumps(body).encode()
            trace.write(wire.decode() + "\n")
            trace.flush()
            os.fsync(trace.fileno())
            return exchange("https://api.openai.com/v1/responses", key, wire)

        def gateway(path: str, body: Json | None) -> Json:
            return exchange(
                args.gateway.rstrip("/") + path,
                gateway_token,
                json.dumps(body).encode() if body is not None else None,
            )

        result = run_agent(args.model, args.task, gateway, complete)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
