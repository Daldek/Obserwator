"""
The hydrological sections „Niżówki”, „Czas trwania i strefy”, „Reżim i sezonowość”,
„Temperatura wody” and „Trendy i bilans” on a root with long records, computed by
Hydrolog's program (GUI plan S5, D11, D13; Nogat plan H7 to H18).

The page draws the results of the analysis ids of the API (``api/analysis/{code}/{id}``);
the numbers it shows are compared with those documents. Kłodzko (IMGW-PIB, discharge and
water level 1951–2025) and Słupsk (IMGW-PIB, with water temperature since 1984).
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import THEMES, WIDTHS

pytestmark = pytest.mark.hydrolog

KLODZKO = "150160180"
SLUPSK = "154170010"
WAIT = 120_000
"""How long a section may take: Hydrolog computes every id on request [ms]."""
MILLION = 1e6


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


def tile(card: Any, label: str) -> Any:
    """The tile of a key figure („Próg”, „BFI”) of a section; a space matches any space."""
    pattern = re.escape(label).replace("\\ ", r"\s")
    return (
        card.locator("dl.figures > div")
        .filter(has=card.page.locator("dt", has_text=re.compile(f"^{pattern}$")))
        .first
    )


def figure(card: Any, label: str) -> str:
    """The value of a key figure of a section."""
    text: str = tile(card, label).locator("dd").inner_text(timeout=WAIT)
    return text


def provenance(card: Any, command: str) -> None:
    """The section names Hydrolog's command that computed its numbers."""
    chip = card.locator(".ana-prov .prov-hydrolog code", has_text=command).first
    chip.wait_for(timeout=WAIT)


def section(open_page: Any, base: str, code: str, name: str, **options: Any) -> Any:
    """The station's panel with one section open; its card."""
    page = open_page(f"?station={code}&section={name}", base=base, **options)
    return page.locator(f'[data-section="{name}"]')


def test_the_low_flow_periods_are_hydrologs(open_page: Any, analysis_url: str) -> None:
    card = section(open_page, analysis_url, KLODZKO, "lowflow")
    periods = analysis(analysis_url, KLODZKO, "low_flow_sequences.Q")
    assert number(figure(card, "Próg")) == pytest.approx(
        periods["threshold"], abs=0.005
    )
    assert number(figure(card, "Niżówek")) == periods["n_events"]
    assert number(figure(card, "Najdłuższa")) == periods["max_duration_days"]
    largest = max(periods["sequences"], key=lambda item: item["deficit_volume_m3"])
    assert number(figure(card, "Największy niedobór")) == pytest.approx(
        largest["deficit_volume_m3"] / MILLION, abs=0.005
    )
    latest = periods["sequences"][-1]
    first_row = card.locator("table.tbl tbody tr").first.inner_text(timeout=WAIT)
    assert latest["start_date"][8:10] + "." + latest["start_date"][5:7] in first_row
    provenance(card, "stats low-flow-sequences")
    expect(card.get_by_role("button", name="Kopiuj do Hydrologa")).to_be_visible()


def test_a_threshold_chosen_by_the_person_recomputes_the_periods(
    open_page: Any, analysis_url: str
) -> None:
    card = section(open_page, analysis_url, KLODZKO, "lowflow")
    stored = analysis(analysis_url, KLODZKO, "low_flow_sequences.Q")
    threshold = tile(card, "Próg").locator("dd")
    expect(threshold).to_have_text(re.compile(r"\d"), timeout=WAIT)

    card.get_by_role("radio", name="Q90").click()
    q90 = analysis(
        analysis_url,
        KLODZKO,
        "low_flow_sequences.Q",
        threshold_method="exceedance",
        exceedance_percent=90,
    )
    assert q90["threshold"] != pytest.approx(stored["threshold"], abs=0.01)
    expect(threshold).to_have_text(
        re.compile(re.escape(f"{q90['threshold']:.2f}".replace(".", ","))), timeout=WAIT
    )
    assert number(figure(card, "Niżówek")) == q90["n_events"]

    card.get_by_role("radio", name="wartość").click()
    limits = card.locator("form.hy-limits")
    limits.locator("input").first.fill("2.5")
    limits.locator("input").nth(1).fill("10")
    limits.get_by_role("button").click()
    given = analysis(
        analysis_url,
        KLODZKO,
        "low_flow_sequences.Q",
        threshold_method="value",
        threshold=2.5,
        min_duration_days=10,
    )
    expect(threshold).to_have_text(re.compile("2,50"), timeout=WAIT)
    expect(tile(card, "Niżówek").locator("dd")).to_have_text(
        str(given["n_events"]), timeout=WAIT
    )
    assert all(item["duration_days"] >= 10 for item in given["sequences"])


def test_low_water_periods_of_the_water_level_are_hydrologs(
    open_page: Any, analysis_url: str
) -> None:
    card = section(open_page, analysis_url, KLODZKO, "lowflow")
    expect(tile(card, "Próg").locator("dd")).to_have_text(
        re.compile(r"m³/s"), timeout=WAIT
    )
    card.get_by_role("radio", name="H · stan wody", exact=True).click()
    periods = analysis(analysis_url, KLODZKO, "low_flow_sequences.H")
    threshold = tile(card, "Próg")
    expect(threshold.locator("dd")).to_have_text(re.compile(r"\scm$"), timeout=WAIT)
    assert number(figure(card, "Próg")) == pytest.approx(periods["threshold"], abs=0.5)
    expect(threshold).to_contain_text("SNW", timeout=WAIT)
    assert number(figure(card, "Niżówek")) == periods["n_events"]
    assert number(figure(card, "Najdłuższa")) == periods["max_duration_days"]
    largest = max(periods["sequences"], key=lambda item: item["deficit_volume"])
    assert largest["deficit_volume_m3"] is None
    deficit = figure(card, "Największy niedobór")
    assert deficit.endswith("cm·d")
    assert number(deficit) == pytest.approx(largest["deficit_volume"], abs=0.5)
    assert number(figure(card, "Łączny niedobór")) == pytest.approx(
        periods["total_deficit"], abs=0.5
    )
    expect(card.get_by_role("radio", name="H90", exact=True)).to_be_visible()
    provenance(card, "stats low-flow-sequences")
    expect(card.get_by_role("button", name="Kopiuj do Hydrologa")).to_be_visible()


def test_duration_curves_and_zones_are_hydrologs(
    open_page: Any, analysis_url: str
) -> None:
    card = section(open_page, analysis_url, KLODZKO, "duration")
    zones = analysis(analysis_url, KLODZKO, "water_level_zones.H")["zones"]
    flows = analysis(analysis_url, KLODZKO, "duration_curve.Q")
    levels = analysis(analysis_url, KLODZKO, "duration_curve.H")
    assert number(figure(card, "NTW")) == zones["ntw_upper"]
    assert number(figure(card, "WTW")) == zones["stw_upper"]
    assert number(figure(card, "Klasa modalna")) == levels["modal_class"]["lower"]
    assert number(figure(card, "Q50 (mediana)")) == pytest.approx(
        flows["median"], abs=0.005
    )
    q90 = flows["values"][flows["exceedance_percents"].index(90.0)]
    assert number(figure(card, "Q90")) == pytest.approx(q90, abs=0.005)
    first_cell = card.page.locator("td:first-child", has_text=re.compile(r"^50$"))
    row = card.locator("table.tbl tbody tr").filter(has=first_cell).first
    cells = row.locator("td").all_inner_texts()
    assert (
        number(cells[1]) == levels["values"][levels["exceedance_percents"].index(50.0)]
    )
    provenance(card, "stats duration-curve")
    provenance(card, "hydrometrics water-level-zones")


def test_regime_and_seasonality_are_hydrologs(
    open_page: Any, analysis_url: str
) -> None:
    card = section(open_page, analysis_url, KLODZKO, "regime")
    regime = analysis(analysis_url, KLODZKO, "regime.Q")
    names = {4: "niwalno-pluwialny", 5: "pluwialno-niwalny"}
    assert figure(card, "Typ reżimu") == names[regime["regime_type"]["code"]]
    assert number(figure(card, "Wskaźnik sezonowości")) == pytest.approx(
        regime["seasonality_index"], abs=0.0005
    )
    maxima = analysis(analysis_url, KLODZKO, "seasonality.Q.max")
    month, day = (int(part) for part in maxima["mean_date"].split("-"))
    roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
    assert figure(card, "Średni termin WQ") == f"{day} {roman[month - 1]}"
    assert number(figure(card, "Koncentracja r")) == pytest.approx(
        maxima["concentration"], abs=0.005
    )
    assert card.locator("figure.hy-circle circle.hy-circle-dot").count() == len(
        maxima["years"]
    )
    for command in (
        "stats daily",
        "stats monthly",
        "stats regime",
        "stats seasonality",
    ):
        provenance(card, command)

    card.get_by_role("radio", name="minima").click()
    minima = analysis(analysis_url, KLODZKO, "seasonality.Q.min")
    month, day = (int(part) for part in minima["mean_date"].split("-"))
    expect(tile(card, "Średni termin NQ").locator("dd")).to_have_text(
        f"{day} {roman[month - 1]}", timeout=WAIT
    )


def test_the_seasonality_of_the_water_levels_extremes_is_hydrologs(
    open_page: Any, analysis_url: str
) -> None:
    card = section(open_page, analysis_url, KLODZKO, "regime")
    expect(tile(card, "Średni termin WQ").locator("dd")).to_have_text(
        re.compile(r"\d"), timeout=WAIT
    )
    seasonality = (
        card.locator("section.ana")
        .filter(has=card.page.locator("h3", has_text="Sezonowość ekstremów rocznych"))
        .last
    )
    seasonality.get_by_role("radio", name="H · stan wody", exact=True).click()
    roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
    for extreme, name in (("max", "WW"), ("min", "NW")):
        if extreme == "min":
            seasonality.get_by_role("radio", name="minima").click()
        found = analysis(analysis_url, KLODZKO, f"seasonality.H.{extreme}")
        month, day = (int(part) for part in found["mean_date"].split("-"))
        expect(tile(card, f"Średni termin {name}").locator("dd")).to_have_text(
            f"{day} {roman[month - 1]}", timeout=WAIT
        )
        assert number(figure(card, "Koncentracja r")) == pytest.approx(
            found["concentration"], abs=0.005
        )
        sources = {"half_years": "półrocza IMGW-PIB", "daily": "szereg dobowy"}
        assert figure(card, "Źródło") == sources[found["source"]]
        expect(card.locator("figure.hy-circle circle.hy-circle-dot")).to_have_count(
            len(found["years"]), timeout=WAIT
        )


def test_water_temperature_is_hydrologs(open_page: Any, analysis_url: str) -> None:
    card = section(open_page, analysis_url, SLUPSK, "temperature")
    harmonics = analysis(analysis_url, SLUPSK, "harmonics.T")
    period = harmonics["period"]
    assert number(figure(card, "A₀ średnia")) == pytest.approx(
        period["mean"], abs=0.005
    )
    assert number(figure(card, "C₁ amplituda")) == pytest.approx(
        period["harmonics"][0]["amplitude"], abs=0.005
    )
    warm = analysis(analysis_url, SLUPSK, "threshold_events.T.ge20")
    assert number(figure(card, "Dni z T ≥ 20 °C")) == warm["days_beyond"]
    assert number(figure(card, "Ciągi takich dni")) == warm["n_events"]
    latest = harmonics["years"][-1]
    row = card.locator("table.tbl tbody tr").first.locator("td").all_inner_texts()
    assert number(row[0]) == latest["year"]
    assert number(row[2]) == pytest.approx(latest["mean"], abs=0.005)
    for command in (
        "stats harmonics",
        "stats threshold-events",
        "stats characteristic",
    ):
        provenance(card, command)


def test_trends_and_water_balance_are_hydrologs(
    open_page: Any, analysis_url: str
) -> None:
    card = section(open_page, analysis_url, KLODZKO, "trends")
    trend = analysis(analysis_url, KLODZKO, "mann_kendall.Q.max")
    row = card.locator("table.tbl tbody tr", has_text="WQ").first
    cells = row.locator("td").all_inner_texts()
    assert number(cells[2]) == trend["s_statistic"]
    assert number(cells[4]) == pytest.approx(trend["p_value"], abs=0.0005)
    runoff = analysis(analysis_url, KLODZKO, "runoff_volume.Q")
    assert number(figure(card, "Średni odpływ roczny")) == pytest.approx(
        runoff["mean_annual_volume_m3"] / MILLION, abs=0.05
    )
    baseflow = analysis(analysis_url, KLODZKO, "baseflow.Q")
    assert number(figure(card, "BFI")) == pytest.approx(baseflow["bfi"], abs=0.0005)
    assert number(figure(card, "Stała recesji k")) == pytest.approx(
        baseflow["recession"]["k"], abs=0.00005
    )
    for command in ("stats mann-kendall", "stats runoff-volume", "stats baseflow"):
        provenance(card, command)


@pytest.mark.parametrize(
    ("code", "name", "label"),
    [
        (KLODZKO, "lowflow", "Threshold"),
        (KLODZKO, "duration", "Modal class"),
        (KLODZKO, "regime", "Seasonality index"),
        (SLUPSK, "temperature", "Explained variance"),
        (KLODZKO, "trends", "Mean annual runoff"),
    ],
)
def test_each_section_reads_in_english_on_a_phone_in_the_dark(
    open_page: Any, analysis_url: str, code: str, name: str, label: str
) -> None:
    card = section(
        open_page, analysis_url, code, name, theme=THEMES[1], width=WIDTHS[1], lang="en"
    )
    expect(tile(card, label).locator("dd")).to_have_text(
        re.compile(r"\d"), timeout=WAIT
    )


def test_low_water_periods_of_the_water_level_read_in_english_on_a_phone_in_the_dark(
    open_page: Any, analysis_url: str
) -> None:
    card = section(
        open_page,
        analysis_url,
        KLODZKO,
        "lowflow",
        theme=THEMES[1],
        width=WIDTHS[1],
        lang="en",
    )
    expect(tile(card, "Threshold").locator("dd")).to_have_text(
        re.compile(r"m³/s"), timeout=WAIT
    )
    card.get_by_role("radio", name="H · water level", exact=True).click()
    periods = analysis(analysis_url, KLODZKO, "low_flow_sequences.H")
    threshold = tile(card, "Threshold")
    expect(threshold.locator("dd")).to_have_text(
        re.compile(rf"^{periods['threshold']:.0f}\s+cm$"), timeout=WAIT
    )
    expect(threshold).to_contain_text("SNW, the mean of the annual minima")
    expect(tile(card, "Low-flow periods").locator("dd")).to_have_text(
        str(periods["n_events"])
    )
    expect(tile(card, "Longest").locator("dd")).to_have_text(
        f"{periods['max_duration_days']} days"
    )
