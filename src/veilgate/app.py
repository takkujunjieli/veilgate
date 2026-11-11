"""HTTP adapter with an outer ASGI boundary that sanitizes all errors and audit events."""

import asyncio
import json
import os
import sys
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import Field, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from veilgate.audit import AuditSink
from veilgate.auth import Authenticator
from veilgate.config import Column, Settings, StrictModel, load_settings, load_tokens
from veilgate.errors import GatewayError, StartupError
from veilgate.files import FileStore
from veilgate.gateway import Gateway
from veilgate.policy import Policy


class ToolInput(StrictModel):
    arguments: dict[str, str] = Field(default_factory=dict)


class ReadInput(StrictModel):
    fields: Annotated[list[Column], Field(min_length=1, max_length=100)] | None = None


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def error_response(code: str, status: int) -> Response:
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return Response(
        json.dumps({"error": {"code": code}}),
        status_code=status,
        media_type="application/json",
        headers=headers,
    )


class Boundary:
    """Buffers bounded responses so audit failure cannot follow sensitive-data release."""

    def __init__(
        self, app: ASGIApp, auth: Authenticator, audit: AuditSink, settings: Settings
    ) -> None:
        self.app = app
        self.auth = auth
        self.audit = audit
        self.settings = settings
        self._slots = asyncio.Semaphore(settings.limits.max_concurrent_requests)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        state = scope.setdefault("state", {})
        state.update(principal=None, resource_id=None, tool_id=None, code="ok")
        request_id = uuid.uuid4().hex
        acquired = False
        messages: list[Message] = []
        response_bytes = 0

        async def capture(message: Message) -> None:
            nonlocal response_bytes
            response_bytes += len(message.get("body", b""))
            if response_bytes > self.settings.limits.max_output_bytes + 1024:
                raise GatewayError("output_limit_exceeded", 413)
            messages.append(message)

        try:
            if not (scope["path"] in ("/healthz", "/readyz") and scope["method"] == "GET"):
                state["principal"] = self.auth.authenticate(scope["headers"])
            if scope.get("query_string"):
                raise GatewayError("invalid_request", 400)
            try:
                await asyncio.wait_for(self._slots.acquire(), timeout=0.05)
                acquired = True
            except TimeoutError:
                raise GatewayError("busy", 503) from None
            async with asyncio.timeout(10):
                body = bytearray()
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        raise GatewayError("invalid_request", 400)
                    body.extend(message.get("body", b""))
                    if len(body) > 4096:
                        raise GatewayError("request_too_large", 413)
                    if not message.get("more_body", False):
                        break
                if scope["method"] == "GET" and body:
                    raise GatewayError("invalid_request", 400)
                delivered = False

                async def bounded_receive() -> Message:
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {"type": "http.request", "body": bytes(body), "more_body": False}
                    return {"type": "http.disconnect"}

                await self.app(scope, bounded_receive, capture)
        except Exception as exc:
            messages.clear()
            response_bytes = 0
            if isinstance(exc, GatewayError):
                code, status = exc.code, exc.status
            elif isinstance(exc, TimeoutError):
                code, status = "request_timeout", 504
            else:
                code, status = "internal_error", 500
            state["code"] = code
            await error_response(code, status)(scope, receive, capture)
        finally:
            if acquired:
                self._slots.release()

        status = messages[0]["status"]
        try:
            self.audit.record(
                request_id=request_id,
                principal=state["principal"],
                resource_id=state["resource_id"],
                tool_id=state["tool_id"],
                policy_version=self.settings.policy_version,
                status=status,
                code=state["code"],
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception:
            messages.clear()
            response_bytes = 0
            await error_response("audit_unavailable", 503)(scope, receive, capture)
        for message in messages:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-request-id", request_id.encode("ascii")),
                ]
            await send(message)


def build_app(settings: Settings, audit: AuditSink | None = None) -> Boundary:
    auth = Authenticator(load_tokens(settings))
    policy = Policy(settings)
    store = FileStore(settings.data_root, settings.limits.max_file_bytes)
    try:
        gateway = Gateway(settings, store, policy)
    except Exception:
        store.close()
        raise

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            store.close()

    core = FastAPI(
        title="VeilGate",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
        lifespan=lifespan,
    )

    @core.exception_handler(GatewayError)
    async def gateway_error(request: Request, exc: GatewayError) -> Response:
        request.state.code = exc.code
        return error_response(exc.code, exc.status)

    @core.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> Response:
        request.state.code = "route_unavailable"
        return error_response("route_unavailable", exc.status_code)

    @core.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _: RequestValidationError) -> Response:
        request.state.code = "invalid_request"
        return error_response("invalid_request", 400)

    @core.get("/healthz")
    @core.get("/readyz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @core.post("/v1/resources/{resource_id}/read")
    async def read_resource(resource_id: str, request: Request) -> Response:
        resource = policy.authorize(request.state.principal, resource_id)
        request.state.resource_id = resource.id
        content_types = request.headers.getlist("content-type")
        if (
            len(content_types) != 1
            or content_types[0].split(";", 1)[0].strip() != "application/json"
        ):
            raise GatewayError("unsupported_media_type", 415)
        if request.headers.get("content-encoding", "identity") != "identity":
            raise GatewayError("unsupported_media_type", 415)
        try:
            payload = json.loads(await request.body(), object_pairs_hook=unique_object)
            options = ReadInput.model_validate(payload)
        except (ValueError, ValidationError, RecursionError):
            raise GatewayError("invalid_request", 400) from None
        result = await run_in_threadpool(
            gateway.read_resource, request.state.principal, resource.id, options.fields
        )
        return Response(result, media_type="application/json")

    @core.get("/v1/tools")
    async def list_tools(request: Request) -> Response:
        return Response(
            json.dumps(gateway.discover(request.state.principal)), media_type="application/json"
        )

    @core.post("/v1/tools/{tool_id}/invoke")
    async def invoke_tool(tool_id: str, request: Request) -> Response:
        # Record only a known, authorized tool ID, never arbitrary caller text.
        tool = gateway.tools.get(tool_id)
        if tool is None or request.state.principal not in tool.allowed_principals:
            raise GatewayError("resource_unavailable", 404)
        request.state.tool_id = tool.id
        if (
            len(request.headers.getlist("content-type")) != 1
            or request.headers["content-type"].split(";", 1)[0].strip() != "application/json"
            or request.headers.get("content-encoding", "identity") != "identity"
        ):
            raise GatewayError("unsupported_media_type", 415)
        try:
            payload = json.loads(await request.body(), object_pairs_hook=unique_object)
            options = ToolInput.model_validate(payload)
        except (ValueError, ValidationError, RecursionError):
            raise GatewayError("invalid_request", 400) from None
        result = await run_in_threadpool(
            gateway.invoke, request.state.principal, tool.id, options.arguments
        )
        return Response(result, media_type="application/json")

    return Boundary(core, auth, audit or AuditSink(sys.stdout), settings)


def create_app() -> Boundary:
    config_path = os.environ.get("VEILGATE_CONFIG")
    if not config_path:
        raise StartupError("missing_configuration")
    return build_app(load_settings(Path(config_path)))
