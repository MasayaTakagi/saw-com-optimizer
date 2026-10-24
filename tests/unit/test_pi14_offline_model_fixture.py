from __future__ import annotations

import json
import os
import socket
import stat
from pathlib import Path
from urllib.parse import urlsplit

import pytest

# This is an inert contract fixture, not a model/provider supported by Pi or SAWOpt.
PROVIDER_ID = "sawopt-pi14-offline-test-only"
MODEL_ID = "sawopt-pi14-dummy-model"
DUMMY_KEY = "SAWOPT_PI14_DUMMY_NOT_A_SECRET"
LOCAL_ENDPOINT = "http://127.0.0.1:9/v1"
API_FAMILY = "openai-completions"


class UnsafeFixture(ValueError):
    """The fake-only model profile does not match the reviewed safety contract."""


def _config(*, provider_id: str = PROVIDER_ID, model_id: str = MODEL_ID, api_key: str = DUMMY_KEY, base_url: str = LOCAL_ENDPOINT) -> dict[str, object]:
    return {
        "providers": {
            provider_id: {
                "name": "Pi 1.4.0 static preflight dummy",
                "baseUrl": base_url,
                "api": API_FAMILY,
                "apiKey": api_key,
                "models": [{"id": model_id, "name": "Offline dummy model"}],
            }
        }
    }


def _write_private_profile(profile: Path, content: object | str | None = None) -> Path:
    profile.mkdir(mode=0o700)
    profile.chmod(0o700)
    path = profile / "models.json"
    if content is None:
        content = _config()
    if isinstance(content, str):
        encoded = content.encode("utf-8")
    else:
        encoded = json.dumps(content, sort_keys=True).encode("utf-8")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(encoded)
            stream.flush()
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def _select_fake_model(
    profile: Path,
    models_path: Path,
    *,
    network_isolated: bool,
) -> dict[str, str | bool]:
    """Model a narrow checklist; this is deliberately not Pi's JSON/auth parser."""
    if not network_isolated:
        raise UnsafeFixture("offline route isolation is a required external precondition")
    if profile.is_symlink() or not profile.is_dir():
        raise UnsafeFixture("expected a real private profile directory")
    if stat.S_IMODE(profile.stat().st_mode) != 0o700:
        raise UnsafeFixture("profile permissions must be 0700")
    expected_path = profile / "models.json"
    if models_path != expected_path:
        raise UnsafeFixture("models.json must be directly inside the expected profile")
    if models_path.is_symlink() or not models_path.is_file():
        raise UnsafeFixture("models.json must be a regular non-symlink file")
    if stat.S_IMODE(models_path.stat().st_mode) != 0o600:
        raise UnsafeFixture("models.json permissions must be 0600")

    try:
        config = json.loads(models_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UnsafeFixture("models.json is missing or malformed") from exc
    if not isinstance(config, dict) or set(config) != {"providers"}:
        raise UnsafeFixture("unexpected top-level config shape")
    providers = config["providers"]
    if not isinstance(providers, dict) or set(providers) != {PROVIDER_ID}:
        raise UnsafeFixture("only the fictitious test provider is allowed")
    provider = providers[PROVIDER_ID]
    if not isinstance(provider, dict) or set(provider) != {"name", "baseUrl", "api", "apiKey", "models"}:
        raise UnsafeFixture("unexpected provider fields")
    if provider["api"] != API_FAMILY:
        raise UnsafeFixture("unexpected API family")
    endpoint = urlsplit(provider["baseUrl"] if isinstance(provider["baseUrl"], str) else "")
    if (
        endpoint.scheme != "http"
        or endpoint.hostname != "127.0.0.1"
        or endpoint.port != 9
        or endpoint.path != "/v1"
        or endpoint.username is not None
        or endpoint.password is not None
        or endpoint.query
        or endpoint.fragment
    ):
        raise UnsafeFixture("only the reviewed loopback endpoint is allowed")
    key = provider["apiKey"]
    if not isinstance(key, str) or key != DUMMY_KEY or "$" in key or key.startswith("!"):
        raise UnsafeFixture("only the exact literal non-secret dummy key is allowed")
    models = provider["models"]
    if not isinstance(models, list) or len(models) != 1:
        raise UnsafeFixture("exactly one dummy model is required")
    model = models[0]
    if not isinstance(model, dict) or set(model) != {"id", "name"} or model["id"] != MODEL_ID:
        raise UnsafeFixture("only the exact fictitious model is allowed")

    # This status is intentionally not called authenticated: Pi's configured-key
    # predicate can mark any nonempty literal as configured without validating it.
    return {
        "provider_id": PROVIDER_ID,
        "model_id": MODEL_ID,
        "credential_source": "test-only literal; not authenticated",
        "model_request_sent": False,
    }


def test_private_fixture_selects_only_dummy_model_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = tmp_path / "private-profile"
    models_path = _write_private_profile(profile)

    def forbidden_network(*_args, **_kwargs):
        raise AssertionError("the fake resolver must not open a network socket")

    monkeypatch.setattr(socket, "socket", forbidden_network)
    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    selected = _select_fake_model(profile, models_path, network_isolated=True)

    assert selected == {
        "provider_id": PROVIDER_ID,
        "model_id": MODEL_ID,
        "credential_source": "test-only literal; not authenticated",
        "model_request_sent": False,
    }
    assert stat.S_IMODE(profile.stat().st_mode) == 0o700
    assert stat.S_IMODE(models_path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "content",
    [
        "{not-json",
        {},
        {"providers": {}},
        {"providers": {PROVIDER_ID: {"api": API_FAMILY}}},
        {"providers": {PROVIDER_ID: {**_config()["providers"][PROVIDER_ID], "models": []}}},
    ],
)
def test_missing_malformed_or_model_less_configuration_fails_closed(tmp_path: Path, content: object) -> None:
    profile = tmp_path / "private-profile"
    path = _write_private_profile(profile, content)
    with pytest.raises(UnsafeFixture):
        _select_fake_model(profile, path, network_isolated=True)


def test_absent_models_json_fails_closed(tmp_path: Path) -> None:
    profile = tmp_path / "private-profile"
    profile.mkdir(mode=0o700)
    profile.chmod(0o700)
    with pytest.raises(UnsafeFixture):
        _select_fake_model(profile, profile / "models.json", network_isolated=True)


@pytest.mark.parametrize("key", ["$OPENAI_API_KEY", "${OPENAI_API_KEY}", "!printf unsafe"])
def test_env_interpolation_and_command_credentials_are_rejected(tmp_path: Path, key: str) -> None:
    profile = tmp_path / "private-profile"
    path = _write_private_profile(profile, _config(api_key=key))
    with pytest.raises(UnsafeFixture):
        _select_fake_model(profile, path, network_isolated=True)


@pytest.mark.parametrize(
    ("provider_id", "model_id", "base_url"),
    [
        ("openai", MODEL_ID, LOCAL_ENDPOINT),
        (PROVIDER_ID, "gpt-4o", LOCAL_ENDPOINT),
        (PROVIDER_ID, MODEL_ID, "https://api.openai.com/v1"),
        (PROVIDER_ID, MODEL_ID, "http://localhost:9/v1"),
        (PROVIDER_ID, MODEL_ID, "http://127.0.0.1:10/v1"),
    ],
)
def test_real_identity_or_non_reviewed_endpoint_is_rejected(
    tmp_path: Path, provider_id: str, model_id: str, base_url: str
) -> None:
    profile = tmp_path / "private-profile"
    path = _write_private_profile(profile, _config(provider_id=provider_id, model_id=model_id, base_url=base_url))
    with pytest.raises(UnsafeFixture):
        _select_fake_model(profile, path, network_isolated=True)


def test_environment_key_is_not_a_fallback_for_missing_literal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "TEST_ONLY_NOT_A_CREDENTIAL")
    config = _config()
    provider = config["providers"][PROVIDER_ID]
    assert isinstance(provider, dict)
    provider.pop("apiKey")
    profile = tmp_path / "private-profile"
    path = _write_private_profile(profile, config)

    with pytest.raises(UnsafeFixture):
        _select_fake_model(profile, path, network_isolated=True)


def test_network_isolation_is_a_hard_precondition(tmp_path: Path) -> None:
    profile = tmp_path / "private-profile"
    path = _write_private_profile(profile)
    with pytest.raises(UnsafeFixture, match="offline route isolation"):
        _select_fake_model(profile, path, network_isolated=False)


def test_wrong_profile_traversal_and_symlinked_model_file_are_rejected(tmp_path: Path) -> None:
    profile = tmp_path / "private-profile"
    path = _write_private_profile(profile)
    other_profile = tmp_path / "other-private-profile"
    other_path = _write_private_profile(other_profile)

    with pytest.raises(UnsafeFixture, match="directly inside"):
        _select_fake_model(profile, other_path, network_isolated=True)
    with pytest.raises(UnsafeFixture, match="directly inside"):
        _select_fake_model(profile, profile / ".." / "other-private-profile" / "models.json", network_isolated=True)

    path.unlink()
    path.symlink_to(other_path)
    with pytest.raises(UnsafeFixture, match="non-symlink"):
        _select_fake_model(profile, path, network_isolated=True)


def test_symlinked_profile_and_insecure_modes_are_rejected(tmp_path: Path) -> None:
    profile = tmp_path / "private-profile"
    path = _write_private_profile(profile)
    profile_alias = tmp_path / "private-profile-alias"
    profile_alias.symlink_to(profile, target_is_directory=True)
    with pytest.raises(UnsafeFixture, match="real private profile"):
        _select_fake_model(profile_alias, profile_alias / "models.json", network_isolated=True)

    profile.chmod(0o755)
    with pytest.raises(UnsafeFixture, match="0700"):
        _select_fake_model(profile, path, network_isolated=True)
    profile.chmod(0o700)
    path.chmod(0o644)
    with pytest.raises(UnsafeFixture, match="0600"):
        _select_fake_model(profile, path, network_isolated=True)
