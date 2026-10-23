"""Supported entry point: safe startup failures and disabled HTTP access logs."""

import argparse
import sys

import uvicorn

from veilgate.app import create_app
from veilgate.errors import StartupError


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the VeilGate private-resource gateway")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    try:
        app = create_app()
    except StartupError as exc:
        print(f"VeilGate startup failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        access_log=False,
        proxy_headers=False,
        server_header=False,
        timeout_keep_alive=5,
        limit_concurrency=64,
    )


if __name__ == "__main__":
    main()
