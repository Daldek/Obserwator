"""Messages of ``instance.py``: the section ``[obserwator.instance]`` (ADR-025)."""

from obserwator.messages import Text

MESSAGES = {
    "not_a_table": Text(
        "[obserwator.instance] must be a table of nogat.toml",
        "[obserwator.instance] musi być tabelą pliku nogat.toml",
    ),
    "unknown_field": Text(
        "[obserwator.instance] has no field {field}; its fields: {allowed}",
        "[obserwator.instance] nie ma pola {field}; jego pola: {allowed}",
    ),
    "not_text": Text(
        "{field} of [obserwator.instance] must be text",
        "{field} w [obserwator.instance] musi być tekstem",
    ),
    "bad_choice": Text(
        "{field} of [obserwator.instance] is {value}; allowed: {allowed}",
        "{field} w [obserwator.instance] ma wartość {value}; dozwolone: {allowed}",
    ),
    "providers_not_table": Text(
        "[obserwator.instance.providers] must be a table of provider identifiers",
        "[obserwator.instance.providers] musi być tabelą identyfikatorów dostawców",
    ),
    "unknown_provider": Text(
        "{provider} is no provider; the providers: {known}",
        "{provider} nie jest dostawcą; dostawcy: {known}",
    ),
    "featured_off": Text(
        "The featured provider {provider} is off in [obserwator.instance.providers]; "
        "a featured provider is visible or hidden",
        "Wyróżniony dostawca {provider} jest wyłączony (off) w "
        "[obserwator.instance.providers]; wyróżniony dostawca jest visible albo hidden",
    ),
    "nothing_served": Text(
        "Every provider is off and pmaxtp is off: the instance would serve nothing",
        "Każdy dostawca jest wyłączony i pmaxtp jest wyłączone: instancja nie "
        "udostępniałaby niczego",
    ),
    "start_needs_featured": Text(
        'start_view = "featured" needs featured_provider',
        'start_view = "featured" wymaga featured_provider',
    ),
    "start_needs_area": Text(
        'start_view = "area" needs area', 'start_view = "area" wymaga area'
    ),
    "mode_needs_area": Text(
        "area_mode needs area: without an area nothing is clipped",
        "area_mode wymaga area: bez obszaru nic nie jest przycinane",
    ),
    "opacity_needs_featured": Text(
        "others_opacity needs featured_provider: without it no station is faded",
        "others_opacity wymaga featured_provider: bez niego żadna stacja nie jest "
        "przygaszona",
    ),
    "bad_opacity": Text(
        "others_opacity of [obserwator.instance] is {value}; it must be a number from "
        "{minimum} to {maximum}",
        "others_opacity w [obserwator.instance] ma wartość {value}; musi być liczbą od "
        "{minimum} do {maximum}",
    ),
    "bad_title": Text(
        "title of [obserwator.instance] must be one line of 1 to {maximum} characters",
        "title w [obserwator.instance] musi być jednym wierszem o długości od 1 do "
        "{maximum} znaków",
    ),
    "file_missing": Text(
        "{field} of [obserwator.instance]: there is no file {path}",
        "{field} w [obserwator.instance]: nie ma pliku {path}",
    ),
    "file_unreadable": Text(
        "{field} of [obserwator.instance]: cannot read {path}: {reason}",
        "{field} w [obserwator.instance]: nie można odczytać {path}: {reason}",
    ),
    "file_too_large": Text(
        "{field} of [obserwator.instance]: {path} has more than {maximum} bytes",
        "{field} w [obserwator.instance]: {path} ma więcej niż {maximum} bajtów",
    ),
    "area_not_json": Text(
        "area of [obserwator.instance]: {path} is no JSON document: {reason}",
        "area w [obserwator.instance]: {path} nie jest dokumentem JSON: {reason}",
    ),
    "area_not_polygon": Text(
        "area of [obserwator.instance]: {path} holds {found}, not one Polygon or "
        "MultiPolygon (RFC 7946)",
        "area w [obserwator.instance]: {path} zawiera {found}, a nie jeden Polygon "
        "albo MultiPolygon (RFC 7946)",
    ),
    "area_bad_ring": Text(
        "area of [obserwator.instance]: {path} has a ring that is not closed or has "
        "fewer than 4 positions",
        "area w [obserwator.instance]: {path} ma pierścień, który nie jest zamknięty "
        "albo ma mniej niż 4 pozycje",
    ),
    "area_bad_position": Text(
        "area of [obserwator.instance]: {path} has a position {position} that is no "
        "longitude from -180 to 180 and latitude from -90 to 90 (WGS84, RFC 7946)",
        "area w [obserwator.instance]: {path} ma pozycję {position}, która nie jest "
        "długością od -180 do 180 i szerokością od -90 do 90 (WGS84, RFC 7946)",
    ),
    "area_crs": Text(
        "area of [obserwator.instance]: {path} names the coordinate system {crs}; "
        "only WGS84 longitude and latitude (RFC 7946) are read",
        "area w [obserwator.instance]: {path} wskazuje układ współrzędnych {crs}; "
        "odczytywane są tylko długość i szerokość WGS84 (RFC 7946)",
    ),
    "area_too_many_vertices": Text(
        "area of [obserwator.instance]: {path} has more than {maximum} vertices; "
        "simplify the polygon",
        "area w [obserwator.instance]: {path} ma więcej niż {maximum} wierzchołków; "
        "uprość wielokąt",
    ),
    "logo_type": Text(
        "logo of [obserwator.instance]: {path} is no PNG, WebP or SVG image (the type "
        "is read from the content)",
        "logo w [obserwator.instance]: {path} nie jest obrazem PNG, WebP ani SVG (typ "
        "jest odczytywany z zawartości)",
    ),
    "logo_svg_doctype": Text(
        "logo of [obserwator.instance]: {path} is SVG with a DOCTYPE or an entity, "
        "which is not read",
        "logo w [obserwator.instance]: {path} jest plikiem SVG z deklaracją DOCTYPE "
        "albo encją, których się nie odczytuje",
    ),
    "terms_not_text": Text(
        "terms of [obserwator.instance]: {path} is no UTF-8 text",
        "terms w [obserwator.instance]: {path} nie jest tekstem UTF-8",
    ),
    "terms_no_title": Text(
        "terms of [obserwator.instance]: {path} must start with its title line "
        '"# …" (remove the draft\'s opening comment)',
        "terms w [obserwator.instance]: {path} musi zaczynać się wierszem tytułu "
        "„# …” (usuń komentarz otwierający wzór)",
    ),
    "terms_bad_link": Text(
        "terms of [obserwator.instance]: {path} links to {href}; a link goes to an "
        "https://, http://, mailto: or # address or to a field of the template",
        "terms w [obserwator.instance]: {path} odsyła do {href}; odnośnik prowadzi do "
        "adresu https://, http://, mailto: albo # lub do pola wzoru",
    ),
    "terms_unfilled": Text(
        "terms of [obserwator.instance]: {path} cannot be filled for this deployment: "
        "{reason}",
        "terms w [obserwator.instance]: {path} nie da się wypełnić dla tego "
        "wdrożenia: {reason}",
    ),
    "empty_start": Text(
        'The start view "{view}" of [obserwator.instance] holds no station; the '
        "map starts on every station",
        'Widok startowy "{view}" z [obserwator.instance] nie obejmuje żadnej stacji; '
        "mapa startuje na wszystkich stacjach",
    ),
    "not_served": Text(
        "{provider} is not served by this instance",
        "{provider} nie jest udostępniany przez tę instancję",
    ),
    "pmaxtp_off": Text(
        "PMAXTP is not served by this instance",
        "PMAXTP nie jest udostępniane przez tę instancję",
    ),
    "outside_area": Text(
        "The point {latitude}, {longitude} lies outside the area of this instance",
        "Punkt {latitude}, {longitude} leży poza obszarem tej instancji",
    ),
    "station_not_served": Text(
        "No station {station} is served by this instance",
        "Ta instancja nie udostępnia stacji {station}",
    ),
    "clip_refused": Text(
        "{command} is not served by an instance that clips its area: its answer "
        "would hold stations outside the area",
        "{command} nie jest udostępniane przez instancję, która przycina swój obszar: "
        "odpowiedź zawierałaby stacje spoza obszaru",
    ),
    "provider_needed": Text(
        "Name one provider with {option}: this instance does not serve {off}",
        "Wskaż jednego dostawcę opcją {option}: ta instancja nie udostępnia {off}",
    ),
}
