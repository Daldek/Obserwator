"""Provider API keys (Nogat plan 2026-11-20, P3, P4): settings, config show, errors."""

import json
import logging
import os
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
from obserwator.datasets import ProviderCredential, providers
from obserwator.exceptions import ObserwatorError

RUNNER = CliRunner()
KEY = "k3y-of-gdanskie-wody-0123456789abcdef"
# Gdańskie Wody (ADR-034), the one provider of the registry whose requests need a key.
PROVIDER = "GDANSKIEWODY"
VARIABLE = "OBSERWATOR_GDANSKIE_WODY_API_KEY"
FILE_VARIABLE = "OBSERWATOR_GDANSKIE_WODY_API_KEY_FILE"


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


def key_file(tmp_path: Path, mode: int) -> Path:
    path = tmp_path / "secrets" / "gdanskie-wody.key"
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


def test_only_gdanskie_wody_needs_a_key_and_the_registry_names_its_variables():
    assert {p.id: p.credential for p in providers()} == {
        "IMGW": None,
        "CHMU": None,
        PROVIDER: ProviderCredential("GDANSKIE_WODY"),
    }
    report = environment_report()
    assert [
        name
        for name in report["credentials"]
        if "_API_KEY" in name and "ADMIN" not in name
    ] == [VARIABLE, FILE_VARIABLE]

    result = RUNNER.invoke(cli_main.app, ["datasets", "providers", "--json"])

    assert result.exit_code == 0, result.output
    # A provider without a key has no `credential` field: its document is unchanged.
    credentials = {
        item["id"]: item.get("credential")
        for item in json.loads(result.stdout)["result"]
    }
    assert credentials == {
        "IMGW": None,
        "CHMU": None,
        PROVIDER: {
            "stem": "GDANSKIE_WODY",
            "variable": VARIABLE,
            "file_variable": FILE_VARIABLE,
        },
    }


def test_config_show_reports_the_key_present_or_missing_and_never_its_value(
    tmp_path, monkeypatch
):
    config = tmp_path / "nogat.toml"
    config.write_text(
        f'[obserwator]\ngdanskie_wody_api_key = "{KEY}"\n', encoding="utf-8"
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
    assert {"key": "gdanskie_wody_api_key", "reason": "credential"} in missing[
        "config_file"
    ]["ignored"]
    assert "gdanskie_wody_api_key" in credential_keys()
    with pytest.raises(ObserwatorError):
        provider_key(PROVIDER)

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
    assert provider_key(PROVIDER) == KEY
    assert VARIABLE in text.stdout and FILE_VARIABLE in text.stdout
    for output in (from_dotenv.stdout, text.stdout, text.stderr):
        assert KEY not in output


def test_a_missing_key_is_forbidden_with_the_reason_provider_and_hint(monkeypatch):
    monkeypatch.setenv("OBSERWATOR_LANG", "en")
    monkeypatch.setenv(VARIABLE, "   ")  # blank: no key

    with pytest.raises(ObserwatorError) as caught:
        provider_key("pl.gdanskiewody")

    error = caught.value
    assert (error.code, dict(error.details)) == (
        "forbidden",
        {"reason": "missing_credentials", "provider": PROVIDER},
    )
    assert VARIABLE in error.hint and FILE_VARIABLE in error.hint

    def needs_the_key(**options):
        provider_key(PROVIDER)
        return []

    monkeypatch.setattr(fetch_module, "fetch_warnings", needs_the_key)
    result = RUNNER.invoke(cli_main.app, ["current", "warnings", "--json"])

    assert result.exit_code == 12, result.output
    document = json.loads(result.stderr.strip().splitlines()[-1])
    assert document["code"] == "forbidden"
    assert document["details"] == {
        "reason": "missing_credentials",
        "provider": PROVIDER,
    }
    assert VARIABLE in document["hint"]


def test_a_rejected_key_is_forbidden_with_invalid_credentials():
    error = credential_error(PROVIDER, "invalid_credentials")

    assert (error.code, dict(error.details)) == (
        "forbidden",
        {"reason": "invalid_credentials", "provider": PROVIDER},
    )
    assert VARIABLE in error.hint
    assert error.localized("pl") != error.localized("en")


def test_the_key_appears_in_no_log_record_envelope_or_sidecar(
    tmp_path, monkeypatch, caplog
):
    from obserwator.testing import build_fixture_store

    monkeypatch.setenv(FILE_VARIABLE, str(key_file(tmp_path, 0o600)))
    caplog.set_level(logging.DEBUG)
    used: list[str] = []

    def uses_the_key(**options):
        used.append(provider_key(PROVIDER))
        return []

    def rejects_the_key(**options):
        provider_key(PROVIDER)
        raise credential_error(PROVIDER, "invalid_credentials")

    monkeypatch.setattr(fetch_module, "fetch_warnings", uses_the_key)
    accepted = RUNNER.invoke(cli_main.app, ["current", "warnings", "--json"])
    monkeypatch.setattr(fetch_module, "fetch_warnings", rejects_the_key)
    rejected = RUNNER.invoke(cli_main.app, ["current", "warnings", "--json"])
    roots = build_fixture_store(tmp_path / "raw", data_root=tmp_path / "data")

    assert used == [KEY]
    assert (accepted.exit_code, rejected.exit_code) == (0, 12)
    assert json.loads(rejected.stderr.strip().splitlines()[-1])["details"] == {
        "reason": "invalid_credentials",
        "provider": PROVIDER,
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
def test_a_key_file_others_may_read_gives_a_warning(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv(FILE_VARIABLE, str(key_file(tmp_path, 0o644)))

    with caplog.at_level(logging.WARNING, logger="obserwator.config"):
        assert provider_key(PROVIDER) == KEY

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
        provider_key(PROVIDER)
    assert not caplog.records
    assert environment_report()["problems"] == []
