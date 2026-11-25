# Intake note: Gdańskie Wody (pomiary.gdanskiewody.pl)

The provider intake of Nogat's plan `docs/plans/2026-11-20-hydromet-providers.md` („Provider intake”): every row of its list, with the date each was checked and the evidence. The facts of 2026-11-20 were checked against the live API with the author's key and the API documentation he pasted (visible only to registered users); those of 2026-11-25 against the live API and the public site, for [ADR-034](../DECISIONS.md#adr-034-gdańskie-wody-the-first-provider-of-the-class-other). The answers recorded on 2026-11-25 for the tests are `src/obserwator/_data/fixtures/gdanskiewody_recordings.json` (current days only; the key is never stored).

**State on 2026-11-25:** the provider is in the registry (`GDANSKIEWODY`) and off by default; its terms are unknown, so its attribution lines are drafts and no server may serve it; by the author's decision of the same day no history is downloaded until he names the range („Nie czekamy na Gdańskie Wody z licencją, najwyżej wycofamy tę funkcjonalność - ale nie pobieramy danych historycznych. Dopiero wskażę zakres po przygotowaniu kodu.”). Usage: [USAGE.md „Gdańskie Wody (Gdańsk)”](../USAGE.md#gdańskie-wody-gdańsk).

| Row | Answer | Checked | Evidence |
|---|---|---|---|
| Identity | Gdańskie Wody Sp. z o.o., short name „Gdańskie Wody”, Poland (`PL`); its „System pomiarów meteorologicznych i hydrologicznych aglomeracji gdańskiej” at https://pomiary.gdanskiewody.pl; contact for the API: `pomiary@gdanskiewody.pl`. In Obserwator: provider id `GDANSKIEWODY` (the plan's `gdanskie-wody`, written as the registry writes ids, ADR-028), dataset prefix `pl.gdanskiewody`, acronym and attribution origin `gdanskiewody`, source class `other` (P11), adapter `obserwator.providers.pl.gdanskiewody`. | 2026-11-25 | The site's title and footer („© 2015 - 2026 Gdańskie Wody Sp. z o.o.”); the API page `https://pomiary.gdanskiewody.pl/rest/` („W razie problemów, uwag lub sugestii zmian prosimy o kontakt pod adresem: pomiary@gdanskiewody.pl”). |
| Terms | **Unknown.** The signup form requires accepting a regulamin and a RODO clause; the regulamin is shown only after sign-in, so whether the data may be stored, served publicly and redistributed, whether attribution is required and in what words, and whether commercial use is allowed are not known. The verbatim text is pending (section „Terms, verbatim” below). Until it is known: the attribution lines are drafts (`obserwator.attribution.provisional`), the licence is `gdanskiewody-terms-unknown` (its URL the signup page `https://pomiary.gdanskiewody.pl/account/signup`), the `license_terms` notice says that the terms are unknown, no server may serve the provider (`terms_unknown`), and its source is `private` in `[obserwator.capture]`. | 2026-11-20, 2026-11-25 | The plan's check of 2026-11-20 (row „Terms”); the API page on 2026-11-25: „Korzystanie z API wymaga nieodpłatnej rejestracji. Szczegółowa dokumentacja dostępna jest dla zarejestrowanych użytkowników.” |
| Access | An API with a key: free registration, the key in the account's settings, sent as `Authorization: Bearer <key>`; REST answering JSON (`Content-Type: application/json; charset=utf-8`; the server also sets a `csrf_cookie`, which Obserwator ignores). The API page: „Umożliwia pobranie listy stacji pomiarowych oraz wartości poszczególnych pomiarów zagregowane do pełnych godzin.” No rate limit is published and no answer carries a rate-limit header; an answer takes 0.2–1.5 s. In Obserwator: `OBSERWATOR_GDANSKIE_WODY_API_KEY` or `OBSERWATOR_GDANSKIE_WODY_API_KEY_FILE` (P3; environment or `.env`, never `nogat.toml`, never logged or in an address), requests one at a time at least `OBSERWATOR_GDANSKIE_WODY_REQUEST_INTERVAL` seconds apart (default and minimum 1, P10). The load the provider accepts is not stated: a backfill waits for its answer. | 2026-11-20, 2026-11-25 | The documentation of 2026-11-20; the API page and the headers of an answer of `GET rest/stations` on 2026-11-25. |
| Errors | Every answer is HTTP 200; an error is `{"status": "error", "code": N, "message": …}` (table „Errors” below), known only from the body. A date before a station's record or after today answers 24 `null`s, not an error. | 2026-11-20, 2026-11-25 | The answers recorded on 2026-11-25 (cases `stations_bad_key`, `m_1_foo_20261103`, `m_1_rain_bad_date`, `m_1_rain_bad_form`, `m_3_rain_20261103`, `m_1_water_20261103`, `m_1_rain_20261103_bad_key`); `-12` from the documentation of 2026-11-20. |
| Stations | `GET rest/stations`: `{"status": "success", "message": "Lista stacji", "data": [...]}`, 131 stations on 2026-11-20 and on 2026-11-25, all `active: true`. A station has `no` (an integer of 1 to 999, with gaps; its stability is not stated), `name` (e.g. „Dolne Miasto”), `lat` and `long` (decimal degrees as texts, WGS84 by their values; CRS and accuracy not stated; empty for 5 stations: 70, 259, 262, 263, 700), `active` and one boolean per quantity. No river, elevation, datum or first and last data; the site's tables write an elevation into some names (e.g. „Gdansk -000,1 m n.p.m.- Dolne Miasto”), the API does not. In Obserwator: code `GDANSKIEWODY-<no>`; family `hydro` for the 93 stations with a hydrological quantity, `meteo` for the 38 others; a catalog `stations/versions/gdanskiewody_stations` checked against Poland's border (ADR-018), `location_source` `pl.gdanskiewody.station_list`, no river, elevation or gauge properties. | 2026-11-20, 2026-11-25 | The live list of 2026-11-25 (131 rows; counted by symbol and family); the recorded case `stations` (8 of its stations). |
| Quantities | 15 symbols, 202 station and quantity pairs (table „Quantities” below). Time step: the hour („zagregowane do pełnych godzin”; how a quantity is aggregated to the hour is not stated). Time zone: UTC (the charts say „Czas UTC”). Labels: **the start of the hour** — the label `2026-11-25 03:00:00` changed while its hour ran (station 2 rain 0.001 at 03:18 UTC, 0.005 at 03:45; station 512 rain 0.004, 0.007; station 4 level 4.95 at 03:17, 4.97 at 03:45), and no later label had a value. The provider's day D runs from the label 06:00 of D to 05:00 of D+1: the site's daily total is their sum (station 1: 26.168 for 2026-11-23 from all 24 labels, 4.505 for 2026-11-24 from the 22 labels with a value at 03:17 UTC). Units only from the public tables (the API names none): conductivity's „mS/cm” contradicts its values, and the vertical datum of „m n.p.m.” is not published. A level is in metres above sea level, never IMGW-PIB's centimetres above a gauge zero. | 2026-11-20, 2026-11-25 | The repeated asks of 2026-11-25 (recorded cases `m_2_rain_20261124_at_031857` and `m_2_rain_20261124_at_034500`, `m_512_rain_20261124_at_031857` and `m_512_rain_20261124_at_034500`, `m_4_water_20261124_at_034500`); the site's tables „Opad”, „Wiatr / ciśnienie”, „Meteo - pozostałe”, „Jakość wód”, „Jakość wód - pozostałe”, „Stan wód” of 2026-11-25 with the totals of 22–24 November. |
| Quality | Raw and unverified, in the provider's words: „Uwaga: Prezentowane dane są danymi surowymi bez weryfikacji. Nie mogą być wykorzystane jako materiał dowodowy.” Revisions: the hour in progress changes until its hour ends; whether a closed hour is revised later is not stated (Obserwator fetches a month again until six hours after its last provider day, and `--force` asks it again later). No flags; a missing hour is `null`; values are JSON numbers, integers and floats mixed. | 2026-11-20, 2026-11-25 | The notice under every table and chart of the site on 2026-11-25; the documentation of 2026-11-20. |
| History | The earliest data are not published per station; a date before a station's start answers 24 `null`s. Found by bisection on 2026-11-20 (which assumes no long gaps, so a first date must come from the data): no. 1 `rain` 2005-06-15, no. 4 and no. 999 `water` 2015-10-16, no. 201 `water` 2017-12-18, no. 504 `flow` 2020-12-31. A full backfill is about 202 pairs × 10 years × 365 days ≈ 0.7 million requests (an estimate, not measured): about 200 hours (8 days) at least at Obserwator's default of one request a second; a year of every pair is about 74,000 requests (about 20 hours), and a month before a station's start is stored as answered (every hour `null`). It is too much without asking the provider first (`pomiary@gdanskiewody.pl`, P10, the plan's question 4); none was run. | 2026-11-20 | The plan's check of 2026-11-20 (rows „History” and „Speed”, the estimate below its table). |
| Overlap | None known: no station of the list is known to duplicate an IMGW-PIB or ČHMÚ gauge; not checked station by station. No merging; a cross-reference at most (the plan's rule). | 2026-11-25 | — |
| Not a source | The site's charts call `/measurments/json/<station>/<channel>/<0..2>` (sic) without a key: the last three days, values as texts, undocumented. Obserwator does not use it. | 2026-11-20 | The plan's check of 2026-11-20. |

## Quantities

Stations per symbol on 2026-11-25; the labels of the provider's public tables on 2026-11-25; Obserwator's variables (ADR-034 D3, D5).

| Symbol | Stations | Public tables' label | Hourly variable | Daily variable (rule) |
|---|---|---|---|---|
| `rain` | 40 | „Opad [mm]” | `P` [mm] | `P` (sum of 24) |
| `water` | 91 | „Maks. poziom wody [m n.p.m.]” (the day's maximum in the tables), „Poziom wody [m n.p.m.]” on the charts | `H_asl` [m] | `H_asl` (mean of 24) |
| `flow` | 2 | „Przepływ [m3/s]” | `Q` [m3/s] | `Q` (mean of 24) |
| `watertemp` | 3 | „Temp. wody [C]” | `T` [degC] | `T` (mean of 24) |
| `temp` | 16 | „Temperatura [C]” | `Tair` [degC] | `Tmean` (mean of 24) |
| `windlevel` | 7 | „Prędkość wiatru [m/s]” | `wind_speed` [m/s] | `wind_speed` (mean of 24) |
| `winddir` | 7 | „Kierunek wiatru”, compass points in the tables; the API gives degrees in steps of 22.5 (112.5 to 225 at station 91 on 2026-11-02 and 03) | `wind_direction` [deg] | — |
| `pressure` | 6 | „Ciśnienie [hPa]” | `pressure` [hPa] | `pressure` (mean of 24) |
| `humidity` | 13 | „Wilgotność [%]” | `humidity` [%] | `humidity` (mean of 24) |
| `sun` | 4 | „Nasłonecznienie [W/m2]” | `irradiance` [W/m2] | `irradiance` (mean of 24) |
| `turbidity` | 1 | „Mętność [FNU]” | — (kept in the month files) | — |
| `dissolvedoxygen` | 3 | „Tlen rozpuszczony [mg/l]” | — (kept) | — |
| `redox` | 3 | „Redoks ORP [mV]” | — (kept) | — |
| `ph` | 3 | „pH” | — (kept) | — |
| `conductivity` | 3 | „Przewodność [mS/cm]”, contradicted by its values: 343 to 648 in the answers of station 700 for 2026-11-01 to 03, up to 2,656 in the site's table of 2026-11-22 | — (kept; no unit claimed) | — |

A daily value is that of the provider's day, 06:00 of D to 05:59 of D+1 (UTC), rounded to three decimals and `missing` without all 24 hours; Obserwator's daily `H_asl` is the mean of the hours, not the day's maximum of the provider's tables.

## Errors

The answers of 2026-11-25, verbatim, and what Obserwator makes of them (ADR-034 D7):

| Code | Message | Meaning | Obserwator |
|---|---|---|---|
| `-100` | „Błąd uwierzytelniania. Więcej informacji: https://pomiary.gdanskiewody.pl/rest/” | authentication | `forbidden`, `details.reason` `invalid_credentials` (without a key: `missing_credentials`, before any request) |
| `-2` | „Błędny symbol parametru: foo” | unknown symbol | `validation_error`, `bad_request` |
| `-3` | „Błędna data: 2026-13-45”, „Błędna data: 20261103” | bad date | `validation_error`, `bad_request` |
| `-11` | „Nie znaleziono stacji o numerze: 3” | no such station | `not_found`, `unknown_station` |
| `-12` | not recorded (the documentation of 2026-11-20) | the station does not measure the quantity | `no_data`, `not_measured` |
| `-13` | „Stacja nie zbiera danych dot. poziomu wody” | the station does not measure the quantity | `no_data`, `not_measured` |
| any other | — | — | `source_unavailable`, `provider_error` |

## Terms, verbatim

Pending: the regulamin of pomiary.gdanskiewody.pl as accepted at signup, to be pasted here by the author (the plan's open question 1). It decides whether the data may be stored and served, the wording of the attribution line (Nogat DEV §20, P9), the publication default of `pl.gdanskiewody.measurements` (P15) and whether the provider can be served at all.

## Open questions

- For the provider (`pomiary@gdanskiewody.pl`): the regulamin's terms and the wording of the line; the vertical datum of the levels and the unit of conductivity; how each quantity is aggregated to the hour; whether a backfill of about 0.7 million requests is acceptable, at what rate, or a bulk export instead; whether closed hours are ever revised.
- For the author: the range of the first download, and the provider's default state once its terms are known.
