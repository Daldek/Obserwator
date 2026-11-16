"""
The GUI's chart module (``web/src/charts/``) in Chromium.

Scales, ticks and decimation are pure functions, called through ``page.evaluate`` of
``import("./src/charts/<module>.js")`` after the page's texts of a language are loaded;
the drawing, the readout and the zoom are checked on charts drawn into the GUI's page
(its stylesheet and Content-Security-Policy), where ``open_page`` fails a test on any
console error, page error or CSP violation.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from tests.e2e.conftest import THEMES, WIDTHS

# The page's language loaded, then the chart module's functions as `charts`.
_SETUP = """
async (lang) => {
  const i18n = await import("./src/i18n.js");
  await i18n.loadTexts(lang);
  window.charts = {
    ...(await import("./src/charts/scale.js")),
    ...(await import("./src/charts/series.js")),
    ...(await import("./src/charts/draw.js")),
  };
  window.dayOf = (y, m, d = 1) => Math.round(Date.UTC(y, m, d) / 86400000);
}
"""

# A chart drawn over the page, in a host as wide as the window less a margin.
_MOUNT = """
(spec) => {
  document.querySelector(".chart-probe")?.remove();
  const host = document.createElement("div");
  host.className = "chart-probe";
  host.style.position = "fixed";
  host.style.inset = "0 16px auto 16px";
  host.style.zIndex = "10000";
  host.style.background = "var(--surface)";
  document.body.append(host);
  window.chart = window.charts.drawChart(host, window.specOf(spec));
}
"""

# A chart of daily values from 2020-01-01, ten days of March missing.
_SPECS = """
() => { window.specOf = ({ days, zoom }) => {
  const start = window.dayOf(2020, 0);
  const data = Array.from({ length: days }, (_, at) => [
    start + at,
    at >= 60 && at < 70 ? null : 100 + 50 * Math.sin((2 * Math.PI * at) / 365) + (at % 7),
  ]);
  return {
    x: { scale: "date" },
    y: { label: "Q [m³/s]", unit: "m³/s", zero: false, digits: 1 },
    series: [{ id: "q", kind: "line", label: "Q", data }],
    readout: true,
    zoom,
    fit: { ratio: 0.45, minHeight: 200 },
  };
}; }
"""


def _open(open_page: Any, lang: str = "pl", **options: Any) -> Any:
    page = open_page(lang=lang, ready=False, **options)
    page.evaluate(_SETUP, lang)
    page.evaluate(_SPECS)
    return page


def _mount(page: Any, days: int, zoom: bool | None = None) -> None:
    page.evaluate(_MOUNT, {"days": days, "zoom": zoom})


def _state(page):
    return page.evaluate(
        """() => {
          const host = document.querySelector(".chart-probe");
          const line = host.querySelector(".readout-line");
          const bar = host.querySelector(".chart-zoom");
          return {
            index: window.chart.readout.index(),
            at: line && line.closest(".readout").getAttribute("visibility") !== "hidden"
              ? Number(line.getAttribute("x1")) : null,
            live: host.querySelector(".chart-sr").textContent,
            range: window.chart.zoom.range(),
            bar: bar.hidden ? null : bar.querySelector(".chart-zoom-range").textContent,
            ticks: [...host.querySelectorAll("text.tick")].map((tick) => tick.textContent),
          };
        }"""
    )


# --- scales and ticks ------------------------------------------------------------------


def test_scales_map_values_to_the_plot_and_back(open_page):
    page = _open(open_page)
    found = page.evaluate(
        """() => {
          const { linearScale, logScale, gumbelScale, reducedVariate } = window.charts;
          const linear = linearScale([0, 10], [100, 200]);
          const log = logScale([1, 1000], [0, 300]);
          const gumbel = gumbelScale([99, 0.1], [0, 600]);
          const share = (p) => (reducedVariate(p) - reducedVariate(99))
            / (reducedVariate(0.1) - reducedVariate(99));
          return {
            linear: [linear(5), linear.invert(150), linear(-10)],
            log: [log(10), log(100), log.invert(200), log(0)],
            gumbel: [gumbel(10), 600 * share(10), gumbel.invert(gumbel(1)), gumbel(100)],
          };
        }"""
    )
    assert found["linear"] == [150, 5, 0]
    assert found["log"][:2] == pytest.approx([100, 200])
    assert found["log"][2] == pytest.approx(100)
    assert math.isnan(found["log"][3])  # a log axis has no place for 0
    assert found["gumbel"][0] == pytest.approx(found["gumbel"][1])
    assert found["gumbel"][2] == pytest.approx(1)
    assert math.isnan(found["gumbel"][3])


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        (
            "pl",
            {
                "years": ["1800", "1850", "1900", "1950", "2000"],
                "months": ["sty 2020", "lut", "mar"],
                "days": ["02.03.2020", "09.03", "16.03"],
                "time": ["0,0", "0,5", "1,0", "1,5"],
                "log": ["0,1", "0,2", "0,5", "1", "2", "5", "10"],
                "decades": ["1", "10", "100", "1000", "10\u00a0000"],
                "numbers": ["\u22123", "0,0", "1951", "12\u00a0345,3"],
                "readout": "01.11.1950",
            },
        ),
        (
            "en",
            {
                "years": ["1800", "1850", "1900", "1950", "2000"],
                "months": ["Jan 2020", "Feb", "Mar"],
                "days": ["02/03/2020", "09/03", "16/03"],
                "time": ["0.0", "0.5", "1.0", "1.5"],
                "log": ["0.1", "0.2", "0.5", "1", "2", "5", "10"],
                "decades": ["1", "10", "100", "1000", "10,000"],
                "numbers": ["\u22123", "0.0", "1951", "12,345.3"],
                "readout": "01/11/1950",
            },
        ),
    ],
)
def test_ticks_are_written_in_the_page_language(open_page, lang, expected):
    page = _open(open_page, lang)
    found = page.evaluate(
        """() => {
          const c = window.charts;
          const labels = (ticks) => ticks.map((tick) => tick.label);
          return {
            years: labels(c.dateTicks(dayOf(1775, 0), dayOf(2025, 0), 10).ticks),
            months: labels(c.dateTicks(dayOf(2020, 0), dayOf(2020, 11), 13).ticks).slice(0, 3),
            monthCount: c.dateTicks(dayOf(2020, 0), dayOf(2020, 11), 13).ticks.length,
            days: labels(c.dateTicks(dayOf(2020, 2, 1), dayOf(2020, 2, 20), 10).ticks),
            time: labels(c.timeTicks(0, 360, 13).ticks).slice(0, 4),
            timeCount: c.timeTicks(0, 360, 13).ticks.length,
            log: labels(c.logTicks(0.1, 10)),
            decades: labels(c.logTicks(1, 1e4)),
            numbers: [c.formatNumber(-3), c.formatNumber(-0.01, 1), c.formatNumber(1951),
                      c.formatNumber(12345.25, 1)],
            readout: c.formatDay(dayOf(1950, 10, 1)),
          };
        }"""
    )
    assert found.pop("monthCount") == 12
    assert found.pop("timeCount") == 13  # 0 to 6 h every half hour
    assert found == expected


@pytest.mark.parametrize(("lang", "years"), [("pl", "T [lata]"), ("en", "T [years]")])
def test_probability_ticks_name_the_exceedance_and_the_return_period(
    open_page, lang, years
):
    page = _open(open_page, lang)
    found = page.evaluate(
        """() => {
          const c = window.charts;
          const scale = c.gumbelScale([99, 0.1], [60, 700]);
          const ticks = c.gumbelTicks(scale, 30);
          const crowded = c.gumbelTicks(c.gumbelScale([99, 0.1], [60, 200]), 30);
          const host = document.createElement("div");
          document.body.append(host);
          const chart = c.drawChart(host, {
            x: { scale: "gumbel", domain: [99, 0.1] },
            y: { label: "WQ" },
            series: [{ id: "g", kind: "line", data: [[90, 10], [1, 50], [0.1, 70]] }],
          });
          const rows = [...chart.svg.querySelectorAll("text.axis-label")].map((t) => t.textContent);
          chart.destroy();
          host.remove();
          return {
            pairs: ticks.map((tick) => [tick.value, tick.sub]),
            positions: ticks.map((tick) => scale(tick.value)),
            crowded: crowded.map((tick) => tick.value),
            rows,
          };
        }"""
    )
    pairs = dict(found["pairs"])
    assert pairs[50] == "2" and pairs[10] == "10" and pairs[1] == "100"
    assert pairs[0.1] == "1000"
    assert found["positions"] == sorted(found["positions"])
    # A narrow axis keeps the major probabilities and drops ticks that would overlap
    assert set(found["crowded"]) <= {50, 10, 1, 0.1, 0.01, 90, 99, 20, 5, 2, 0.5, 0.2}
    assert 10 in found["crowded"] and len(found["crowded"]) < len(found["pairs"])
    assert found["rows"][:2] == ["p [%]", years]


# --- decimation ------------------------------------------------------------------------


def test_decimation_keeps_each_columns_extremes_and_gaps(open_page):
    page = _open(open_page)
    found = page.evaluate(
        """() => {
          const { thinPoints } = window.charts;
          // 90,000 daily values (ČHMÚ since 1775), a gap of 30 days, 700 columns
          const n = 90000, columns = 700;
          const points = Array.from({ length: n }, (_, at) => ({
            x: at,
            y: at >= 45000 && at < 45030 ? null : Math.sin(at / 58.1) * 100 + ((at * 7919) % 101),
          }));
          const kept = thinPoints(points, (x) => x, columns);
          const column = (x) => Math.min(columns - 1, Math.floor((x / (n - 1)) * columns));
          const worst = [];
          const lows = new Map(), highs = new Map(), keptLows = new Map(), keptHighs = new Map();
          for (const [source, low, high] of [[points, lows, highs], [kept, keptLows, keptHighs]]) {
            for (const p of source) {
              if (!Number.isFinite(p.y)) continue;
              const c = column(p.x);
              low.set(c, Math.min(low.get(c) ?? Infinity, p.y));
              high.set(c, Math.max(high.get(c) ?? -Infinity, p.y));
            }
          }
          for (const [c, value] of lows) if (keptLows.get(c) !== value) worst.push(c);
          for (const [c, value] of highs) if (keptHighs.get(c) !== value) worst.push(c);
          const band = Array.from({ length: n }, (_, at) => ({ x: at, lo: -(at % 13), hi: at % 17 }));
          const thinBand = thinPoints(band, (x) => x, columns, { low: (p) => p.lo, high: (p) => p.hi });
          const short = points.slice(0, 2000);
          return {
            count: kept.length,
            ordered: kept.every((p, at) => at === 0 || p.x > kept[at - 1].x),
            ends: [kept[0].x, kept.at(-1).x],
            gap: kept.some((p) => p.y === null && p.x >= 45000 && p.x < 45030),
            columnsWrong: worst.length,
            band: [thinBand.length, Math.min(...thinBand.map((p) => p.lo)), Math.max(...thinBand.map((p) => p.hi))],
            shortKept: thinPoints(short, (x) => x, columns) === short,
          };
        }"""
    )
    assert found["count"] <= 5 * 700
    assert found["ordered"]
    assert found["ends"] == [0, 89999]
    assert found["gap"]  # the gap still breaks the drawn line
    assert found["columnsWrong"] == 0
    assert found["band"][0] <= 5 * 700 and found["band"][1:] == [-12, 16]
    assert found["shortKept"]  # four points a column or fewer: drawn as they are


def test_close_reference_lines_keep_their_labels_apart(open_page):
    page = _open(open_page)
    found = page.evaluate(
        """() => {
          const host = document.createElement("div");
          document.body.append(host);
          // SSW 98 cm and SNW 80 cm on a 0-800 cm axis, a lone level far above
          const chart = window.charts.drawChart(host, {
            size: { width: 760, height: 432 },
            x: { scale: "date" },
            y: { min: 0, max: 800 },
            series: [{ id: "h", kind: "line", data: [[0, 100], [365, 300]] }],
            marks: [
              { kind: "hline", y: 98, label: "SSW" },
              { kind: "hline", y: 80, label: "SNW" },
              { kind: "hline", y: 600, label: "WWW" },
            ],
          });
          const rows = [...chart.svg.querySelectorAll("g.mark.hline")].map((group) => ({
            line: Number(group.querySelector("line").getAttribute("y1")),
            label: Number(group.querySelector("text").getAttribute("y")),
          }));
          chart.destroy();
          host.remove();
          return rows;
        }"""
    )
    ssw, snw, www = found
    assert www["label"] == pytest.approx(www["line"] - 4, abs=0.11)  # alone: above it
    assert ssw["label"] == pytest.approx(ssw["line"] - 4, abs=0.11)
    assert snw["label"] > snw["line"]  # the lower one moves below its line
    assert snw["label"] - ssw["label"] >= 12.9


# --- drawing, readout, zoom ------------------------------------------------------------


def test_fifty_thousand_daily_values_draw_in_under_200_ms(open_page):
    page = _open(open_page, width=1440)
    found = page.evaluate(
        """() => {
          const times = [];
          let drawn = 0;
          for (let run = 0; run < 3; run += 1) {
            const spec = window.specOf({ days: 50000 });
            const host = document.createElement("div");
            document.body.append(host);
            const started = performance.now();
            const chart = window.charts.drawChart(host, spec);
            chart.svg.getBBox();
            times.push(performance.now() - started);
            drawn = (chart.svg.querySelector("path.ser").getAttribute("d").match(/[ML]/g) || []).length;
            chart.destroy();
            host.remove();
          }
          return { best: Math.min(...times), drawn, width: window.innerWidth };
        }"""
    )
    assert found["best"] < 200, f"{found['best']:.0f} ms"
    # Decimated to at most five points a pixel column of the plot
    assert 0 < found["drawn"] <= 5 * found["width"]


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_readout_moves_by_keys(open_page, theme, width):
    page = _open(open_page, "pl", theme=theme, width=width)
    _mount(page, days=300)
    page.focus(".chart-probe svg")
    page.keyboard.press("ArrowRight")
    first = _state(page)
    assert first["index"] == 0 and first["live"].startswith("01.01.2020 · Q: ")
    page.keyboard.press("ArrowRight")
    second = _state(page)
    assert second["index"] == 1 and second["live"].startswith("02.01.2020")
    assert second["at"] > first["at"]
    page.keyboard.press("Shift+ArrowRight")
    assert _state(page)["index"] == 11
    page.keyboard.press("End")
    end = _state(page)
    assert end["index"] == 299 and end["live"].startswith("26.10.2020")
    # A day of the gap reads its date alone
    page.keyboard.press("Home")
    for _ in range(61):
        page.keyboard.press("ArrowRight")
    assert _state(page)["live"] == "02.03.2020"
    page.keyboard.press("Escape")
    hidden = _state(page)
    assert hidden["index"] is None and hidden["at"] is None and hidden["live"] == ""


@pytest.mark.parametrize(
    ("lang", "reset"), [("pl", "Pokaż całość"), ("en", "Show all")]
)
def test_zoom_by_keys_and_by_a_range(open_page, lang, reset):
    page = _open(open_page, lang)
    _mount(page, days=3000)
    whole = _state(page)
    assert whole["range"] is None and whole["bar"] is None
    assert whole["ticks"][-1].endswith("2028")

    # Keys: + halves the range around the readout, − doubles it, 0 shows the whole
    page.focus(".chart-probe svg")
    page.keyboard.press("End")
    last = _state(page)["live"]
    page.keyboard.press("+")
    half = _state(page)
    span = half["range"]["max"] - half["range"]["min"]
    assert span == pytest.approx(2999 / 2, rel=0.02)
    assert half["live"] == last  # the readout stays on its day
    assert half["bar"] is not None and page.inner_text(".chart-zoom-reset") == reset
    page.keyboard.press("+")
    assert _state(page)["range"]["max"] - _state(page)["range"]["min"] < span
    page.keyboard.press("-")
    page.keyboard.press("-")
    assert _state(page)["range"] is None

    # The readout's arrows move a zoomed range past its edge
    page.keyboard.press("+")
    page.keyboard.press("+")
    before = _state(page)["range"]
    page.keyboard.press("Home")
    page.keyboard.press("ArrowLeft")
    moved = _state(page)["range"]
    assert moved["min"] < before["min"] and moved["max"] < before["max"]
    page.keyboard.press("0")
    assert _state(page)["range"] is None

    # A mouse drag over the plot shows the range dragged; the button shows the whole
    box = page.locator(".chart-probe svg").bounding_box()
    y = box["y"] + box["height"] / 2
    page.mouse.move(box["x"] + box["width"] * 0.4, y)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * 0.5, y, steps=4)
    page.mouse.move(box["x"] + box["width"] * 0.6, y, steps=4)
    page.mouse.up()
    dragged = _state(page)
    assert dragged["range"] is not None
    assert 0.15 < (dragged["range"]["max"] - dragged["range"]["min"]) / 2999 < 0.25
    assert dragged["ticks"] != whole["ticks"]
    page.click(".chart-zoom-reset")
    assert _state(page)["range"] is None and _state(page)["bar"] is None


def test_language_switch_redraws_ticks_and_readout(open_page):
    page = _open(open_page, "pl")
    _mount(page, days=1000)
    assert "maj" in _state(page)["ticks"]
    page.evaluate("async () => (await import('./src/i18n.js')).loadTexts('en')")
    assert "May" in _state(page)["ticks"]
    page.focus(".chart-probe svg")
    page.keyboard.press("ArrowRight")
    assert _state(page)["live"].startswith("01/01/2020 · Q: ")
