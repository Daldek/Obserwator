# Obserwator — przewodnik dla agentów (wersja <!-- obserwator:version -->)

> Plik generowany z katalogu komend: `obserwator commands guide --format agents --lang pl`. Nie edytuj ręcznie.

## Czym jest Obserwator

Obserwator to biblioteka Pythona, CLI `obserwator`, REST API i serwer MCP do publicznych danych hydrologicznych i meteorologicznych. Archiwa trafiają do wersjonowanego katalogu surowego (niezmienne wersje, tożsamość to SHA-256) albo do zwykłych plików; z niego powstają w katalogu danych szeregi, katalogi stacji i analizy, czytane offline.

Czyta archiwalne i bieżące dane stacji poniższych dostawców, lokalne kopie i opady maksymalne PMAXTP. Nieobsługiwane: prognozy, klimatyczne `now` i `recent` ČHMÚ, PMAXTP poza Polską. Instalacja: `pip install obserwator[cli]` (`[mcp]` dodaje serwer MCP, `[store]` szeregi Parquet).

<!-- obserwator:providers -->

## Zasady: sprawdź → uruchom → przeczytaj

<!-- obserwator:rules -->

## Interfejsy

| Interfejs | Wynik | Błąd |
|---|---|---|
| Python | `CommandResult` (`to_json()`) | `ObserwatorError` (`code`, `detail`, `hint`, `details`); `obserwator.error_report.error_report(exc).to_dict()` = dokument błędu |
| CLI `obserwator` | `--json`: koperta JSON w jednej linii stdout (bez niego podsumowanie dla człowieka) | ostatnia linia stderr: dokument błędu `obserwator-error/1`; kod wyjścia |
| REST `/api/v1` | 200 + koperta, także dla `partial` i `failed` | `application/problem+json` (z `hint`) |
| MCP | `structuredContent` = koperta | `isError: true` + dokument błędu `obserwator-error/1` |

Ta sama komenda w każdym interfejsie: CLI `obserwator <grupa> <komenda> --opcja wartość --json` (flaga: `--` + nazwa opcji, `-` zamiast `_`); Python `run_command("<grupa> <komenda>", options={...})`; REST `/api/v1/<grupa>/<komenda>` (GET: parametry zapytania, POST: ciało JSON); narzędzie MCP `obserwator_<grupa>_<komenda>`.

- **REST:** katalogi ustawia serwer (`OBSERWATOR_ROOT`, `OBSERWATOR_RAW_ROOT`); bez opcji lokalnych; zapis (POST bez `?check=true`) wymaga włączenia na serwerze i `X-API-Key`.
- **MCP:** `obserwator mcp` (stdio): komendy zapisujące tylko planują (`check` stałe `true`), dopóki użytkownik nie włączy zapisu (`--allow-writes`); wtedy `check` nadal domyślnie `true`. `/mcp` serwera REST (`OBSERWATOR_MCP_ENABLED=true`) tylko czyta i planuje.
- **Język:** wynik maszynowy jest po angielsku; polski na prośbę: `--lang pl` (`commands list|schema|guide`, poza nimi podsumowanie CLI bez `--json`), `lang: "pl"` (MCP), `Accept-Language: pl` (REST).

## Koperta, statusy i błędy

Komenda zwraca kopertę `obserwator-result/1` `{schema, tool, version, command, check, status, result, attribution, terms_notice, notices}`: `result` to dokument z własnym `schema` (`obserwator-<rodzaj>/1`), ich lista albo null; `attribution` i `terms_notice` przychodzą z danymi dostawców; `notices` to `{level, code, message}`. W komendach listowych `result` to lista, a koperta ma `page` `{total, next_cursor, truncated}`: dopóki `truncated`, podaj `next_cursor` jako `cursor`. Strumień bez `output` daje same linie danych: na stdout CLI (z `--json` i bez) albo jako załącznik REST (nagłówki `X-Obserwator-Status`, `X-Obserwator-Notices`).

<!-- obserwator:statuses -->

Błąd ma kod z zamkniętego rejestru, ten sam w każdym interfejsie; `details.option` wskazuje błędną opcję. Kody (kod wyjścia CLI/status HTTP; `—`: nigdy): <!-- obserwator:errors -->.

## Zbiory danych

Klucz zbioru ma postać `<kraj>.<dostawca>.<zbiór>`; slug (`imgw_hydro_daily`) i alias legacy (`hydro/dobowe`) — tylko na wejściu. Zbiory magazynu:

<!-- obserwator:datasets -->

- `stations`: WIGOS (wymagane dla `cz.chmu.*`), 9 cyfr (`pl.imgw.meteo_synop_*`) albo `GDANSKIEWODY-<nr>` z zapisanej listy `pl.gdanskiewody.station_list`, dwa ostatnie opcjonalne w `store check|sync`; jeden rodzaj plików na wywołanie.
- `years`: wymagane w `datasets files|download` i, dla `pl.*`, w `store check|sync`; tam opcjonalne dla `cz.chmu.*` (brak = opublikowane); nigdy dla `cz.chmu.{meteo_daily,groundwater_characteristic}`; nie przed „Od roku”. `months` tylko dla `pl.*`, `params` tylko dla `pl.imgw.hydro_semiannual`.

## Komendy

Jedna linia na komendę, według skutku; szczegóły: `obserwator commands schema --command "<komenda>" --json`. Znaczniki: `[output: …]` — opcja zapisuje plik; `[jest sprawdzeniem]` — komenda sama planuje; `[lokalna]` — bez trasy REST.

<!-- obserwator:commands -->

## Flagi i wartości

<!-- obserwator:flags -->

## Typowe przepływy

`KOD_STACJI` i `KOD_WIGOS` zastąp wartościami z poprzednich kroków.

<!-- obserwator:flows -->

## Czego nie robić

1. Nie składaj ani nie przeszukuj URL-i serwerów dostawców — `datasets files|download`, `store sync`.
2. Kody wyjścia 10 i 11 to nie awaria programu — czytaj kopertę.
3. Nie uruchamiaj zapisu (`store sync`, `series build`, `datasets download`) bez planu i zgody użytkownika.
4. Nie zgaduj stacji ani zbioru: przy kilku trafieniach `stations find` zapytaj; obecność stacji w zbiorze sprawdź `series summary`.
5. Nie edytuj, nie przenoś ani nie usuwaj plików magazynu — tylko rośnie.
6. Nie pobieraj „na zapas”: zawężaj `years`, `months` i `stations`.
7. Długie listy czytaj stronami (`limit`, `cursor`); używaj `series read` albo `series export --output`, nie CSV w kontekście.
8. Nie odpytuj `current …` w pętli — to API na żywo; zachowaj wynik.
9. Pokazuj linie `attribution` i `terms_notice` dosłownie z danymi i w tym, co z nich zrobisz (także komunikat `license_terms`).
10. `version` wskazuj tylko pod `*/versions/` katalogu, bez `..`; w REST i MCP przez HTTP względnie do katalogu komendy.

Rozwijasz to repozytorium? Przeczytaj CLAUDE.md.
