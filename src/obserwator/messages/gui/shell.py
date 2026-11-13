"""The page's shell: the top bar, the views, the theme, the language and the footer."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    "shell.view_stations": Text("Stations", "Stacje"),
    "shell.view_current": Text("Current measurements", "Pomiary bieżące"),
}
