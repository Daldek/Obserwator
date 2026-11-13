"""What one GUI app holds while it runs, shared by its routes (``request.app.state.gui``)."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from obserwator._version import __version__
from obserwator.gui._config import GuiConfig

if TYPE_CHECKING:
    from obserwator.gui._analyses import Analyses
    from obserwator.gui._feedback import Feedback
    from obserwator.gui._live import CurrentData, Pmaxtp
    from obserwator.gui._root import DataRoot
    from obserwator.gui._traffic import TrafficState


@dataclass
class GuiState:
    """
    The parts of a running GUI app.

    Attributes
    ----------
    config : GuiConfig
        The resolved settings.
    root : DataRoot
        The data root, read only.
    analyses : Analyses
        Stored results and computations on request.
    current : CurrentData
        Snapshots of IMGW-PIB's current data.
    pmaxtp : Pmaxtp
        PMAXTP of points.
    traffic : TrafficState
        Rate limit, daily statistics and access log (Nogat DEV-15.9 to DEV-15.11).
    feedback : Feedback
        Reports of „Zgłoś uwagę” (DEV-15.12).
    terms : bytes or None
        The filled ``regulamin.html`` (DEV-15.7), or None when the deployment is
        not public (no usable ``[nogat.operator]``).
    version : str
        Obserwator's version, the app's version in reports and the session.
    """

    config: GuiConfig
    root: DataRoot
    analyses: Analyses
    current: CurrentData
    pmaxtp: Pmaxtp
    traffic: TrafficState
    feedback: Feedback
    terms: bytes | None
    version: str = __version__
    hidden: tuple[Path, ...] = field(default_factory=tuple)

    def directories(self) -> tuple[Path, ...]:
        """The server's directories hidden in answers (D6): root, state, temporary, working."""
        return (
            self.config.root,
            self.config.state_dir,
            Path(tempfile.gettempdir()),
            Path.cwd(),
            *self.hidden,
        )
