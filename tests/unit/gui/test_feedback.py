"""„Zgłoś uwagę”: ``POST api/feedback`` and ``feedback.jsonl`` (Nogat DEV-15.12)."""

from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from obserwator.gui._feedback import BODY_MAX_BYTES, Feedback, post_feedback

IP = "203.0.113.77"
STATION = "150160180"
SAME = {"Sec-Fetch-Site": "same-origin"}
REPORT = {
    "message": "  The chart shows no data for May.  ",
    "context": {
        "view": "stations",
        "station": STATION,
        "parameters": {"dataset": "pl.imgw.hydro_daily", "year": 2024, "raw": True},
    },
}


class Ticks:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class Root:
    def snapshot(self):
        return SimpleNamespace(features={STATION: SimpleNamespace(properties={})})


def make_app(path, ticks=None) -> Starlette:
    app = Starlette(routes=[Route("/api/feedback", post_feedback, methods=["POST"])])
    feedback = Feedback(path, monotonic=ticks or Ticks())
    app.state.gui = SimpleNamespace(root=Root(), feedback=feedback, version="3.1.0")
    return app


def client_of(app, address: str = IP) -> TestClient:
    return TestClient(app, client=(address, 4321))


@pytest.fixture
def path(tmp_path):
    return tmp_path / "state" / "feedback.jsonl"


@pytest.fixture
def client(path):
    return client_of(make_app(path))


def post(client, body=REPORT, headers=SAME, **kwargs):
    content = body if isinstance(body, bytes) else json.dumps(body).encode()
    return client.post(
        "/api/feedback",
        content=content,
        headers={"Content-Type": "application/json", **headers},
        **kwargs,
    )


def stored(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_report_is_stored_as_one_line_with_the_servers_context(client, path):
    before = datetime.now(UTC).replace(microsecond=0)

    answer = post(client, headers={**SAME, "User-Agent": "Firefox/140"})

    assert answer.status_code == 200
    assert answer.json() == {"id": 1, "status": "ok"}
    (report,) = stored(path)
    assert list(report) == ["id", "created_at", "message", "context", "is_read"]
    assert report["id"] == 1
    created = datetime.fromisoformat(report["created_at"])
    assert report["created_at"].endswith("+00:00")
    assert before <= created <= datetime.now(UTC) + timedelta(seconds=1)
    assert report["message"] == "The chart shows no data for May."
    assert report["context"] == {
        "view": "stations",
        "station": STATION,
        "parameters": {"dataset": "pl.imgw.hydro_daily", "year": 2024, "raw": True},
        "app_version": "3.1.0",
    }
    assert report["is_read"] is False
    text = path.read_bytes()
    assert IP.encode() not in text and b"Firefox" not in text
    if os.name != "nt":  # Windows has no permission bits
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_a_report_without_a_station_stores_null_and_empty_parameters(client, path):
    answer = post(client, {"message": "Hello", "context": {"view": "pmaxtp"}})

    assert answer.status_code == 200
    assert stored(path)[0]["context"] == {
        "view": "pmaxtp",
        "station": None,
        "parameters": {},
        "app_version": "3.1.0",
    }


def test_ids_ascend_across_instances_from_the_largest_in_the_file(path):
    first = client_of(make_app(path))
    ids = [post(first).json()["id"], post(first).json()["id"]]
    second = client_of(make_app(path), "198.51.100.1")
    ids.append(post(second).json()["id"])
    with path.open("a", encoding="utf-8") as file:
        file.write('{"id": 41, "message": "kept"}\nnot json\n')
    ids.append(post(second).json()["id"])

    assert ids == [1, 2, 3, 42]
    last = path.read_text(encoding="utf-8").splitlines()[-1]
    assert json.loads(last)["id"] == 42


@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Sec-Fetch-Site": "cross-site", "Origin": "http://testserver"},
        {"Origin": "https://evil.example"},
        {},
    ],
)
def test_another_site_is_forbidden(client, path, headers):
    answer = post(client, headers=headers)

    assert answer.status_code == 403
    assert answer.json()["code"] == "forbidden"
    assert not path.exists()


def test_the_pages_origin_is_accepted_without_sec_fetch_site(client):
    assert post(client, headers={"Origin": "http://testserver"}).status_code == 200


def test_another_media_type_is_refused(client, path):
    answer = client.post(
        "/api/feedback",
        content=json.dumps(REPORT),
        headers={**SAME, "Content-Type": "text/plain"},
    )

    assert answer.status_code == 400
    assert answer.json()["code"] == "validation_error"
    assert answer.json()["details"]["reason"] == "content_type"
    assert not path.exists()


def _padded(size: int) -> bytes:
    body = json.dumps({"message": "x", "context": {"view": "current"}}).encode()
    return body + b" " * (size - len(body))


def test_a_body_of_112_kib_is_read_and_one_byte_more_is_413(client):
    accepted = post(client, _padded(BODY_MAX_BYTES))
    refused = post(client, _padded(BODY_MAX_BYTES + 1))

    assert accepted.status_code == 200
    assert refused.status_code == 413
    assert refused.json()["code"] == "validation_error"
    assert refused.json()["details"]["reason"] == "too_large"


def test_a_chunked_body_over_the_limit_is_413(client):
    def chunks():
        for _ in range(8):
            yield b" " * (BODY_MAX_BYTES // 4)

    answer = client.post(
        "/api/feedback",
        content=chunks(),
        headers={**SAME, "Content-Type": "application/json"},
    )

    assert answer.status_code == 413


def _report(message="Hello", **context):
    return {"message": message, "context": {"view": "stations", **context}}


@pytest.mark.parametrize(
    "body",
    [
        b"{not json",
        b'{"message": "x", "context": {"view": "current", "parameters": {"a": NaN}}}',
        b"[]",
        {"message": "x"},
        {"message": "x", "context": {"view": "current"}, "email": "a@b.c"},
        {"context": {"view": "current"}},
        _report(""),
        _report("   \n\t "),
        _report(7),
        _report("x" * 5001),
        {"message": "x", "context": []},
        {"message": "x", "context": {"view": "current", "address": "/x"}},
        {"message": "x", "context": {"view": "station"}},
        {"message": "x", "context": {}},
        _report(station="000000000"),
        _report(station=150160180),
        _report(station=""),
        _report(parameters=["a"]),
        _report(parameters={"a": {"b": 1}}),
        _report(parameters={"a": [1]}),
        _report(parameters={f"p{i}": i for i in range(51)}),
        _report(parameters={"long": "x" * 100_000}),
    ],
)
def test_an_invalid_report_is_refused_and_not_stored(client, path, body):
    answer = post(client, body)

    assert answer.status_code == 400
    assert answer.json()["code"] == "validation_error"
    assert not path.exists()


@pytest.mark.parametrize(
    "body",
    [
        _report("  " + "x" * 5000 + "\n"),
        _report(station=None),
        _report(parameters={f"p{i}": None for i in range(50)}),
        _report(parameters={"long": "x" * 99_000}),
    ],
)
def test_a_report_at_the_boundaries_is_accepted(client, body):
    assert post(client, body).status_code == 200


def test_the_answer_speaks_the_readers_language(client):
    polish = post(client, _report(""))
    english = post(client, _report(""), headers={**SAME, "Accept-Language": "en"})

    assert polish.json()["message"] != english.json()["message"]
    assert english.json()["message"] == "The description must not be empty."


def test_five_reports_per_address_in_ten_minutes(path):
    ticks = Ticks()
    app = make_app(path, ticks)
    client = client_of(app)

    accepted = [post(client).status_code for _ in range(5)]
    ticks.now += 120
    refused = post(client)
    other = post(client_of(app, "198.51.100.1"))
    ticks.now += 480  # ten minutes after the first report
    again = post(client)

    assert accepted == [200] * 5
    assert refused.status_code == 429
    assert refused.headers["Retry-After"] == "480"
    assert refused.json()["code"] == "rate_limited"
    assert refused.json()["details"] == {"retry_after": 480}
    assert other.status_code == 200
    assert again.status_code == 200
    assert len(stored(path)) == 7


def test_an_invalid_report_does_not_use_the_limit(path):
    client = client_of(make_app(path))

    for _ in range(10):
        post(client, _report(""))

    assert post(client).status_code == 200


def test_a_file_that_cannot_be_written_is_an_io_error(tmp_path):
    (tmp_path / "state").write_text("not a directory", encoding="utf-8")
    client = client_of(make_app(tmp_path / "state" / "feedback.jsonl"))

    answer = post(client)

    assert answer.status_code == 500
    assert answer.json()["code"] == "io_error"
    assert str(tmp_path) not in answer.text
