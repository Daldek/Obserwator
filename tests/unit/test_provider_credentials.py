"""Provider API keys (Nogat plan 2026-11-20, P3, P4): settings, config show, errors."""

import dataclasses
import json
import logging
import os
import sys
from pathlib import Path

import platformdirs
import pytest
from typer.testing import CliRunner

from obserwator import fetch as fetch_module
from obserwator.cli import main as cli_main
from obserwator.config import (
    credential_error,
    credential_keys,
    environment_report,
    provider_key,
)
from obserwator.datasets import ProviderCredential, get_provider, providers
from obserwator.exceptions import ObserwatorError

RUNNER = CliRunner()
KEY = "k3y-of-the-test-provider-0123456789abcdef"
VARIABLE = "OBSERWATOR_TEST_PROVIDER_API_KEY"
FILE_VARIABLE = "OBSERWATOR_TEST_PROVIDER_API_KEY_FILE"


@pytest.fixture(autouse=True)
def user_environment(tmp_path, monkeypatch):
    """No OBSERWATOR_/NOGAT_ variable, ``.env`` or user ``nogat.toml`` of the machine."""
    for name in list(os.environ):
        if name.startswith(("OBSERWATOR_", "NOGAT_")):
            monkeypatch.delenv(name)
    home = tmp_path / "home"
    monkeypatch.setattr(
        platformdirs, "user_config_path", lambda *a, **k: home / "config"
    )
    monkeypatch.setattr(platformdirs, "user_data_path", lambda *a, **k: home / "data")
    monkeypatch.setattr(platformdirs, "user_cache_path", lambda *a, **k: home / "cache")
    monkeypatch.setattr(platformdirs, "user_state_path", lambda *a, **k: home / "state")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)


@pytest.fixture
def test_provider(monkeypatch):
    """A provider declaring a credential, appended to the registry (none of 3.2.0 does)."""
    registry = sys.modules["obserwator.datasets"]
    provider = dataclasses.replace(
        get_provider("CHMU"),
        id="TESTP",
        short_name="Test provider",
        key_prefix="xx.testp",
        datasets=(),
        credential=ProviderCredential("TEST_PROVIDER"),
    )
    monkeypatch.setattr(registry, "_PROVIDERS", (*providers(), provider))
    monkeypatch.setattr(
        registry,
        "_PROVIDER_BY_NAME",
        {**registry._PROVIDER_BY_NAME, "TESTP": provider, "xx.testp": provider},
    )
    return provider


def key_file(tmp_path: Path, mode: int) -> Path:
    path = tmp_path / "secrets" / "test-provider.key"
    path.parent.mkdir(exist_ok=True)
    path.write_text(KEY + "\n", encoding="utf-8")
    path.chmod(mode)
    return path


def test_the_credential_names_its_two_variables():
    credential = ProviderCredential("GDANSKIE_WODY")

    assert credential.variable == "OBSERWATOR_GDANSKIE_WODY_API_KEY"
    assert credential.file_variable == "OBSERWATOR_GDANSKIE_WODY_API_KEY_FILE"
    for stem in ("gdanskie_wody", "GDANSKIE__WODY", "_X", "X_", "Ś"):
        with pytest.raises(ValueError):
            ProviderCredential(stem)


def test_no_provider_of_the_registry_needs_a_key_and_its_document_is_unchanged():
    assert all(provider.credential is None for provider in providers())
    report = environment_report()
    assert not any(
        "_API_KEY" in name and "ADMIN" not in name for name in report["credentials"]
    )

    result = RUNNER.invoke(cli_main.app, ["datasets", "providers", "--json"])

    assert result.exit_code == 0, result.output
    assert "credential" not in result.stdout


def test_config_show_reports_the_key_present_or_missing_and_never_its_value(
    tmp_path, monkeypatch, test_provider
):
    config = tmp_path / "nogat.toml"
    config.write_text(
        f'[obserwator]\ntest_provider_api_key = "{KEY}"\n', encoding="utf-8"
    )
    monkeypatch.setenv("NOGAT_CONFIG", str(config))

    missing = json.loads(
        RUNNER.invoke(cli_main.app, ["config", "show", "--json"]).stdout
    )

    # nogat.toml never gives a key: ignored as a credential, and the key stays missing.
    assert (
        missing["credentials"][VARIABLE],
        missing["credentials"][FILE_VARIABLE],
    ) == (
        "missing",
        "missing",
    )
    assert {"key": "test_provider_api_key", "reason": "credential"} in missing[
        "config_file"
    ]["ignored"]
    assert "test_provider_api_key" in credential_keys()
    with pytest.raises(ObserwatorError):
        provider_key("TESTP")

    (Path.cwd() / ".env").write_text(f"{VARIABLE}={KEY}\n", encoding="utf-8")
    from_dotenv = RUNNER.invoke(cli_main.app, ["config", "show", "--json"])
    monkeypatch.setenv(FILE_VARIABLE, str(key_file(tmp_path, 0o600)))
    text = RUNNER.invoke(cli_main.app, ["config", "show"])

    present = json.loads(from_dotenv.stdout)
    assert (
        present["credentials"][VARIABLE],
        present["credentials"][FILE_VARIABLE],
    ) == (
        "present",
        "missing",
    )
    assert provider_key("TESTP") == KEY
    assert VARIABLE in text.stdout and FILE_VARIABLE in text.stdout
    for output in (from_dotenv.stdout, text.stdout, text.stderr):
        assert KEY not in output


def test_a_missing_key_is_forbidden_with_the_reason_provider_and_hint(
    monkeypatch, test_provider
):
    monkeypatch.setenv("OBSERWATOR_LANG", "en")
    monkeypatch.setenv(VARIABLE, "   ")  # blank: no key

    with pytest.raises(ObserwatorError) as caught:
        provider_key("xx.testp")

    error = caught.value
    assert (error.code, dict(error.details)) == (
        "forbidden",
        {"reason": "missing_credentials", "provider": "TESTP"},
    )
    assert VARIABLE in error.hint and FILE_VARIABLE in error.hint

    def needs_the_key(**options):
        provider_key("TESTP")
        return []

    monkeypatch.setattr(fetch_module, "fetch_warnings", needs_the_key)
    result = RUNNER.invoke(cli_main.app, ["current", "warnings", "--json"])

    assert result.exit_code == 12, result.output
    document = json.loads(result.stderr.strip().splitlines()[-1])
    assert document["code"] == "forbidden"
    assert document["details"] == {"reason": "missing_credentials", "provider": "TESTP"}
    assert VARIABLE in document["hint"]


def test_a_rejected_key_is_forbidden_with_invalid_credentials(test_provider):
    error = credential_error("TESTP", "invalid_credentials")

    assert (error.code, dict(error.details)) == (
        "forbidden",
        {"reason": "invalid_credentials", "provider": "TESTP"},
    )
    assert VARIABLE in error.hint
    assert error.localized("pl") != error.localized("en")


def test_the_key_appears_in_no_log_record_envelope_or_sidecar(
    tmp_path, monkeypatch, caplog, test_provider
):
    from obserwator.testing import build_fixture_store

    monkeypatch.setenv(FILE_VARIABLE, str(key_file(tmp_path, 0o600)))
    caplog.set_level(logging.DEBUG)
    used: list[str] = []

    def uses_the_key(**options):
        used.append(provider_key("TESTP"))
        return []

    def rejects_the_key(**options):
        provider_key("TESTP")
        raise credential_error("TESTP", "invalid_credentials")

    monkeypatch.setattr(fetch_module, "fetch_warnings", uses_the_key)
    accepted = RUNNER.invoke(cli_main.app, ["current", "warnings", "--json"])
    monkeypatch.setattr(fetch_module, "fetch_warnings", rejects_the_key)
    rejected = RUNNER.invoke(cli_main.app, ["current", "warnings", "--json"])
    roots = build_fixture_store(tmp_path / "raw", data_root=tmp_path / "data")

    assert used == [KEY]
    assert (accepted.exit_code, rejected.exit_code) == (0, 12)
    assert json.loads(rejected.stderr.strip().splitlines()[-1])["details"] == {
        "reason": "invalid_credentials",
        "provider": "TESTP",
    }
    outputs = [accepted.stdout, accepted.stderr, rejected.stdout, rejected.stderr]
    outputs += [record.getMessage() for record in caplog.records]
    assert all(KEY not in output for output in outputs)
    written = [
        path
        for root in (roots.raw.root, roots.data.root)
        for path in root.rglob("*")
        if path.is_file()
    ]
    assert any(path.name.endswith(".meta.json") for path in written)
    assert all(KEY.encode() not in path.read_bytes() for path in written)


@pytest.mark.skipif(os.name == "nt", reason="no permission bits on Windows")
def test_a_key_file_others_may_read_gives_a_warning(
    tmp_path, monkeypatch, caplog, test_provider
):
    monkeypatch.setenv(FILE_VARIABLE, str(key_file(tmp_path, 0o644)))

    with caplog.at_level(logging.WARNING, logger="obserwator.config"):
        assert provider_key("TESTP") == KEY

    (record,) = [r for r in caplog.records if r.name == "obserwator.config"]
    assert FILE_VARIABLE in record.getMessage() and "0644" in record.getMessage()
    assert KEY not in record.getMessage()
    problems = environment_report()["problems"]
    assert {(p["code"], p["option"]) for p in problems} == {
        ("secret_file_mode", FILE_VARIABLE)
    }

    key_file(tmp_path, 0o600)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="obserwator.config"):
        provider_key("TESTP")
    assert not caplog.records
    assert environment_report()["problems"] == []
