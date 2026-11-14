"""The station view: the map, its bar and legend, the station list, its search and filters, the current measurements („Pomiary bieżące”)."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    # The station list (src/list.js)
    "stations.list.search_placeholder": Text(
        "Name, river or code", "Nazwa, rzeka albo kod"
    ),
    "stations.list.search_label": Text(
        "Search stations by name, river or code",
        "Szukaj stacji po nazwie, rzece albo kodzie",
    ),
    "stations.list.provider": Text("Provider", "Dostawca"),
    "stations.list.provider_all": Text("All", "Wszyscy"),
    "stations.list.kind": Text("Station kind", "Rodzaj stacji"),
    "stations.list.kind_all": Text("All", "Wszystkie"),
    "stations.list.kind_hydro": Text("Hydrological", "Hydrologiczne"),
    "stations.list.kind_meteo": Text("Meteorological", "Meteorologiczne"),
    "stations.list.datasets": Text(
        "Series in the data root", "Szeregi w katalogu danych"
    ),
    "stations.list.active_only": Text("active only", "tylko czynne"),
    "stations.list.found.one": Text("station", "stacja"),
    "stations.list.found.few": Text("stations", "stacje"),
    "stations.list.found.many": Text("stations", "stacji"),
    "stations.list.found.other": Text("stations", "stacji"),
    "stations.list.on_map": Text("on the map {n}", "na mapie {n}"),
    "stations.list.unlocated": Text("without coordinates {n}", "bez współrzędnych {n}"),
    "stations.list.no_location": Text("no coordinates", "bez współrzędnych"),
    "stations.list.none": Text("No station matches.", "Żadna stacja nie pasuje."),
    "stations.list.clear": Text("Clear the filters", "Wyczyść filtry"),
    "stations.list.more": Text(
        "Show more ({count} of {rest})", "Pokaż kolejne ({count} z {rest})"
    ),
    "stations.catalog_only": Text("only in the catalog", "tylko w katalogu"),
    "stations.inactive": Text("inactive", "nieczynna"),
    # The map (src/map.js)
    "stations.map.label": Text("Station map", "Mapa stacji"),
    "stations.map.basemap_credit": Text("Basemap: {credit}", "Podkład mapy: {credit}"),
    "stations.map.failure": Text(
        "This browser does not draw the map", "Ta przeglądarka nie rysuje mapy"
    ),
    "stations.map.failure_rest": Text(
        "The station list, the station panel and the PMAXTP form still work.",
        "Lista stacji, panel stacji i formularz PMAXTP działają dalej.",
    ),
    "stations.map.zoom": Text("Map zoom", "Powiększenie mapy"),
    "stations.map.zoom_in": Text("Zoom in", "Przybliż"),
    "stations.map.zoom_out": Text("Zoom out", "Oddal"),
    # The tooltip of a point
    "stations.tip.series": Text("series {years}", "szeregi {years}"),
    "stations.tip.outdated": Text(
        "(state of the last 26 h)", "(stan z ostatnich 26 h)"
    ),
    "stations.tip.water_level": Text("Water level H", "Stan wody H"),
    "stations.tip.discharge": Text("Discharge Q", "Przepływ Q"),
    "stations.tip.water_temperature": Text("Water temperature", "Temperatura wody"),
    "stations.tip.no_values": Text(
        "IMGW-PIB gives no current measurements of this station.",
        "IMGW-PIB nie podaje teraz pomiarów tej stacji.",
    ),
    "stations.tip.precipitation": Text("Precipitation in 10 min", "Opad w 10 min"),
    "stations.tip.air_temperature": Text("Air temperature", "Temperatura powietrza"),
    "stations.tip.wind": Text("Wind (mean)", "Wiatr (średni)"),
    "stations.tip.humidity": Text("Relative humidity", "Wilgotność względna"),
    # hydro.imgw.pl's classes (src/symbols.js): its words, STATUSES.<class>Short
    "stations.state.alarm": Text("Above the alarm level", "Powyżej stanu alarmowego"),
    "stations.state.warning": Text(
        "Above the warning level", "Powyżej stanu ostrzegawczego"
    ),
    "stations.state.high": Text("High water zone", "Strefa stanów wysokich"),
    "stations.state.medium": Text("Medium water zone", "Strefa stanów średnich"),
    "stations.state.low": Text("Low water zone", "Strefa stanów niskich"),
    "stations.state.below": Text(
        "Below the periodic minimum", "Poniżej minimum okresowego"
    ),
    "stations.state.no_data": Text("No water level data", "Brak danych stanu wody"),
    "stations.state.unknown": Text(
        "No characteristic or conventional levels", "Brak stanów charakt. / umownych"
    ),
    "stations.precip.heavy": Text("Heavy precipitation", "Opad intensywny"),
    "stations.precip.some": Text("Precipitation", "Opad"),
    "stations.precip.none": Text("No precipitation", "Brak opadu"),
    "stations.precip.no_data": Text("No precipitation data", "Brak danych opadowych"),
    "stations.precip.heavy_note": Text(
        "at least heavy rain on Chomicz's scale, ≥ {mm} mm in 10 min",
        "co najmniej silny deszcz w skali Chomicza, ≥ {mm} mm w 10 min",
    ),
    "stations.precip.last_10_min": Text("in the last 10 min", "w ostatnich 10 min"),
    # The legend
    "stations.legend.title": Text("Legend", "Legenda"),
    "stations.legend.chmi": Text(
        "{provider} (dashed outline)", "{provider} (obrys przerywany)"
    ),
    "stations.legend.inactive": Text("inactive (faded)", "nieczynna (blado)"),
    "stations.legend.selected": Text("selected", "wybrana"),
    "stations.legend.stations_note": Text(
        "Station shapes and colours as on IMGW-PIB's map hydro.imgw.pl; the view "
        "“Current measurements” shows the water state and the precipitation.",
        "Kształty i kolory stacji jak na mapie hydro.imgw.pl (IMGW-PIB); stan wody "
        "i opad pokazuje widok „Pomiary bieżące”.",
    ),
    "stations.legend.hydro_title": Text(
        "Hydrological stations: water state", "Stacje hydrologiczne: stan wody"
    ),
    "stations.legend.hydro_note": Text(
        "Filled: the state of the measurements of the last 2 hours; hollow centre: "
        "of the last 26 hours.",
        "Pełny: stan z pomiarów ostatnich 2 godzin; pusty środek: z ostatnich "
        "26 godzin.",
    ),
    "stations.legend.meteo_title": Text(
        "Meteorological stations: precipitation in 10 min",
        "Stacje meteorologiczne: opad w 10 min",
    ),
    "stations.legend.meteo_note": Text(
        "Symbols and colours as on hydro.imgw.pl, which classes the precipitation of "
        "6 hours; IMGW-PIB's 6-hour class is not available here, so the latest "
        "10-minute total gives the class. Heavy: at least heavy rain on Chomicz's "
        "scale.",
        "Symbole i kolory jak na hydro.imgw.pl, które klasyfikuje opad z 6 godzin; "
        "klasa 6-godzinna IMGW-PIB jest tu niedostępna, więc klasę daje ostatnia "
        "suma 10-minutowa. Intensywny: co najmniej silny deszcz w skali Chomicza.",
    ),
    "stations.legend.loading": Text(
        "Fetching the current measurements from IMGW-PIB…",
        "Pobieram pomiary bieżące z IMGW-PIB…",
    ),
    "stations.legend.snapshot": Text(
        "IMGW-PIB snapshot of {time}: {hydro}, {meteo}; refreshed every {minutes} min, "
        "not stored.",
        "Migawka IMGW-PIB z {time}: {hydro}, {meteo}; odświeżana co {minutes} min, "
        "niezapisywana.",
    ),
    "stations.legend.hydro_count.one": Text(
        "{n} hydrological station", "{n} stacja hydrologiczna"
    ),
    "stations.legend.hydro_count.few": Text(
        "{n} hydrological stations", "{n} stacje hydrologiczne"
    ),
    "stations.legend.hydro_count.many": Text(
        "{n} hydrological stations", "{n} stacji hydrologicznych"
    ),
    "stations.legend.hydro_count.other": Text(
        "{n} hydrological stations", "{n} stacji hydrologicznej"
    ),
    "stations.legend.meteo_count.one": Text(
        "{n} meteorological", "{n} meteorologiczna"
    ),
    "stations.legend.meteo_count.few": Text(
        "{n} meteorological", "{n} meteorologiczne"
    ),
    "stations.legend.meteo_count.many": Text(
        "{n} meteorological", "{n} meteorologicznych"
    ),
    "stations.legend.meteo_count.other": Text(
        "{n} meteorological", "{n} meteorologicznej"
    ),
    "stations.legend.last_snapshot": Text(
        "(showing the last snapshot)", "(pokazuję ostatnią migawkę)"
    ),
    "stations.legend.pick": Text("PMAXTP point", "punkt PMAXTP"),
    "stations.legend.pmaxtp_note": Text(
        "Click the map within PMAXTP's bounds ({bounds}). The map draws no PMAXTP grid.",
        "Kliknij mapę w granicach PMAXTP ({bounds}). Mapa nie rysuje siatki PMAXTP.",
    ),
    "stations.legend.borders": Text(
        "Background: the state borders of Poland (PRG, GUGiK) and Czechia (RÚIAN, "
        "ČÚZK) from Obserwator's package.",
        "Tło: granice państwowe Polski (PRG, GUGiK) i Czech (RÚIAN, ČÚZK) z pakietu "
        "Obserwatora.",
    ),
    "stations.legend.basemap_failed": Text(
        "The basemap did not load: the background is the state borders of Poland "
        "(PRG, GUGiK) and Czechia (RÚIAN, ČÚZK) from Obserwator's package.",
        "Podkład mapy się nie wczytał: tło to granice państwowe Polski (PRG, GUGiK) i "
        "Czech (RÚIAN, ČÚZK) z pakietu Obserwatora.",
    ),
    # The snapshots of api/current, named where one fails
    "stations.source.states": Text(
        "water states (the map of hydro.imgw.pl)", "stany wody (mapa hydro.imgw.pl)"
    ),
    "stations.source.hydro": Text("hydrological measurements", "pomiary hydrologiczne"),
    "stations.source.meteo": Text(
        "meteorological measurements", "pomiary meteorologiczne"
    ),
}
