"""
A fake of Hydrolog's program for the tests of the GUI's analyses (run as a script).

It answers ``config show --json`` and ``commands batch --input-file F --output O
--json`` as Hydrolog 1.0.0.dev0 does: one line per call in ``O`` (the envelope or the
error document), the batch's envelope on stdout, exit code 0, 10 or 11. A call is
answered with the envelope recorded in ``hydrolog_recordings.json`` for its command
(and ``parameter`` or ``index``), else with an envelope whose result echoes the call.

Environment:

``FAKE_HYDROLOG_LOG``
    A JSON Lines file: one line per process that ran a batch (``pid``, ``start``,
    ``end``, ``cwd``, ``calls`` with their options and whether their files exist).
``FAKE_HYDROLOG_SLEEP``
    Seconds a batch waits before it answers.
``FAKE_HYDROLOG_EXIT``
    An exit code a batch ends with instead, after printing an error document on
    stderr (a program that fails).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

VERSION = "1.0.0.dev0"
RECORDINGS = json.loads(
    (Path(__file__).with_name("hydrolog_recordings.json")).read_text(encoding="utf-8")
)["answers"]


def _envelope(command: str, result: object) -> dict[str, object]:
    return {
        "schema": "hydrolog-result/1",
        "tool": "hydrolog",
        "version": VERSION,
        "command": command,
        "check": False,
        "status": "ok",
        "result": result,
    }


def _answer(call: dict[str, object], base: Path) -> dict[str, object]:
    command = str(call["command"])
    options = dict(call["options"])  # type: ignore[call-overload]
    variant = options.get("parameter") or options.get("index")
    recorded = RECORDINGS.get(f"{command}|{variant}") or RECORDINGS.get(command)
    files = {
        name: str((base / str(value)).resolve())
        for name, value in options.items()
        if name.endswith("_file")
    }
    if recorded is not None:
        answer = dict(recorded)
        if answer["schema"] == "hydrolog-result/1":
            answer["inputs"] = {**options, **files}
        return answer
    return {
        **_envelope(command, {"schema": "fake-result/1", "options": options}),
        "attribution": [],
        "terms_notice": [],
        "notices": [],
        "inputs": {**options, **files},
    }


def _batch(arguments: list[str]) -> int:
    start = time.time()
    script = Path(arguments[arguments.index("--input-file") + 1])
    output = Path(arguments[arguments.index("--output") + 1])
    calls = [
        json.loads(line) for line in script.read_text(encoding="utf-8").splitlines()
    ]
    time.sleep(float(os.environ.get("FAKE_HYDROLOG_SLEEP") or 0))
    failure = os.environ.get("FAKE_HYDROLOG_EXIT")
    if failure:
        error = {
            "schema": "hydrolog-error/1",
            "code": "internal_error",
            "message": "the fake program fails",
        }
        print(json.dumps(error), file=sys.stderr)
        return int(failure)
    base = script.parent
    answers = [_answer(call, base) for call in calls]
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for answer in answers:
            stream.write(json.dumps(answer, ensure_ascii=False) + "\n")
    failed = sum(answer["schema"] != "hydrolog-result/1" for answer in answers)
    log = os.environ.get("FAKE_HYDROLOG_LOG")
    if log:
        entry = {
            "pid": os.getpid(),
            "start": start,
            "end": time.time(),
            "cwd": os.getcwd(),
            "calls": [
                {
                    "command": call["command"],
                    "options": call["options"],
                    "files": {
                        name: (base / str(value)).is_file()
                        for name, value in call["options"].items()
                        if name.endswith("_file")
                    },
                }
                for call in calls
            ],
        }
        with open(log, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry) + "\n")
    print(
        json.dumps(
            _envelope(
                "commands batch",
                {
                    "n_calls": len(calls),
                    "n_ok": len(calls) - failed,
                    "n_failed": failed,
                },
            )
        )
    )
    if not failed:
        return 0
    return 11 if failed == len(calls) else 10


def main(arguments: list[str]) -> int:
    """Answer one invocation of the program."""
    if arguments[:2] == ["config", "show"]:
        print(json.dumps(_envelope("config show", {"settings": []})))
        return 0
    if arguments[:2] == ["commands", "batch"]:
        return _batch(arguments)
    print(f"fake hydrolog: unknown call {arguments}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
