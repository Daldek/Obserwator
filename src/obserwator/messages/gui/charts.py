"""The charts: axes, readout, zoom, the image and table files."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    "charts.axis.return_period": Text("T [years]", "T [lata]"),
    "charts.readout.probability": Text(
        "p = {p} % · T = {years} years", "p = {p} % · T = {years} lat"
    ),
    "charts.keys.readout": Text(
        "Left and right arrows: read the values; Shift or Page Up and Page Down: "
        "ten steps; Home, End: the first and the last; Esc: hide the readout.",
        "Strzałki w lewo i w prawo: odczyt wartości; Shift albo Page Up i Page Down: "
        "dziesięć kroków; Home, End: początek i koniec; Esc: ukryj odczyt.",
    ),
    "charts.keys.zoom": Text(
        "Plus and minus: zoom in and out; 0: the whole chart; drag over the plot "
        "with the mouse to show a range.",
        "Plus i minus: przybliż i oddal; 0: cały wykres; przeciągnij myszą po "
        "wykresie, aby pokazać zakres.",
    ),
    "charts.zoom.reset": Text("Show all", "Pokaż całość"),
    "charts.zoom.range": Text("Shown: {from} – {to}", "Widoczne: {from} – {to}"),
    "charts.export.image_failed": Text(
        "The browser could not draw the chart as an image.",
        "Przeglądarka nie zdołała zapisać wykresu jako obrazu.",
    ),
}
