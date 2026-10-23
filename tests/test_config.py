from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from veilgate.app import create_app
from veilgate.config import Settings, load_settings, load_tokens
from veilgate.errors import StartupError

from .conftest import TOKEN


@pytest.mark.parametrize(
    "path",
    ["../x.csv", "/x.csv", "x/../y.csv", "x//y.csv", "./x.csv", "a.json", "x\\y.csv", "a\x00.csv"],
)
def test_config_paths_fail_closed(setup: dict[str, Any], path: str) -> None:
    setup["config"]["resources"][0]["path"] = path
    with pytest.raises(ValidationError):
        Settings.model_validate(setup["config"])


def test_unknown_config_keys_rejected(setup: dict[str, Any]) -> None:
    setup["config"]["resources"][0]["publish_fields"] = ["email"]
    with pytest.raises(ValidationError):
        Settings.model_validate(setup["config"])


@pytest.mark.parametrize(
    "change", ["principal", "resource", "fields", "unknown", "env", "version", "limit"]
)
def test_configuration_invariants(setup: dict[str, Any], change: str) -> None:
    config = setup["config"]
    if change == "principal":
        config["principals"].append(config["principals"][0])
    elif change == "resource":
        config["resources"].append(config["resources"][0])
    elif change == "fields":
        config["resources"][0]["published_fields"] = ["email", "email"]
    elif change == "unknown":
        config["resources"][0]["allowed_principals"] = ["mallory"]
    elif change == "env":
        config["principals"][1]["token_env"] = "TEST_TOKEN"
    elif change == "version":
        config["schema_version"] = 2
    elif change == "limit":
        config["limits"] = {"max_rows": "100"}
    with pytest.raises(ValidationError):
        Settings.model_validate(config)


@pytest.mark.parametrize("token", ["short", "", "x" * 257, "x" * 40 + "\n", "é" * 40])
def test_credentials_fail_closed(
    setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    monkeypatch.setenv("TEST_TOKEN", token)
    with pytest.raises(StartupError, match="invalid_credentials"):
        load_tokens(Settings.model_validate(setup["config"]))


def test_duplicate_tokens_rejected(setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTHER_TOKEN", TOKEN)
    with pytest.raises(StartupError):
        load_tokens(Settings.model_validate(setup["config"]))


@pytest.mark.parametrize(
    "content", ["broken =", "secret = 'do-not-disclose'", "x" * 262145, "data_root = 42"]
)
def test_load_errors_redacted(tmp_path: Path, content: str) -> None:
    path = tmp_path / "secret-location.toml"
    path.write_text(content)
    with pytest.raises(StartupError) as exc:
        load_settings(path)
    assert str(exc.value) == "invalid_configuration"


def test_example_and_factory(setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VEILGATE_DATA_ROOT", str(setup["root"]))
    monkeypatch.setenv("VEILGATE_CONFIG", "examples/policy.toml")
    monkeypatch.setenv("VEILGATE_DEMO_TOKEN", TOKEN)
    settings = load_settings(Path("examples/policy.toml"))
    assert settings.data_root == str(setup["root"])
    from starlette.testclient import TestClient

    with TestClient(create_app()) as client:
        assert client.get("/readyz").status_code == 200


def test_missing_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VEILGATE_CONFIG", raising=False)
    with pytest.raises(StartupError, match="missing_configuration"):
        create_app()
