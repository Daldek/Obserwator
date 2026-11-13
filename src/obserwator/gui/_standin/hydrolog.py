"""
Hydrolog's program as O2 runs it: catalog calls in batches, one process per round.

A port of O2's ``obserwator._hydrolog`` (temporary, with the stand-in): the GUI writes
the series files of a station, runs Hydrolog's catalog calls in a separate process
(``hydrolog commands batch``) and keeps every line of its output as Hydrolog wrote it.
Line ``i`` of the output is the bytes that ``hydrolog <command> … --json`` prints for
call ``i`` alone: the ``hydrolog-result/1`` envelope, or the ``hydrolog-error/1``
document of a call that failed. The program is the GUI's setting ``hydrolog_command``
(``OBSERWATOR_HYDROLOG_COMMAND``), already split into words.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from obserwator.exceptions import ObserwatorError
from obserwator.messages import message

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


def _failed(detail: str, **details: object) -> ObserwatorError:
    return ObserwatorError(
        detail,
        code="source_unavailable",
        details={"reason": "hydrolog_failed", **details},
    )


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
        raise _failed(message("gui.errors.hydrolog_failed", reason=str(exc))) from exc
    if (
        not isinstance(document, dict)
        or document.get("schema") != _RESULT
        or document.get("tool") != _PROGRAM
        or not isinstance(document.get("version"), str)
    ):
        raise _failed(
            message("gui.errors.hydrolog_failed", reason=_last_line(data)[:200])
        )
    return document


def _start(args: Sequence[str], **kwargs: Any) -> subprocess.Popen[bytes]:
    """Start the program; one that cannot be started is ``source_unavailable``."""
    try:
        return subprocess.Popen(args, stdin=subprocess.DEVNULL, **kwargs)
    except OSError as exc:
        raise _failed(message("gui.errors.hydrolog_failed", reason=str(exc))) from exc


def _wait(process: subprocess.Popen[bytes], deadline: Deadline | None) -> int:
    """The exit code of ``process``; it is killed past the deadline."""
    try:
        while True:
            try:
                return process.wait(timeout=_POLL_SECONDS)
            except subprocess.TimeoutExpired:
                if deadline is not None and time.monotonic() >= deadline.at:
                    raise ObserwatorError(
                        message(
                            "gui.errors.hydrolog_timeout",
                            seconds=round(deadline.seconds),
                        ),
                        code="source_unavailable",
                        details={"reason": "timeout", "timeout": deadline.seconds},
                    ) from None
    except BaseException:
        process.kill()
        process.wait()
        raise


@dataclass
class Hydrolog:
    """
    A Hydrolog program: its command line and, once asked, its version.

    Attributes
    ----------
    words : tuple of str
        The command line that starts it.
    """

    words: tuple[str, ...]
    _version: str | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def version(self) -> str:
        """
        Hydrolog's version (``hydrolog config show --json``), asked once.

        Raises
        ------
        ObserwatorError
            Code ``source_unavailable`` (``details.reason`` ``hydrolog_failed``) when
            the program cannot be started or does not answer as Hydrolog does.
        """
        with self._lock:
            if self._version is None:
                process = _start(
                    [*self.words, "config", "show", "--json"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                try:
                    out, err = process.communicate(timeout=_VERSION_SECONDS)
                except subprocess.TimeoutExpired as exc:
                    process.kill()
                    process.communicate()
                    raise _failed(
                        message(
                            "gui.errors.hydrolog_timeout",
                            seconds=round(_VERSION_SECONDS),
                        )
                    ) from exc
                if process.returncode != 0:
                    raise _failed(
                        message(
                            "gui.analyses.hydrolog_exit",
                            code=process.returncode,
                            reason=_error_text(err),
                        ),
                        exit_code=process.returncode,
                    )
                self._version = str(_envelope(out)["version"])
            return self._version

    def batch(
        self,
        directory: Path,
        name: str,
        calls: Sequence[Call],
        *,
        deadline: Deadline | None = None,
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

        Returns
        -------
        tuple of (str, list of bytes)
            Hydrolog's version and its lines: line ``i`` (with its line feed)
            is Hydrolog's answer to call ``i``.

        Raises
        ------
        ObserwatorError
            Code ``source_unavailable``: ``details.reason`` ``timeout`` past
            the deadline; ``hydrolog_failed`` when the program cannot be started,
            ends with another exit code than the batch's (0, 10, 11), or its
            output is not one envelope or error document per call.
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
                _start(args, stdout=stdout, stderr=stderr, cwd=directory), deadline
            )
        if code not in _BATCH_EXIT_CODES:
            raise _failed(
                message(
                    "gui.analyses.hydrolog_exit",
                    code=code,
                    reason=_error_text(stderr_path.read_bytes()),
                ),
                exit_code=code,
            )
        version = str(_envelope(stdout_path.read_bytes())["version"])
        try:
            lines = output.read_bytes().splitlines(keepends=True)
        except OSError as exc:
            raise _failed(
                message("gui.errors.hydrolog_failed", reason=str(exc))
            ) from exc
        if len(lines) != len(calls):
            raise _failed(
                message(
                    "gui.analyses.hydrolog_line_count",
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
                        "gui.errors.hydrolog_failed",
                        reason=line[:200].decode("utf-8", "replace"),
                    )
                )
        return version, lines
