"""Versioned unit/tool bundle paths from the client's embedded ItemVersions index."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import requests

from empire_core.exceptions import NetworkError

from . import cache
from .cdn import RETRY_AFTER_FAILURE

_BASE_URL = "https://empire-html5.goodgamestudios.com/default"
_DLL = re.compile(r'(?:src|href)=["\']dll/ggs\.dll\.([a-f0-9]+)\.js["\']')
_FILL = re.compile(r"ItemVersions\.prototype\.fill=function\(\)\{(.*?)\},ItemVersions\}", re.DOTALL)
_ENTRY = re.compile(r'this\.assets(?:\.([A-Za-z_$][\w$]*)|\["([^"\\]+)"\])="([^"\\]+)"')
_PATH = re.compile(r"itemassets/[A-Za-z0-9_./-]+")
_lock = threading.Lock()
_loaded: AssetIndex | None = None
_last_failure: tuple[float, str] | None = None
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssetIndex:
    """
    An immutable snapshot of client asset names and versioned bundle paths.

    Inject a mapping for offline use, or call :meth:`load` to discover the current
    DLL from the official client page. Paths are CDN-relative, extensionless
    asset bundles, not individual PNG files. The index has its own DLL version;
    it is independent of the items JSON version.

    Client: ``ItemVersions.getPath/fill`` (ggs.dll lines 16066–16078) and
    ``PathProvider.getAssetURL`` (ggs.dll line 3437).
    """

    paths: Mapping[str, str]
    version: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-f0-9]+", self.version):
            raise ValueError("Invalid ItemVersions DLL version")
        paths = dict(self.paths)
        for name, path in paths.items():
            if not isinstance(name, str) or not name or not isinstance(path, str) or not _PATH.fullmatch(path):
                raise ValueError("Invalid ItemVersions asset entry")
            if any(part in {"", ".", ".."} for part in path.split("/")):
                raise ValueError("Invalid ItemVersions asset path")
        object.__setattr__(self, "paths", MappingProxyType(paths))

    def path(self, name: str) -> str:
        """The exact indexed path; raises KeyError when the asset is absent."""
        try:
            return self.paths[name]
        except KeyError:
            raise KeyError(f"Asset {name!r} is absent from ItemVersions {self.version}") from None

    @classmethod
    def from_javascript(cls, source: str, *, version: str) -> AssetIndex:
        """
        Parse the client's ItemVersions.fill assignments without executing JavaScript.

        Both dot and quoted bracket keys occur in the official DLL. An unknown
        format raises ValueError instead of producing a partial asset index.
        """
        body = _FILL.search(source)
        if body is None:
            raise ValueError("ItemVersions.fill is missing from the DLL")
        assignments = body.group(1)
        if re.sub(r"[\s,;]", "", _ENTRY.sub("", assignments)):
            raise ValueError("Unsupported ItemVersions asset index format")
        paths = {match[1] or match[2]: match[3] for match in _ENTRY.finditer(assignments)}
        if not paths:
            raise ValueError("ItemVersions asset index is empty")
        return cls(paths, version=version)

    @classmethod
    def load(cls, *, refresh: bool = False, cache_dir: str | Path | None = None) -> AssetIndex:
        """
        Lazily load the official index, cached in memory and on disk by DLL hash.

        The first call in a process checks the client page for its DLL version.
        Subsequent calls reuse the snapshot; ``refresh=True`` checks and downloads
        again. A cached DLL index avoids downloading the DLL on process restart.
        Network failures raise NetworkError and back off for five minutes;
        malformed metadata/indexes raise ValueError. Neither imports nor building
        a GameData object calls this loader.
        """
        global _loaded, _last_failure
        with _lock:
            if _loaded is not None and not refresh:
                return _loaded
            if not refresh and _last_failure is not None:
                failed_at, message = _last_failure
                if time.monotonic() - failed_at < RETRY_AFTER_FAILURE:
                    raise NetworkError(message)
            directory = Path(cache_dir) if cache_dir is not None else cache.default_cache_dir()
            try:
                response = requests.get(f"{_BASE_URL}/index.html", timeout=10)
                response.raise_for_status()
                versions = set(_DLL.findall(response.text))
                if len(versions) != 1:
                    raise ValueError("Client page does not identify one ItemVersions DLL")
                version = versions.pop()
                path = directory / f"item-assets-{version}.json"
                with cache.locked(path.with_suffix(".lock")):
                    if path.exists() and not refresh:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                        if not isinstance(payload, dict):
                            raise ValueError("Invalid cached ItemVersions asset index")
                        result = cls(payload, version=version)
                        if not result.paths:
                            raise ValueError("Cached ItemVersions asset index is empty")
                    else:
                        response = requests.get(f"{_BASE_URL}/dll/ggs.dll.{version}.js", timeout=30)
                        response.raise_for_status()
                        result = cls.from_javascript(response.text, version=version)
                        try:
                            cache.write_atomic(path, json.dumps(dict(result.paths)))
                        except OSError as error:
                            logger.debug("Could not cache asset index: %s", error)
            except requests.RequestException as error:
                message = f"Could not load the asset index: {error}"
                _last_failure = (time.monotonic(), message)
                raise NetworkError(message) from error
            _loaded = result
            _last_failure = None
            return result


__all__ = ["AssetIndex"]
