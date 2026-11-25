"""Messages of ``providers/pl/gdanskiewody.py`` (Gdańskie Wody, ADR-034)."""

from obserwator.messages import Text

MESSAGES = {
    # An error the provider reports in the body of an HTTP 200 answer (P4).
    "answer_error": Text(
        "Gdańskie Wody answered {url} with the error {code}: {text}",
        "Gdańskie Wody odpowiedziały na {url} błędem {code}: {text}",
    ),
    "no_station_list": Text(
        "The raw root {root} holds no station list of Gdańskie Wody ({dataset}): it "
        "names the stations and quantities of the month files",
        "Surowy magazyn {root} nie ma listy stacji Gdańskich Wód ({dataset}): to ona "
        "wskazuje stacje i wielkości plików miesięcznych",
    ),
    "files_from_station_list": Text(
        "The files of {key} are named by the station list a raw root holds: store "
        "check and store sync of a raw root give them",
        "Pliki zbioru {key} wskazuje lista stacji zapisana w surowym magazynie: podają "
        "je store check i store sync surowego magazynu",
    ),
    "station_not_listed": Text(
        "The station {code} is not on the station list of the raw root: sync "
        "pl.gdanskiewody.station_list, then its month files",
        "Stacji {code} nie ma na liście stacji surowego magazynu: zsynchronizuj "
        "pl.gdanskiewody.station_list, potem jej pliki miesięczne",
    ),
    "cancelled": Text(
        "The requests of Gdańskie Wody were cancelled",
        "Przerwano zapytania do Gdańskich Wód",
    ),
}
