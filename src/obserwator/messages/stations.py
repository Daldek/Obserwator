"""Messages of ``stations.py``."""

from obserwator.messages import Text

MESSAGES = {
    "unknown_kind_station_allowed_hydro": Text(
        "Unknown kind of station: {kind!r}; allowed: hydro, meteo",
        "Nieznany rodzaj stacji: {kind!r}; dozwolone hydro, meteo",
    ),
    "unknown_source_station_list_allowed": Text(
        "Unknown source of the station list: {source!r}; allowed: live, store",
        "Nieznane źródło listy stacji: {source!r}; dozwolone live, store",
    ),
    "search_store_source_store_needs": Text(
        "A search in the store (source=store) needs the store directory root",
        "Wyszukiwanie w magazynie (source=store) wymaga katalogu magazynu root",
    ),
    "store_directory_root_allowed_only": Text(
        "The store directory root is allowed only with source=store",
        "Katalog magazynu root jest dozwolony tylko przy source=store",
    ),
    "no_station_catalog": Text(
        "The data root holds no station catalog of {providers}",
        "Katalog danych nie zawiera katalogu stacji dostawców: {providers}",
    ),
    "station_search_phrase_must_not": Text(
        "The station search phrase must not be empty",
        "Fraza wyszukiwania stacji nie może być pusta",
    ),
    "bbox_needs_four_numbers": Text(
        "bbox must be four numbers west,south,east,north (WGS84 degrees); got {bbox}",
        "bbox musi być czterema liczbami zachód,południe,wschód,północ (stopnie "
        "WGS84); podano {bbox}",
    ),
    "bbox_out_of_range": Text(
        "bbox {bbox} is out of range: longitudes (west, east) must lie within "
        "-180..180 and latitudes (south, north) within -90..90",
        "bbox {bbox} poza zakresem: długości (zachód, wschód) muszą leżeć w "
        "-180..180, a szerokości (południe, północ) w -90..90",
    ),
    "bbox_inverted": Text(
        "bbox {bbox} is inverted: west must not exceed east, nor south exceed north",
        "bbox {bbox} jest odwrócony: zachód nie może przekraczać wschodu ani "
        "południe północy",
    ),
    "unreadable_listing_no_file": Text(
        "Unreadable listing {url}: no file {newest}",
        "Nieczytelny listing {url}: brak pliku {newest}",
    ),
    "unexpected_response_from_list_stations": Text(
        "Unexpected response from {url}: a list of stations was expected",
        "Nieoczekiwana odpowiedź z {url}: oczekiwano listy stacji",
    ),
    "details_cancelled": Text(
        "The download of hydro.imgw.pl's station details was cancelled",
        "Przerwano pobieranie szczegółów stacji z hydro.imgw.pl",
    ),
}
