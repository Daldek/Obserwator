"""Messages of ``config.py``."""

from obserwator.messages import Text

MESSAGES = {
    "cannot_use_settings_file": Text(
        "Cannot use the settings file {path}: {error}",
        "Nie można użyć pliku ustawień {path}: {error}",
    ),
    "short_secret": Text(
        "{name} is shorter than {minimum} bytes; give a random key of at least "
        "{minimum} bytes (e.g. openssl rand -hex 32)",
        "{name} jest krótszy niż {minimum} bajtów; podaj losowy klucz o długości co "
        "najmniej {minimum} bajtów (np. openssl rand -hex 32)",
    ),
    "secret_file_mode": Text(
        "{name} names a file that group or others may access (mode {mode}); make it "
        "0600, owned by the service's user",
        "{name} wskazuje plik, do którego mają dostęp grupa lub inni (tryb {mode}); "
        "ustaw tryb 0600 i właściciela: użytkownika usługi",
    ),
    "secret_refused": Text(
        "{problem}. With [obserwator.instance] the server does not start with a "
        "weak key or token (ADR-025).",
        "{problem}. Z sekcją [obserwator.instance] serwer nie uruchamia się ze "
        "słabym kluczem ani tokenem (ADR-025).",
    ),
    "api_keys_deprecated": Text(
        "{path} holds the REST API keys of obserwator admin, which nothing checks; "
        "the command and the file are removed in v4.0.0. Delete the file: REST "
        "writes use OBSERWATOR_STORE_WRITE_TOKEN or OBSERWATOR_STORE_WRITE_TOKEN_FILE.",
        "{path} zawiera klucze REST API polecenia obserwator admin, których nic nie "
        "sprawdza; polecenie i plik znikają w v4.0.0. Usuń plik: zapisy przez REST "
        "używają OBSERWATOR_STORE_WRITE_TOKEN albo OBSERWATOR_STORE_WRITE_TOKEN_FILE.",
    ),
    "unknown_layout": Text(
        "The root {root} has a layout this Obserwator {version} does not read: "
        "{problems}",
        "Katalog {root} ma układ, którego ten Obserwator {version} nie odczytuje: "
        "{problems}",
    ),
    "unknown_layout_hint": Text(
        "Install the Obserwator release that wrote the root (git tag), or serve a "
        "root of the layout {schema}",
        "Zainstaluj wydanie Obserwatora, które zapisało katalog (tag git), albo "
        "wskaż katalog w układzie {schema}",
    ),
}
