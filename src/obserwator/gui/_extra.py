"""The ``gui`` extra: Starlette and uvicorn, imported only when the GUI is served."""

from __future__ import annotations

import importlib
from typing import Final

from obserwator.exceptions import ObserwatorError
from obserwator.messages import message

REQUIREMENTS: Final = ("starlette>=1.9,<2", "uvicorn[standard]>=0.24")
"""Requirements of the extra beside ``obserwator[store]``; ``pyproject.toml`` says the same."""
INSTALL_HINT: Final = 'pip install "obserwator[gui]"'
"""The command that installs the extra, as the ``missing_dependency`` error shows it."""
_MODULES: Final = ("starlette", "uvicorn", "pyarrow")


def require_gui_extra() -> None:
    """
    Raise ``missing_dependency`` unless Starlette, uvicorn and pyarrow import.

    Raises
    ------
    ObserwatorError
        With code ``missing_dependency`` when a package of the ``gui`` extra is
        missing; ``hint`` says how to install it.
    """
    for module in _MODULES:
        try:
            importlib.import_module(module)
        except ImportError as exc:
            raise ObserwatorError(
                message("gui.server.needs_extra", module=module),
                code="missing_dependency",
                details={"extra": "gui", "module": module},
                hint=INSTALL_HINT,
            ) from exc
