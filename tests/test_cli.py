from typing import Any

import pytest

from veilgate import cli
from veilgate.errors import StartupError


def test_cli_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    app = object()
    calls: list[Any] = []
    monkeypatch.setattr("sys.argv", ["veilgate"])
    monkeypatch.setattr(cli, "create_app", lambda: app)
    monkeypatch.setattr(cli.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    cli.main()
    args, kwargs = calls[0]
    assert args == (app,)
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["access_log"] is False
    assert kwargs["proxy_headers"] is False


def test_startup_error_is_sanitized(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    def fail() -> None:
        raise StartupError("invalid_configuration")

    monkeypatch.setattr("sys.argv", ["veilgate"])
    monkeypatch.setattr(cli, "create_app", fail)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    assert capsys.readouterr().err == "VeilGate startup failed: invalid_configuration\n"
