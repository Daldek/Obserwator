"""``obserwator config show``: the settings in force and where each comes from (DEV-18.6)."""

from typing import Any

import typer

from obserwator.cli._dispatch import _LANG, ObserwatorCommand, ObserwatorSubgroup, _json
from obserwator.config import environment_report
from obserwator.messages import localize, message

app = typer.Typer(help=message("cli.config_help", lang=_LANG), cls=ObserwatorSubgroup)


def _origin(entry: dict[str, Any]) -> str:
    if entry["source"] == "default":
        return message("cli.config_default", lang=_LANG)
    return f"{entry['source']} {entry['name']}"


def _render(report: dict[str, Any]) -> str:
    """Human-readable form of the report, in the language of the CLI."""
    file = report["config_file"]
    if file["error"] is not None:
        state = f"{message('cli.config_file_error', lang=_LANG)}: {file['error']}"
    else:
        state = message(
            "cli.config_file_exists" if file["exists"] else "cli.config_file_absent",
            lang=_LANG,
        )
    lines: list[str] = [
        message("cli.config_file_line", lang=_LANG, path=file["path"], state=state),
        message("cli.config_settings_title", lang=_LANG),
    ]
    for key, entry in report["keys"].items():
        lines.append(f"  {key} = {_json(entry['value'])}  [{_origin(entry)}]")
    lines.append(message("cli.config_credentials_title", lang=_LANG))
    for name, state in report["credentials"].items():
        shown = message(
            "cli.config_credential_present"
            if state == "present"
            else "cli.config_credential_missing",
            lang=_LANG,
        )
        lines.append(f"  {name}: {shown}")
    # The data root and the raw root (ADR-017 D5), each with its source and size.
    for key, unset, line in (
        ("store", "cli.config_store_unset", "cli.config_store"),
        ("raw_store", "cli.config_raw_store_unset", "cli.config_raw_store"),
    ):
        store = report[key]
        if store["root"] is None:
            lines.append(message(unset, lang=_LANG))
            continue
        size = store["size_bytes"]
        lines.append(
            message(
                line,
                lang=_LANG,
                root=store["root"],
                origin=_origin(store),
                size=(
                    message("cli.config_store_no_directory", lang=_LANG)
                    if size is None
                    else f"{size} B"
                ),
            )
        )
    # The instance's section (ADR-025) and what keeps a server from starting or warns.
    instance = report.get("instance")
    if instance is None:
        lines.append(message("cli.config_instance_none", lang=_LANG))
    else:
        lines.append(message("cli.config_instance_title", lang=_LANG))
        for key, value in instance.items():
            lines.append(f"  {key} = {_json(value)}")
    # The captures (ADR-030 D5, D7): the spool and each source's publication state.
    capture = report.get("capture")
    if capture is not None:
        lines.append(
            message("cli.config_capture_title", lang=_LANG, spool=capture["spool"])
        )
        for key, entry in capture["sources"].items():
            lines.append(f"  {key} = {entry['state']}  [{_origin(entry)}]")
    # The provider files (ADR-033): each file and the provider it adds.
    files = report.get("provider_files") or []
    if files:
        lines.append(message("cli.config_provider_files_title", lang=_LANG))
        for entry in files:
            provider = entry["provider"] or message(
                "cli.config_provider_file_unused", lang=_LANG
            )
            lines.append(f"  {entry['path']} = {provider}")
    problems = report.get("problems") or []
    if not problems:
        lines.append(message("cli.config_no_problems", lang=_LANG))
    else:
        lines.append(message("cli.config_problems_title", lang=_LANG))
        for problem in problems:
            text = localize(problem["message"], _LANG)
            lines.append(f"  [{problem['code']}] {problem['option']}: {text}")
    return "\n".join(lines)


@app.command(
    "show", cls=ObserwatorCommand, help=message("cli.config_show_help", lang=_LANG)
)
def show(
    as_json: bool = typer.Option(
        False,
        "--json",
        help=message("cli.config_json_help", lang=_LANG),
    ),
) -> None:
    """Show the settings in force (``obserwator-config/1`` with ``--json``)."""
    report = environment_report()
    typer.echo(_json(report) if as_json else _render(report))
