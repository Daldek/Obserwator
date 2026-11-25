"""
Provider adapters: one module per data provider, behind one protocol (ADR-029).

``obserwator.datasets`` is the declarative registry: the providers and their datasets,
from which the command catalog, ``AGENTS.md`` and ``llms.txt`` are generated. An
adapter (`ProviderAdapter`) is what Obserwator does with one provider beyond that:
the enumeration and download of its files, its station sources and their parsers, the
parsers of its datasets, its live current data, the credential its requests need, the
attribution origins of its data, its station catalog and the hook of its captures.
`ProviderDescriptor.adapter` gives a provider's adapter.

The modules are named by country and the provider's acronym (ECO-082, ADR-028):
``pl.imgw`` (IMGW-PIB), ``cz.chmu`` (ČHMÚ) and ``pl.gdanskiewody`` (Gdańskie Wody,
ADR-034). Adding a provider is one module here,
one entry in `_ADAPTERS`, its registry entries, its attribution lines and its
messages. A provider fed by files (ADR-033) needs none of them: the one
`obserwator.providers.files.FileFedAdapter` serves each provider file of
``nogat.toml``, after the packaged adapters.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from obserwator.datasets import provider_files
from obserwator.providers.base import (
    Answer,
    CheckScope,
    Kind,
    ProviderAdapter,
    SourceAction,
)
from obserwator.providers.cz.chmu import ADAPTER as _CHMU
from obserwator.providers.files import adapters as _file_adapters
from obserwator.providers.pl.gdanskiewody import ADAPTER as _GDANSKIEWODY
from obserwator.providers.pl.imgw import ADAPTER as _IMGW
from obserwator.providers.pl.pig import ADAPTER as _PIG

__all__ = [
    "Answer",
    "CheckScope",
    "Kind",
    "ProviderAdapter",
    "SourceAction",
    "adapter",
]

_ADAPTERS: Mapping[str, ProviderAdapter] = MappingProxyType(
    {
        item.provider_id: item
        for item in (
            _IMGW,
            _CHMU,
            _GDANSKIEWODY,
            _PIG,
            *_file_adapters(provider_files().files),
        )
    }
)
"""The adapter of every provider of the registry, by its id."""


def adapter(provider: str, /) -> ProviderAdapter:
    """
    Return the adapter of a provider.

    Parameters
    ----------
    provider : str
        Identifier (``"IMGW"``, ``"CHMU"``) or key prefix (``"pl.imgw"``).

    Returns
    -------
    ProviderAdapter
        The provider's adapter.

    Raises
    ------
    ObserwatorValidationError
        If the value names no provider of the registry.
    """
    from obserwator.datasets import get_provider

    return _ADAPTERS[get_provider(provider).id]
