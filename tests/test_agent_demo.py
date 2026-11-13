"""Protocol test with a simulated model; not real-agent acceptance evidence."""

import json
import runpy
from typing import Any


def test_agent_keeps_only_gateway_results_in_model_history() -> None:
    run_agent = runpy.run_path("scripts/agent_demo.py")["run_agent"]
    requests = []
    invocations = []

    def gateway(path: str, body: Any) -> dict[str, Any]:
        if path == "/v1/tools":
            return {
                "tools": [
                    {
                        "id": "report",
                        "description": "Approved report",
                        "input_schema": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                            "additionalProperties": False,
                        },
                    }
                ]
            }
        invocations.append((path, body))
        return {"rows": [{"group": "East", "count": 2, "total": "250.00"}]}

    def complete(body: Any) -> dict[str, Any]:
        requests.append(json.loads(json.dumps(body)))
        if len(requests) == 1:
            return {
                "output": [
                    {
                        "type": "function_call",
                        "name": "report",
                        "arguments": "{}",
                        "call_id": "call1",
                    }
                ]
            }
        return {"output": [{"type": "message", "content": "East: 250.00"}]}

    run_agent("test-model", "Compare regions", gateway, complete)
    assert len(requests) == 2
    assert invocations == [("/v1/tools/report/invoke", {"arguments": {}})]
    assert requests[1]["input"][-1]["type"] == "function_call_output"
    assert "250.00" in json.dumps(requests[1])
    assert "Authorization" not in json.dumps(requests)
