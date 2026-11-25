"""
Live checks of Gdańskie Wody's API (``pomiary.gdanskiewody.pl/rest``, ADR-034).

Marked ``live``; the gate leaves them out and ``-m live`` runs them with a key::

    uv run pytest tests/live/test_gdanskiewody_live.py -m live

Skipped without ``OBSERWATOR_GDANSKIE_WODY_API_KEY`` or the file of
``OBSERWATOR_GDANSKIE_WODY_API_KEY_FILE`` (the environment or ``.env``). Three
requests, one at a time and at least the request interval apart (the adapter's pace on
the system clock): the station list, one past day of station 1's rain and one day of
an unknown symbol.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from obserwator._parsing.gdanskiewody import day_points, read_stations
from obserwator.config import provider_key
from obserwator.datasets import get_dataset
from obserwator.exceptions import ObserwatorError, ObserwatorValidationError
from obserwator.fetch import _IDENTIFY
from obserwator.providers.pl import gdanskiewody
from obserwator.providers.pl.gdanskiewody import ADAPTER

pytestmark = pytest.mark.live

MEASUREMENTS = "https://pomiary.gdanskiewody.pl/rest/measurements"
# A past day: closed, so all its 24 hours are labelled.
DAY = datetime.now(UTC).date() - timedelta(days=3)


@pytest.fixture(scope="module")
def client() -> Iterator[httpx.Client]:
    """A client of the provider; every test is skipped without a key."""
    try:
        provider_key("GDANSKIEWODY")
    except ObserwatorError:
        pytest.skip(
            "needs OBSERWATOR_GDANSKIE_WODY_API_KEY or "
            "OBSERWATOR_GDANSKIE_WODY_API_KEY_FILE"
        )
    with httpx.Client(timeout=30.0, headers=_IDENTIFY) as session:
        yield session


def ask(client: httpx.Client, url: str) -> object:
    """One request through the adapter: its key, its pace, its errors."""
    return gdanskiewody._ask(client, url, source=ADAPTER.server_name)


def test_the_station_list_parses(client):
    archive = ADAPTER.station_file(
        get_dataset("pl.gdanskiewody.station_list"), "stations"
    )
    assert archive is not None

    result = ADAPTER.download(archive, client=client, cancel=None)

    stations = {s.number: s for s in read_stations(result.data, filename=result.url)}
    assert all(s.code == f"GDANSKIEWODY-{number}" for number, s in stations.items())
    assert "rain" in stations[1].quantities


def test_a_past_day_of_rain_gives_its_24_hours(client):
    url = f"{MEASUREMENTS}/1/rain/{DAY.isoformat()}"

    points = day_points(ask(client, url), DAY, filename=url)

    start = datetime(DAY.year, DAY.month, DAY.day, 6, tzinfo=UTC)
    assert [moment for moment, _ in points] == [
        start + timedelta(hours=offset) for offset in range(24)
    ]


def test_an_unknown_symbol_is_a_validation_error(client):
    url = f"{MEASUREMENTS}/1/foo/{DAY.isoformat()}"

    with pytest.raises(ObserwatorValidationError) as caught:
        ask(client, url)

    details = caught.value.details
    assert (details["url"], details["provider_code"], details["reason"]) == (
        url,
        -2,
        "bad_request",
    )
