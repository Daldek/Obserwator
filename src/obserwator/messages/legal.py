"""
Names and formulas that keep their wording in every language.

The attribution lines and the terms lines are the only source of the texts the data
providers require (ADR-012, Nogat DEV §20): they are persisted in sidecars, series,
catalogs, PMAXTP cells and exports and printed on every surface with provider data,
and their wordings are prescribed (the IMGW-PIB terms, the PMAXTP terms, CC BY 4.0
of ČHMÚ and of ČÚZK, GUGiK's conditions of reuse), so a file must not depend on the
language of the person or program that wrote it; an institution has one official name.
The Polish text is the English one by design (the guard test allows it for this area
only).
"""

from obserwator.messages import Text

_IMGW_NAME = "Instytut Meteorologii i Gospodarki Wodnej – Państwowy Instytut Badawczy"
_IMGW_PROCESSED = (
    "Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu "
    "Badawczego zostały przetworzone"
)
_PMAXTP_PAGE = "https://klimat.imgw.pl/opady-maksymalne"
_PMAXTP_PROCESSED = (
    "Dane Instytutu Meteorologii i Gospodarki Wodnej – Państwowego Instytutu "
    f"Badawczego pochodzące ze strony {_PMAXTP_PAGE} zostały przetworzone"
)
_PMAXTP_MONOGRAPH = (
    "„Modele probabilistyczne opadów maksymalnych o określonym czasie trwania i "
    "prawdopodobieństwie przewyższenia – Projekt PMAXTP”, red. Bogdan Ozga-Zieliński, "
    f"{_IMGW_NAME}, Warszawa 2022"
)
_CHMU_ATTRIBUTION = (
    "Źródło danych: Český hydrometeorologický ústav (ČHMÚ), https://opendata.chmi.cz, "
    "licencja CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)"
)
# CP never names the processing (ECO-071); `obserwator.attribution` reads an older
# „Dane ČHMÚ zostały przetworzone (…)” as this line.
_CHMU_PROCESSED = "Dane ČHMÚ zostały przetworzone"
_GUGIK_ATTRIBUTION = (
    "Źródło: Główny Urząd Geodezji i Kartografii – GUGiK, {products} (wytworzono "
    "{period}, pozyskano {date}); dane przetworzone"
)
_CUZK_ATTRIBUTION = (
    "Źródło: Český úřad zeměměřický a katastrální (ČÚZK), {products} (pozyskano "
    "{date}), licencja CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/); "
    "dane przetworzone"
)
_TERMS_DANEPUBLICZNE = (
    "Regulamin danych IMGW-PIB: https://danepubliczne.imgw.pl/regulations"
)
_TERMS_HYDRO = (
    "Regulamin serwisu hydrologicznego IMGW-PIB: https://hydro.imgw.pl/#/regulamin"
)
_TERMS_PMAXTP = f"Regulamin danych PMAXTP: {_PMAXTP_PAGE}"
# Gdańskie Wody's lines are drafts (ADR-034): its regulamin is shown only to a
# signed-in user, so neither the wording it requires nor its terms are known (the
# providers plan's question 1, P9). `obserwator.attribution.provisional` marks them, and
# no server serves the data they come with until the provider's terms replace them.
_GDANSKIEWODY_SHORT = "Gdańskie Wody"
_GDANSKIEWODY_NAME = f"{_GDANSKIEWODY_SHORT} Sp. z o.o."
_GDANSKIEWODY_ATTRIBUTION = (
    f"Źródło danych: {_GDANSKIEWODY_NAME}, https://pomiary.gdanskiewody.pl "
    "(brzmienie robocze do czasu poznania regulaminu dostawcy)"
)
_GDANSKIEWODY_PROCESSED = "Dane Gdańskich Wód zostały przetworzone"
_TERMS_GDANSKIEWODY = (
    "Regulamin pomiary.gdanskiewody.pl: nieznany, widoczny tylko po zalogowaniu "
    "(https://pomiary.gdanskiewody.pl/login)"
)
# PIG-PIB (ADR-035): W, WP and the terms line RW of Nogat DEV-20.13, quoted from the
# table of provider lines; `obserwator.attribution` fills W's ``period`` (the years of
# the readings or hours of a product) and ``date`` (the days of the captures it read).
_PIG_SHORT = "PIG-PIB"
_PIG_NAME = "Państwowy Instytut Geologiczny – Państwowy Instytut Badawczy"
_PIG_ATTRIBUTION = (
    f"Źródło danych: {_PIG_NAME} ({_PIG_SHORT}), Monitoring Wód Podziemnych państwowej "
    "służby geologicznej (wytworzono {period}, pozyskano {date}), licencja CC BY 4.0 "
    "(https://creativecommons.org/licenses/by/4.0/)"
)
_PIG_PROCESSED = "Dane PIG-PIB zostały przetworzone"
_TERMS_PIG = (
    "Regulamin danych PIG-PIB: "
    "https://www.pgi.gov.pl/rejestry-i-bazy-danych-geologicznych/zasady-korzystania-z-isp.html"
)

RETIRED_LINES = (
    "Dane pochodzą z serwisu hydrologicznego IMGW-PIB https://hydro.imgw.pl",
    "Dane IMGW-PIB można wykorzystywać nieodpłatnie do celów prywatnych "
    "(niezarobkowych). Wykorzystanie w działalności gospodarczej, na stronach z "
    "reklamami lub do celów wymienionych w regulaminie (m.in. planowanie w "
    "gospodarowaniu wodami, art. 317 Prawa wodnego) wymaga umowy z IMGW-PIB.",
    "Regulamin: https://danepubliczne.imgw.pl/regulations",
    "Regulamin: https://hydro.imgw.pl/#/regulamin",
    f"Regulamin: {_PMAXTP_PAGE}",
)
"""
Lines of earlier versions of Nogat DEV §20 that ECO-065 retired: H (the line of
hydro.imgw.pl), N (a summary of the IMGW-PIB terms) and the terms lines before they
named their terms. Series, catalogs and analyses stored before hold them; a reader never
carries them on (`obserwator.attribution`).
"""

MESSAGES = {
    "imgw_name": Text(_IMGW_NAME, _IMGW_NAME),
    # S and P of DEV-20.1 (IMGW-PIB data other than PMAXTP).
    "imgw_attribution": Text(
        f"Źródłem pochodzenia danych jest {_IMGW_NAME}",
        f"Źródłem pochodzenia danych jest {_IMGW_NAME}",
    ),
    "imgw_processed_attribution": Text(_IMGW_PROCESSED, _IMGW_PROCESSED),
    # PS, PP and M of DEV-20.2 (PMAXTP data).
    "pmaxtp_attribution": Text(
        f"Źródłem pochodzenia danych jest {_IMGW_NAME}, dane pochodzą ze strony "
        f"{_PMAXTP_PAGE}",
        f"Źródłem pochodzenia danych jest {_IMGW_NAME}, dane pochodzą ze strony "
        f"{_PMAXTP_PAGE}",
    ),
    "pmaxtp_processed_attribution": Text(_PMAXTP_PROCESSED, _PMAXTP_PROCESSED),
    "pmaxtp_monograph": Text(_PMAXTP_MONOGRAPH, _PMAXTP_MONOGRAPH),
    # C and CP of DEV-20.3 (ČHMÚ data, CC BY 4.0).
    "chmu_attribution": Text(_CHMU_ATTRIBUTION, _CHMU_ATTRIBUTION),
    "chmu_processed_attribution": Text(_CHMU_PROCESSED, _CHMU_PROCESSED),
    # G of DEV-20.9 and Z of DEV-20.11 (GUGiK and ČÚZK data: the packaged state borders,
    # ADR-018); `obserwator.attribution` fills in the products and days of the files.
    "gugik_attribution": Text(_GUGIK_ATTRIBUTION, _GUGIK_ATTRIBUTION),
    "cuzk_attribution": Text(_CUZK_ATTRIBUTION, _CUZK_ATTRIBUTION),
    # The terms lines RD, RH, RK of DEV-20.7 (every product with IMGW-PIB data).
    "imgw_terms_danepubliczne": Text(_TERMS_DANEPUBLICZNE, _TERMS_DANEPUBLICZNE),
    "imgw_terms_hydro": Text(_TERMS_HYDRO, _TERMS_HYDRO),
    "imgw_terms_pmaxtp": Text(_TERMS_PMAXTP, _TERMS_PMAXTP),
    # Gdańskie Wody's names (ADR-034), then its line, processed line and terms line:
    # drafts until its terms give their wording (Nogat DEV §20 holds no row of it, P9).
    "gdanskiewody_name": Text(_GDANSKIEWODY_NAME, _GDANSKIEWODY_NAME),
    "gdanskiewody_short_name": Text(_GDANSKIEWODY_SHORT, _GDANSKIEWODY_SHORT),
    "gdanskiewody_attribution": Text(
        _GDANSKIEWODY_ATTRIBUTION, _GDANSKIEWODY_ATTRIBUTION
    ),
    "gdanskiewody_processed_attribution": Text(
        _GDANSKIEWODY_PROCESSED, _GDANSKIEWODY_PROCESSED
    ),
    "gdanskiewody_terms": Text(_TERMS_GDANSKIEWODY, _TERMS_GDANSKIEWODY),
    # PIG-PIB's names, W (with its period and date filled per product), WP and RW of
    # Nogat DEV-20.13 (ADR-035).
    "pig_name": Text(_PIG_NAME, _PIG_NAME),
    "pig_short_name": Text(_PIG_SHORT, _PIG_SHORT),
    "pig_attribution": Text(_PIG_ATTRIBUTION, _PIG_ATTRIBUTION),
    "pig_processed_attribution": Text(_PIG_PROCESSED, _PIG_PROCESSED),
    "pig_terms": Text(_TERMS_PIG, _TERMS_PIG),
}
