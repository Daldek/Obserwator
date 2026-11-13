"""
Hydrolog's program: every number of the stored and on-the-fly analyses (ADR-016).

Obserwator computes no statistic itself (Nogat ECO-059): it writes the series
files of a station, runs Hydrolog's catalog calls in a separate process
(``hydrolog commands batch``) and keeps every line of its output as Hydrolog
wrote it. Line ``i`` of the output is the bytes that ``hydrolog <command> …
--json`` prints for call ``i`` alone: the ``hydrolog-result/1`` envelope, or the
``hydrolog-error/1`` document of a call that failed.

The program is the setting ``hydrolog_command`` (``OBSERWATOR_HYDROLOG_COMMAND``,
``[obserwator] hydrolog_command`` of ``nogat.toml``): a command line split as a
shell splits it; without it, ``hydrolog`` found on ``PATH``. No option of a
command chooses it, so REST and MCP never start another program.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from obserwator.config import Settings
from obserwator.exceptions import (
    ObserwatorCancelledError,
    ObserwatorError,
    ObserwatorValidationError,
)
from obserwator.messages import message

__all__ = ["Call", "Deadline", "Hydrolog", "open_hydrolog", "program_words"]

_PROGRAM = "hydrolog"
_RESULT = "hydrolog-result/1"
_ERROR = "hydrolog-error/1"
# ``commands batch`` ends with 0 (every call ok), 10 (some failed) or 11 (all failed);
# its line of every call is written in each case.
_BATCH_EXIT_CODES = frozenset({0, 10, 11})
_POLL_SECONDS = 0.05
# ``config show`` imports Hydrolog once (about 1.5 s); a program that does not
# answer within this time is unusable.
_VERSION_SECONDS = 120.0
_MISSING = "hydrolog_missing"
_FAILED = "hydrolog_failed"


@dataclass(frozen=True)
class Call:
    """One catalog call of Hydrolog: the command name and its options."""

    command: str
    options: Mapping[str, Any]


@dataclass(frozen=True)
class Deadline:
    """The moment (``time.monotonic``) by which a computation must end, and its length."""

    at: float
    seconds: float

    @classmethod
    def after(cls, seconds: float) -> Deadline:
        """The deadline ``seconds`` from now."""
        return cls(time.monotonic() + seconds, seconds)


def _missing(detail: str) -> NoReturn:
    raise ObserwatorError(
        detail,
        code="missing_dependency",
        details={"reason": _MISSING},
        hint=message("analyses.hint_hydrolog_command"),
    )


def _failed(detail: str, **details: object) -> ObserwatorError:
    return ObserwatorError(
        detail, code="source_unavailable", details={"reason": _FAILED, **details}
    )


def _split(line: str) -> list[str]:
    """The words of a command line: POSIX rules, or Windows paths with quotes."""
    if os.name != "nt":
        return shlex.split(line)
    return [
        word[1:-1] if len(word) > 1 and word[0] == word[-1] == '"' else word
        for word in shlex.split(line, posix=False)
    ]


def program_words() -> tuple[str, ...]:
    """
    The command line that starts Hydrolog, read from the settings now.

    Returns
    -------
    tuple of str
        The program found (an absolute path) followed by the other words of
        ``hydrolog_command``; ``("<path>/hydrolog",)`` without the setting.

    Raises
    ------
    ObserwatorError
        Code ``missing_dependency`` (``details.reason`` ``hydrolog_missing``)
        when the setting names no program that can be found or, without the
        setting, ``hydrolog`` is not on ``PATH``.
    ObserwatorValidationError
        If the setting is no command line (an unclosed quote).
    """
    configured = Settings().hydrolog_command
    if configured is None or not configured.strip():
        found = shutil.which(_PROGRAM)
        if found is None:
            _missing(message("analyses.hydrolog_not_installed"))
        return (found,)
    try:
        words = _split(configured)
    except ValueError as exc:
        raise ObserwatorValidationError(
            message("analyses.hydrolog_command_invalid", reason=str(exc)),
            details={"option": "hydrolog_command"},
        ) from exc
    found = shutil.which(words[0]) if words else None
    if found is None:
        _missing(message("analyses.hydrolog_program_not_found"))
    return (found, *words[1:])


def _last_line(data: bytes) -> str:
    lines = [line for line in data.decode("utf-8", "replace").splitlines() if line]
    return lines[-1] if lines else ""


def _error_text(data: bytes) -> str:
    """The message of the ``hydrolog-error/1`` document Hydrolog printed last, else the line."""
    line = _last_line(data)
    try:
        document = json.loads(line)
    except ValueError:
        return line[:500]
    if isinstance(document, dict) and isinstance(document.get("message"), str):
        return str(document["message"])
    return line[:500]


def _envelope(data: bytes) -> dict[str, Any]:
    """Hydrolog's ``--json`` envelope printed on stdout (one JSON line)."""
    try:
        document = json.loads(data)
    except ValueError as exc:
        raise _failed(message("analyses.hydrolog_unreadable", reason=str(exc))) from exc
    if (
        not isinstance(document, dict)
        or document.get("schema") != _RESULT
        or document.get("tool") != _PROGRAM
        or not isinstance(document.get("version"), str)
    ):
        raise _failed(
            message("analyses.hydrolog_unreadable", reason=_last_line(data)[:200])
        )
    return document


@dataclass(frozen=True)
class Hydrolog:
    """
    A Hydrolog program: its command line and, once asked, its version.

    Attributes
    ----------
    words : tuple of str
        The command line that starts it.
    version : str or None
        The version it reported (``config show``); every batch must report
        the same. None accepts the version of the first batch.
    """

    words: tuple[str, ...]
    version: str | None

    def batch(
        self,
        directory: Path,
        name: str,
        calls: Sequence[Call],
        *,
        deadline: Deadline | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> tuple[str, list[bytes]]:
        """
        Run ``calls`` in one Hydrolog process: ``commands batch`` of a JSON Lines file.

        The calls go to ``<directory>/<name>.jsonl``; Hydrolog resolves their
        relative paths against ``directory`` and writes one line per call to
        ``<name>.out.jsonl`` there.

        Parameters
        ----------
        directory : pathlib.Path
            Existing scratch directory of the series files of the calls.
        name : str
            Stem of the files of this batch in ``directory``.
        calls : sequence of Call
            At least one call.
        deadline : Deadline or None, optional
            The process is killed when it runs past it.
        cancel : callable or None, optional
            Polled while the process runs; ``True`` kills it.

        Returns
        -------
        tuple of (str, list of bytes)
            Hydrolog's version and its lines: line ``i`` (with its line feed)
            is Hydrolog's answer to call ``i``.

        Raises
        ------
        ObserwatorCancelledError
            If ``cancel`` returned ``True``.
        ObserwatorError
            Code ``source_unavailable``: ``details.reason`` ``timeout`` past
            the deadline; ``hydrolog_failed`` when the program ended with
            another exit code than the batch's (0, 10, 11), its version
            changed, or its output is not one envelope or error document per
            call.
        """
        script = directory / f"{name}.jsonl"
        output = directory / f"{name}.out.jsonl"
        with script.open("w", encoding="utf-8", newline="\n") as stream:
            for call in calls:
                entry = {"command": call.command, "options": dict(call.options)}
                stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        args = [
            *self.words,
            "commands",
            "batch",
            "--input-file",
            str(script),
            "--output",
            str(output),
            "--json",
        ]
        stdout_path = directory / f"{name}.stdout"
        stderr_path = directory / f"{name}.stderr"
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            code = _wait(
                subprocess.Popen(
                    args,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    cwd=directory,
                ),
                deadline,
                cancel,
            )
        if code not in _BATCH_EXIT_CODES:
            raise _failed(
                message(
                    "analyses.hydrolog_failed",
                    code=code,
                    reason=_error_text(stderr_path.read_bytes()),
                ),
                exit_code=code,
            )
        version = str(_envelope(stdout_path.read_bytes())["version"])
        if self.version is not None and version != self.version:
            raise _failed(
                message(
                    "analyses.hydrolog_version_changed",
                    before=self.version,
                    after=version,
                )
            )
        try:
            lines = output.read_bytes().splitlines(keepends=True)
        except OSError as exc:
            raise _failed(
                message("analyses.hydrolog_unreadable", reason=str(exc))
            ) from exc
        if len(lines) != len(calls):
            raise _failed(
                message(
                    "analyses.hydrolog_line_count",
                    lines=len(lines),
                    calls=len(calls),
                )
            )
        for line in lines:
            try:
                schema = json.loads(line).get("schema")
            except (ValueError, AttributeError):
                schema = None
            if schema not in (_RESULT, _ERROR) or not line.endswith(b"\n"):
                raise _failed(
                    message(
                        "analyses.hydrolog_unreadable",
                        reason=line[:200].decode("utf-8", "replace"),
                    )
                )
        return version, lines


def _wait(
    process: subprocess.Popen[bytes],
    deadline: Deadline | None,
    cancel: Callable[[], bool] | None,
) -> int:
    """The exit code of ``process``; it is killed on cancellation or past the deadline."""
    try:
        while True:
            try:
                return process.wait(timeout=_POLL_SECONDS)
            except subprocess.TimeoutExpired:
                if cancel is not None and cancel():
                    raise ObserwatorCancelledError(
                        message("common.cancelled")
                    ) from None
                if deadline is not None and time.monotonic() >= deadline.at:
                    raise ObserwatorError(
                        message("analyses.hydrolog_timeout", seconds=deadline.seconds),
                        code="source_unavailable",
                        details={"reason": "timeout", "timeout": deadline.seconds},
                    ) from None
    except BaseException:
        process.kill()
        process.wait()
        raise


def open_hydrolog() -> Hydrolog:
    """
    Find Hydrolog's program and ask its version (``hydrolog config show --json``).

    Returns
    -------
    Hydrolog
        The program and its version.

    Raises
    ------
    ObserwatorError
        Code ``missing_dependency`` (``details.reason`` ``hydrolog_missing``)
        without a program; ``source_unavailable`` (``hydrolog_failed``) when
        the program does not answer as Hydrolog does.
    """
    words = program_words()
    try:
        answered = subprocess.run(
            [*words, "config", "show", "--json"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=_VERSION_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise _failed(
            message("analyses.hydrolog_timeout", seconds=_VERSION_SECONDS)
        ) from exc
    except OSError as exc:
        raise _failed(message("analyses.hydrolog_unreadable", reason=str(exc))) from exc
    if answered.returncode != 0:
        raise _failed(
            message(
                "analyses.hydrolog_failed",
                code=answered.returncode,
                reason=_error_text(answered.stderr),
            ),
            exit_code=answered.returncode,
        )
    return Hydrolog(tuple(words), str(_envelope(answered.stdout)["version"]))
