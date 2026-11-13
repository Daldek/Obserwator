"""The regulamin filled for the deployment (Nogat DEV-15.7, design/README "Kit")."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

import obserwator
from obserwator.gui._config import Basemap, GuiConfig
from obserwator.gui._terms import BLOCKS, fill, terms_page

WEB = Path(obserwator.__file__).parent / "gui" / "web"
TEMPLATE = (WEB / "nogat" / "nogat-terms.html").read_text(encoding="utf-8")
OPERATOR = {
    "name": "Jan Kowalski",
    "email": "jan@example.org",
    "terms_effective": "2026-11-20",
    "processor": "Cloudflare, Inc.",
    "processor_transfer": "Transfers to the USA under the EU-U.S. DPF.",
    "processor_cookie": "",
    "mail_provider": "iCloud Mail (Apple)",
    "mail_transfer": "Mogą być przetwarzane poza Europejskim Obszarem Gospodarczym.",
}
BASEMAP = Basemap("https://tiles.example/planet", "https://tiles.example", "OSM")

# The heading of each block of the kit's template.
HEADINGS = {
    "imgw": "<h3>IMGW-PIB: dane publiczne</h3>",
    "imgw-hydro": "<h3>IMGW-PIB: serwis hydrologiczny</h3>",
    "pmaxtp": "<h3>IMGW-PIB: opady maksymalne PMAXTP</h3>",
    "chmi": "<h3>ČHMÚ</h3>",
    "gugik": "<h3>GUGiK</h3>",
    "osm": "<h3>OpenStreetMap (kafelki OpenFreeMap, podkład OSM serwisu geoportal.gov.pl)</h3>",
    "esri": "<h3>Esri World Imagery</h3>",
}


def config(
    tmp_path,
    *,
    operator=OPERATOR,
    gui=None,
    basemap=None,
) -> GuiConfig:
    return GuiConfig(
        root=tmp_path / "root",
        state_dir=tmp_path / "state",
        basemap=basemap,
        request_limit=300,
        request_window=60,
        gui={"obserwator": "https://obserwator.example/"} if gui is None else gui,
        operator=operator,
        operator_problems=(),
    )


def values(**changes: str) -> dict[str, str]:
    return {
        "service_name": "Obserwator",
        "service_url": "https://obserwator.example/",
        "operator_name": "Jan Kowalski",
        "operator_email": "jan@example.org",
        "terms_effective": "2026-11-20",
        "processor": "Cloudflare, Inc.",
        "processor_transfer": "",
        "processor_cookie": "",
        "mail_provider": "iCloud Mail (Apple)",
        "mail_transfer": "",
        "software_licence": "MIT",
        "source_url": "https://github.com/Daldek/Obserwator",
        "tokens_href": "nogat/tokens.css",
        "kit_href": "nogat/",
        **changes,
    }


def test_the_page_keeps_obserwators_blocks_and_fills_every_field(tmp_path):
    page = terms_page(config(tmp_path), WEB)

    assert page is not None
    text = page.decode("utf-8")
    for block in BLOCKS:
        assert HEADINGS[block] in text
    for block in ("gugik", "osm", "esri"):
        assert HEADINGS[block] not in text
    assert "{{" not in text and "<!-- block" not in text and "<!-- /block" not in text
    assert "Regulamin serwisu Obserwator" in text
    assert '<a href="mailto:jan@example.org">jan@example.org</a>' in text
    assert "obowiązuje od 2026-11-20" in text
    assert "Transfers to the USA under the EU-U.S. DPF." in text
    assert "w usłudze iCloud Mail (Apple). Mogą być przetwarzane poza" in text
    assert "na licencji MIT" in text
    assert '<a href="https://github.com/Daldek/Obserwator">' in text
    assert '<link rel="stylesheet" href="nogat/tokens.css">' in text
    assert '<link rel="stylesheet" href="nogat/nogat-terms.css">' in text
    assert (
        '<a href="https://obserwator.example/">Wróć do serwisu Obserwator</a>' in text
    )


def test_a_basemap_adds_the_openstreetmap_block(tmp_path):
    page = terms_page(config(tmp_path, basemap=BASEMAP), WEB)

    assert page is not None
    assert HEADINGS["osm"] in page.decode("utf-8")


def test_values_are_html_escaped(tmp_path):
    operator = {**OPERATOR, "name": "Kowalski & <Syn> \"S.A.\" 'x'"}

    page = terms_page(config(tmp_path, operator=operator), WEB)

    assert page is not None
    text = page.decode("utf-8")
    assert "Kowalski &amp; &lt;Syn&gt; &quot;S.A.&quot; &#x27;x&#x27;" in text
    assert "<Syn>" not in text


@pytest.mark.parametrize(
    "key", ["processor_transfer", "processor_cookie", "mail_transfer"]
)
def test_an_empty_sentence_of_the_operator_is_allowed(tmp_path, key):
    operator = {**OPERATOR, key: ""}

    assert terms_page(config(tmp_path, operator=operator), WEB) is not None


def test_no_page_without_an_operator_or_without_the_guis_address(tmp_path):
    assert terms_page(config(tmp_path, operator=None), WEB) is None
    assert (
        terms_page(config(tmp_path, gui={"hydrolog": "https://h.example/"}), WEB)
        is None
    )


def test_a_failed_filling_gives_no_page_and_a_warning(tmp_path, caplog):
    operator = {key: value for key, value in OPERATOR.items() if key != "processor"}

    with caplog.at_level(logging.WARNING, logger="obserwator.gui._terms"):
        page = terms_page(config(tmp_path, operator=operator), WEB)

    assert page is None
    assert "processor" in caplog.text


def test_fill_drops_unlisted_blocks_with_their_markers():
    text = fill(TEMPLATE, values(), ["chmi"])

    assert HEADINGS["chmi"] in text
    for block in ("imgw", "imgw-hydro", "pmaxtp", "gugik", "osm"):
        assert HEADINGS[block] not in text
    assert "<!-- block" not in text and "<!-- /block" not in text
    assert "\n\n\n" not in text


# A name that is no block of the kit (``imgw-terms`` was a derived one before ECO-065)
@pytest.mark.parametrize("listed", ["nope", "imgw-terms"])
def test_fill_refuses_a_block_that_cannot_be_listed(listed):
    with pytest.raises(ValueError, match=listed):
        fill(TEMPLATE, values(), [listed])


@pytest.mark.parametrize(
    ("changes", "named"),
    [
        ({"operator_email": "  "}, "operator_email"),
        ({"mail_provider": ""}, "mail_provider"),
        ({"service_name": ""}, "service_name"),
        ({"surplus": "x"}, "surplus"),
    ],
)
def test_fill_refuses_an_empty_or_unknown_value(changes, named):
    with pytest.raises(ValueError, match=named):
        fill(TEMPLATE, values(**changes), BLOCKS)


def test_fill_refuses_a_missing_value():
    given = values()
    del given["kit_href"]

    with pytest.raises(ValueError, match="kit_href"):
        fill(TEMPLATE, given, BLOCKS)


def test_fill_refuses_a_page_with_a_field_left():
    with pytest.raises(ValueError, match=r"\{\{"):
        fill(TEMPLATE, values(operator_name="{{x"), BLOCKS)
