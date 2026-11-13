"""The view „PMAXTP”: the point, the method, the tables and the files."""

from obserwator.messages import Text

MESSAGES: dict[str, Text] = {
    # The methods of the PMAXTP model
    "pmaxtp.method.pot.name": Text(
        "Peak Over Threshold", "Peak Over Threshold, wartości szczytowe powyżej progu"
    ),
    "pmaxtp.method.amp.name": Text(
        "Annual Max Precipitation", "Annual Max Precipitation, maksima roczne"
    ),
    "pmaxtp.method.pot.text": Text(
        "Peaks over a threshold: every rainfall event exceeding the threshold, whatever "
        "the year it occurred in. Recommended for analyses of the frequency of extreme "
        "events.",
        "Metoda wartości szczytowych powyżej progu: wszystkie zdarzenia opadowe "
        "przekraczające próg, niezależnie od roku wystąpienia. Zalecana do analiz "
        "częstości zdarzeń ekstremalnych.",
    ),
    "pmaxtp.method.amp.text": Text(
        "Annual maxima: only the largest rainfall of each year of the measurement "
        "series. Used in traditional hydrological analyses.",
        "Metoda rocznych wartości maksymalnych: tylko największy opad każdego roku "
        "serii pomiarowej. Stosowana w tradycyjnych analizach hydrologicznych.",
    ),
    # The form of the left panel
    "pmaxtp.form.hint": Text(
        "Click a point on the map or type its coordinates: the panel on the right will "
        "show IMGW-PIB's PMAXTP probable maximum precipitation for that place.",
        "Kliknij punkt na mapie albo wpisz jego współrzędne: panel po prawej pokaże "
        "opady maksymalne prawdopodobne PMAXTP IMGW-PIB dla tego miejsca.",
    ),
    "pmaxtp.form.method": Text("Method", "Metoda"),
    "pmaxtp.form.method_label": Text("PMAXTP method", "Metoda PMAXTP"),
    "pmaxtp.form.latitude": Text("Latitude [° N]", "Szerokość [° N]"),
    "pmaxtp.form.longitude": Text("Longitude [° E]", "Długość [° E]"),
    "pmaxtp.form.example": Text("e.g. {value}", "np. {value}"),
    "pmaxtp.form.bounds": Text(
        "Range: {bounds} (the bounds of {function}); IMGW-PIB answers for the points "
        "of its grid in Poland. The point is rounded to 4 decimal places, as in the "
        "address of IMGW-PIB's API.",
        "Zakres: {bounds} (granice {function}); IMGW-PIB odpowiada dla punktów swojej "
        "siatki w Polsce. Punkt jest zaokrąglany do 4 miejsc po przecinku, jak w "
        "adresie API IMGW-PIB.",
    ),
    "pmaxtp.form.error_number": Text(
        "Enter the latitude and the longitude in decimal degrees.",
        "Podaj szerokość i długość geograficzną w stopniach dziesiętnych.",
    ),
    "pmaxtp.form.error_outside": Text(
        "The point {point} lies outside the range of PMAXTP: {bounds}.",
        "Punkt {point} leży poza zakresem PMAXTP: {bounds}.",
    ),
    "pmaxtp.form.submit": Text("Show results", "Pokaż wyniki"),
    "pmaxtp.form.places": Text("Example places", "Przykładowe miejsca"),
    "pmaxtp.form.methods": Text("Methods", "Metody"),
    "pmaxtp.place.warsaw": Text("Warsaw", "Warszawa"),
    "pmaxtp.place.krakow": Text("Krakow", "Kraków"),
    "pmaxtp.place.gdansk": Text("Gdansk", "Gdańsk"),
    "pmaxtp.place.wroclaw": Text("Wroclaw", "Wrocław"),
    "pmaxtp.place.poznan": Text("Poznan", "Poznań"),
    # The tables of the answer
    "pmaxtp.table.ks.label": Text("Quantiles", "Kwantyle"),
    "pmaxtp.table.ks.title": Text(
        "Quantiles of maximum precipitation [{unit}].",
        "Kwantyle opadu maksymalnego [{unit}].",
    ),
    "pmaxtp.table.sg.label": Text("Upper bound", "Górna granica"),
    "pmaxtp.table.sg.title": Text(
        "Upper bounds of the confidence interval of the quantiles [{unit}].",
        "Górne granice przedziału ufności kwantyli [{unit}].",
    ),
    "pmaxtp.table.rb.label": Text("Estimation error", "Błąd estymacji"),
    "pmaxtp.table.rb.title": Text(
        "Estimation errors of the quantiles [{unit}].",
        "Błędy estymacji kwantyli [{unit}].",
    ),
    # The results panel
    "pmaxtp.result.empty": Text(
        "Click a point on the map or type coordinates on the left: PMAXTP tables of "
        "that place and the files to download will appear here. The map draws no "
        "PMAXTP grid.",
        "Kliknij punkt na mapie albo wpisz współrzędne po lewej: tu pojawią się tabele "
        "PMAXTP tego miejsca i pliki do pobrania. Mapa nie rysuje siatki PMAXTP.",
    ),
    "pmaxtp.result.loading": Text(
        "Fetching PMAXTP from IMGW-PIB for {point} ({method})…",
        "Pobieram PMAXTP z IMGW-PIB dla {point} ({method})…",
    ),
    "pmaxtp.result.method": Text("Method", "Metoda"),
    "pmaxtp.result.point": Text("Point", "Punkt"),
    "pmaxtp.result.fetched": Text("IMGW-PIB's answer", "Odpowiedź IMGW-PIB"),
    "pmaxtp.result.cache": Text(
        "kept in the server's memory for up to 24 h, never stored",
        "w pamięci serwera do 24 h, niezapisywana",
    ),
    "pmaxtp.result.table_label": Text("PMAXTP table", "Tabela PMAXTP"),
    "pmaxtp.result.axes": Text(
        "Rows: rainfall duration t [min]; columns: exceedance probability p [%].",
        "Wiersze: czas trwania opadu t [min]; kolumny: prawdopodobieństwo "
        "przewyższenia p [%].",
    ),
    "pmaxtp.result.monograph": Text(
        "Monograph of the PMAXTP project (Open Access, CC BY 4.0):",
        "Monografia projektu PMAXTP (Open Access, CC BY 4.0):",
    ),
    "pmaxtp.result.monograph_link": Text(
        "PDF on IMGW-PIB's website", "PDF w serwisie IMGW-PIB"
    ),
    "pmaxtp.result.downloads": Text("Download", "Pobierz"),
    "pmaxtp.result.files": Text(
        "The server packs the files from IMGW-PIB's API answer for this point: three "
        "tables (ks, sg, rb), durations × probabilities ({durations} × "
        "{probabilities}). CSV: UTF-8, comma, decimal point, with the lines above and "
        "the terms in the columns attribution and terms_notice, one per row from the "
        "first data row; JSON: the document obserwator-pmaxtp-export/1 with the units "
        "and the fields attribution and terms_notice.",
        "Pliki składa serwer z odpowiedzi API IMGW-PIB dla tego punktu: trzy tabele "
        "(ks, sg, rb), czasy trwania × prawdopodobieństwa ({durations} × "
        "{probabilities}). CSV: UTF-8, przecinek, kropka dziesiętna, w kolumnach "
        "attribution i terms_notice powyższe linie i regulamin, po jednej w wierszu od "
        "pierwszego wiersza danych; JSON: dokument obserwator-pmaxtp-export/1 z "
        "jednostkami i polami attribution i terms_notice.",
    ),
    "pmaxtp.result.source_link": Text(
        "IMGW-PIB's API answer (JSON)", "Odpowiedź API IMGW-PIB (JSON)"
    ),
    "pmaxtp.result.source_note": Text(
        "this point straight from IMGW-PIB's service. IMGW-PIB publishes no PMAXTP "
        "files at a point's address: its page",
        "ten punkt wprost z serwisu IMGW-PIB. IMGW-PIB nie publikuje plików PMAXTP pod "
        "adresem punktu: jego strona",
    ),
    "pmaxtp.result.source_note_end": Text(
        "builds the files in the browser from the same answer.",
        "składa pliki w przeglądarce z tej samej odpowiedzi.",
    ),
}
