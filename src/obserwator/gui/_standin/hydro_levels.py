"""The ids of „Stany charakterystyczne”, „Krzywa natężenia przepływu” and „Przepływy maksymalne i minimalne” (``local://gui-calls-hydro-levels.md``)."""

from __future__ import annotations

from obserwator.gui._standin import HALF_YEARS, HYDRO_DAILY, PERIOD, Spec


def _daily(variable: str) -> dict[str, object]:
    return {"value_column": variable, "date_column": "date"}


SPECS: list[Spec] = [
    *(
        Spec(
            f"characteristic.{variable}",
            "stats characteristic",
            ("hydro",),
            {"input_file": HYDRO_DAILY},
            {"input_file": variable},
            {**_daily(variable), "parameter": variable},
            PERIOD,
        )
        for variable in ("H", "Q", "T")
    ),
    *(
        Spec(
            f"characteristic.{variable}.half_years",
            "stats characteristic",
            ("hydro",),
            {"half_year_file": HALF_YEARS},
            {"half_year_file": variable},
            {"parameter": variable},
            PERIOD,
        )
        for variable in ("H", "Q", "T")
    ),
]
