"""
The hydrological sections „Stany charakterystyczne”, „Krzywa natężenia przepływu” and
„Przepływy maksymalne i minimalne” on a root with long records, computed by Hydrolog's
program (GUI plan S5, D11, D13; Nogat plan H1 to H6, H16).

The page draws the results of the analysis ids of the API (``api/analysis/{code}/{id}``):
the numbers it shows are compared with those documents, a flood quantile with Hydrolog's
own call on the same exported series, and the hand-off of the annual maxima with Nogat's
schema. Kłodzko (IMGW-PIB, 1951–2025, with IMGW-PIB's half-year characteristics) and Děčín
(ČHMÚ, the Labe since 1888, with ČHMÚ's thresholds in its catalog entry).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from obserwator import export_series

pytestmark = pytest.mark.hydrolog

KLODZKO = "150160180"
DECIN = "0-203-1-240000"
WAIT = 120_000
"""How long a section may take: Hydrolog computes every id on request [ms]."""
HANDOFF_SCHEMA = (
    Path(__file__).resolve().parents[2] / "schemas" / "nogat" / "handoff-1.schema.json"
)


def analysis(base: str, code: str, id_: str, **overrides: Any) -> dict[str, Any]:
    """Hydrolog's result of an id as the API serves it to the page."""
    query = urllib.parse.urlencode(overrides)
    url = f"{base}api/analysis/{urllib.parse.quote(code)}/{id_}"
    with urllib.request.urlopen(
        f"{url}?{query}" if query else url, timeout=180
    ) as answer:
        document: dict[str, Any] = json.load(answer)
    assert document["status"] == "ok", document.get("error")
    result: dict[str, Any] = document["envelope"]["result"]
    return result


def number(text: str) -> float:
    """The first number of a Polish text: „1 060,5 m³/s” → 1060.5."""
    found = re.search(r"[−-]?\d[\d\u00a0\u202f ]*(?:,\d+)?", text)
    assert found, text
    plain = re.sub(r"[\u00a0\u202f ]", "", found.group(0))
    return float(plain.replace(",", ".").replace("−", "-"))


def curve(formula: str) -> tuple[float, float, float]:
    """a, H₀ and b of the formula „Q = a · (H − H₀)^b” („H + 0,9” for H₀ = −0,9)."""
    found = re.fullmatch(r"Q = (\S+) · \(H ([−+]) (\S+)\)\^(\S+)", formula.strip())
    assert found, formula
    a, sign, level, b = found.groups()
    return number(a), (number(level) if sign == "−" else -number(level)), number(b)


def figure(card: Any, label: str) -> str:
    """The value of a key figure („Lat”, „Q1% (T = 100)”) of a section."""
    tile = card.locator("dl.figures > div").filter(
        has=card.page.locator("dt", has_text=re.compile(f"^{re.escape(label)}$"))
    )
    text: str = tile.locator("dd").first.inner_text(timeout=WAIT)
    return text


def provenance(card: Any, command: str) -> None:
    """The section names Hydrolog's command that computed its numbers."""
    chip = card.locator(".ana-prov .prov-hydrolog code", has_text=command).first
    chip.wait_for(timeout=WAIT)


def section(open_page: Any, base: str, code: str, name: str, **options: Any) -> Any:
    """The station's panel with one section open; its card."""
    page = open_page(f"?station={code}&section={name}", base=base, **options)
    return page.locator(f'[data-section="{name}"]')


@pytest.mark.parametrize("code", [KLODZKO, DECIN])
def test_each_section_shows_hydrologs_numbers_with_their_provenance(
    open_page: Any, analysis_url: str, code: str
) -> None:
    card = section(open_page, analysis_url, code, "characteristic")
    second = analysis(analysis_url, code, "characteristic.Q")
    highest = card.locator("table.hy-matrix td").filter(
        has=card.page.locator(".hy-name", has_text=re.compile("^WWQ$"))
    )
    assert number(highest.locator("strong").inner_text(timeout=WAIT)) == pytest.approx(
        second["wwx"], abs=0.5
    )
    provenance(card, "stats characteristic")
    levels = analysis(analysis_url, code, "characteristic.H")
    listed = card.locator("ul.hy-levels li", has_text="SWW").inner_text(timeout=WAIT)
    assert number(listed.split(":")[1]) == pytest.approx(levels["swx"], abs=0.5)
    events = analysis(
        analysis_url, code, f"threshold_events.H.{'spa1' if code == DECIN else 'swx'}"
    )
    assert number(figure(card, "Dni poza progiem")) == events["days_beyond"]
    assert number(figure(card, "Próg")) == pytest.approx(events["threshold"], abs=0.5)
    provenance(card, "stats threshold-events")

    card = section(open_page, analysis_url, code, "rating")
    fit = analysis(analysis_url, code, "rating_curve")
    formula = card.locator(".hy-formula").inner_text(timeout=WAIT)
    a, h0, b = curve(formula)
    assert a == pytest.approx(fit["a"], rel=1e-3)
    assert h0 == pytest.approx(fit["h0"], abs=0.05)
    assert b == pytest.approx(fit["b"], abs=5e-4)
    provenance(card, "hydrometrics rating-curve")

    card = section(open_page, analysis_url, code, "extremes")
    flood = analysis(analysis_url, code, "flood_frequency.Q")
    assert number(figure(card, "Lat")) == flood["n_years"]
    best = flood["distributions"][0]
    hundred = best["quantiles"][best["return_periods"].index(100.0)]
    assert number(figure(card, "Q1% (T = 100)")) == pytest.approx(hundred, abs=0.5)
    low = analysis(analysis_url, code, "low_flow.Q")
    assert number(figure(card, "NNQ")) == pytest.approx(
        low["empirical"]["values_ascending"][0], abs=5e-4
    )
    for command in ("stats flood-frequency", "stats homogeneity", "stats low-flow"):
        provenance(card, command)


def test_choosing_the_years_refits_the_rating_curve(
    open_page: Any, analysis_url: str
) -> None:
    card = section(open_page, analysis_url, KLODZKO, "rating")
    formula = card.locator(".hy-formula")
    default = formula.inner_text(timeout=WAIT)
    years = card.locator("form.years").first
    years.locator("input").nth(0).fill("1971")
    years.locator("input").nth(1).fill("1980")
    years.locator("button[type=submit]").click()

    card.page.wait_for_function(
        "([selector, before]) => document.querySelector(selector)?.textContent !== before",
        arg=['[data-section="rating"] .hy-formula', default],
        timeout=WAIT,
    )
    fit = analysis(
        analysis_url, KLODZKO, "rating_curve", first_year=1971, last_year=1980
    )
    a, h0, b = curve(formula.inner_text())
    assert (fit["first_year"], fit["last_year"]) == (1971, 1980)
    assert a == pytest.approx(fit["a"], rel=1e-3)
    assert h0 == pytest.approx(fit["h0"], abs=0.05)
    assert b == pytest.approx(fit["b"], abs=5e-4)
    assert number(figure(card, "Par")) == fit["n_points"]


def test_a_flood_quantile_equals_hydrologs_own_call(
    open_page: Any, analysis_url: str, tmp_path: Path
) -> None:
    card = section(open_page, analysis_url, KLODZKO, "extremes")
    shown = number(figure(card, "Q1% (T = 100)"))

    series = tmp_path / "half_years.csv"
    export_series(
        root=os.environ["OBSERWATOR_GUI_E2E_ROOT"],
        dataset="pl.imgw.hydro_semiannual",
        station=KLODZKO,
        output=series,
    )
    command = [
        *shlex.split(os.environ["OBSERWATOR_HYDROLOG_COMMAND"]),
        "stats",
        "flood-frequency",
        f"--half-year-file={series}",
        "--parameter=Q",
        "--json",
    ]
    done = subprocess.run(
        command, capture_output=True, text=True, check=True, timeout=180
    )
    own = json.loads(done.stdout)["result"]
    best = next(
        item
        for item in own["distributions"]
        if item["distribution_name"] == own["best_distribution"]
    )
    assert shown == pytest.approx(
        best["quantiles"][best["return_periods"].index(100.0)], abs=0.5
    )


def test_the_annual_maxima_hand_off_is_a_valid_nogat_hand_off(
    open_page: Any, analysis_url: str
) -> None:
    card = section(open_page, analysis_url, KLODZKO, "extremes")
    handoff = card.locator(".hy-handoff").first
    handoff.wait_for(timeout=WAIT)
    with card.page.expect_download(timeout=WAIT) as download:
        handoff.locator(".btn-row button").nth(1).click()
    document = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))

    schema = json.loads(HANDOFF_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(document)
    flood = analysis(analysis_url, KLODZKO, "flood_frequency.Q")
    payload = document["payload"]
    assert payload["schema"] == "hydrolog-series/1"
    assert (payload["step"], payload["statistic"]) == ("year", "max")
    assert payload["years"] == flood["hydrological_years"]
    assert payload["values"] == flood["annual_maxima"]
    assert document["result"]["analysis"] == "flood_frequency.Q"
