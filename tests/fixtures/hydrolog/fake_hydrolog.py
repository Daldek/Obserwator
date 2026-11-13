"""
A recorded Hydrolog program for the offline tests of the stored analyses (ADR-016).

It answers the two calls Obserwator makes, as Hydrolog 1.0 does:

- ``config show --json``: the envelope with ``version``;
- ``commands batch --input-file CALLS --output RESULTS --json``: one line per call
  in RESULTS, the recorded answer of the call's command (``answers.json``, real
  Hydrolog answers on the fixture store): its envelope with the call's own
  ``inputs`` (paths absolute against the directory of CALLS) and the attribution
  lines of the series file it read, or the recorded error document; the
  envelope of the batch on stdout and the exit code 0, 10 or 11.

The environment steers it: ``FAKE_HYDROLOG_VERSION`` (the version, else
``1.0.0.dev0``), ``FAKE_HYDROLOG_SLEEP`` (seconds before a batch answers),
``FAKE_HYDROLOG_FAIL`` (a batch ends with exit code 1 and an error document),
``FAKE_HYDROLOG_LOG`` (a file that gets one line per run: its arguments and
calls).
"""

import csv
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
VERSION = os.environ.get("FAKE_HYDROLOG_VERSION", "1.0.0.dev0")
FILES = ("input_file", "half_year_file")


def envelope(command, result, inputs, *, status="ok", notices=(), lines=None):
    document = {
        "schema": "hydrolog-result/1",
        "tool": "hydrolog",
        "version": VERSION,
        "command": command,
        "check": False,
        "status": status,
        "result": result,
    }
    if lines:
        document["attribution"] = lines[0]
        if lines[1]:
            document["terms_notice"] = lines[1]
    document["notices"] = list(notices)
    document["inputs"] = inputs
    return document


def series_lines(path):
    """The attribution and terms lines of an Obserwator series export."""
    attribution, terms = [], []
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            for column, found in (
                ("attribution", attribution),
                ("terms_notice", terms),
            ):
                for line in (row.get(column) or "").split("\n"):
                    if line and line not in found:
                        found.append(line)
    return attribution, terms


def answer(call, base, answers):
    command, options = call["command"], dict(call["options"])
    inputs = {
        key: str((base / value).resolve()) if key in FILES else value
        for key, value in options.items()
    }
    key = command + (f"#{options['index']}" if "index" in options else "")
    recorded = answers.get(key)
    if recorded is None:
        return False, {
            "schema": "hydrolog-error/1",
            "code": "validation_error",
            "title": "Validation error",
            "message": f"No recorded answer of {key}",
            "hint": None,
            "details": {},
            "exit_code": 2,
            "command": command,
        }
    if "error" in recorded:
        return False, {**recorded["error"], "command": command}
    files = [Path(inputs[key]) for key in FILES if key in inputs]
    lines = series_lines(files[0]) if files else None
    return True, envelope(
        command, recorded["result"], inputs, notices=recorded["notices"], lines=lines
    )


def batch(arguments):
    script = Path(arguments[arguments.index("--input-file") + 1])
    output = Path(arguments[arguments.index("--output") + 1])
    calls = [
        json.loads(line) for line in script.read_text(encoding="utf-8").splitlines()
    ]
    log = os.environ.get("FAKE_HYDROLOG_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as stream:
            stream.write(json.dumps({"argv": arguments, "calls": calls}) + "\n")
    if os.environ.get("FAKE_HYDROLOG_SLEEP"):
        time.sleep(float(os.environ["FAKE_HYDROLOG_SLEEP"]))
    if os.environ.get("FAKE_HYDROLOG_FAIL"):
        error = {
            "schema": "hydrolog-error/1",
            "code": "internal_error",
            "title": "Internal error",
            "message": "A recorded failure of the whole program",
            "exit_code": 1,
        }
        print(json.dumps(error), file=sys.stderr)
        return 1
    answers = json.loads((HERE / "answers.json").read_text(encoding="utf-8"))
    results = [answer(call, script.parent, answers) for call in calls]
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for _, document in results:
            stream.write(json.dumps(document, ensure_ascii=False) + "\n")
    failed = [n for n, (ok, _) in enumerate(results, start=1) if not ok]
    status = (
        "ok" if not failed else ("failed" if len(failed) == len(results) else "partial")
    )
    print(
        json.dumps(
            envelope(
                "commands batch",
                {
                    "schema": "hydrolog-commands-batch/1",
                    "n_calls": len(results),
                    "n_ok": len(results) - len(failed),
                    "n_failed": len(failed),
                },
                {"input_file": str(script), "output": str(output)},
                status=status,
            )
        )
    )
    return {"ok": 0, "partial": 10, "failed": 11}[status]


def main(arguments):
    if arguments[:3] == ["config", "show", "--json"]:
        print(json.dumps(envelope("config show", {"schema": "hydrolog-config/1"}, {})))
        return 0
    if arguments[:2] == ["commands", "batch"]:
        return batch(arguments)
    print(
        json.dumps({"schema": "hydrolog-error/1", "code": "validation_error"}),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
