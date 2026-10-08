"""
A game-data table: rows keyed by id, each validated the first time it is read.

Loading the game data then costs no row validation at all: a table holds the items rows as the
file has them, trimmed to the columns its model reads, and validates a row when it is asked for.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator, Mapping
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

K = TypeVar("K")
R = TypeVar("R", bound=BaseModel)


class Table(Mapping[K, R], Generic[K, R]):
    """
    One items table by id, read-only.

    Reading a row by id (``table[Building.KEEP_L1]``, ``table.get(171)``, ``171 in table``)
    validates that row alone. Iterating, ``len()`` or comparing validates every row once, and keys
    come back as the rows' ids: the enum member, or the plain int of an id the enum lacks. A row
    that does not fit its model is left out, as if the table did not have it, with a warning the
    first time it is read. A table is shared by every thread that reads the game data: each row
    is validated once, so ``table[k] is table[k]`` holds across threads. ``context`` is passed to
    each row's validation, for a model that reads a row by another table.
    """

    __slots__ = ("_all", "_context", "_id_field", "_lock", "_model", "_name", "_read", "_rows")

    def __init__(
        self,
        model: type[R],
        id_field: str,
        rows: Mapping[int, dict[str, Any]],
        *,
        name: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        self._model = model
        self._context = context
        self._id_field = id_field
        self._rows = rows
        self._name = name or model.__name__
        self._read: dict[int, R | None] = {}
        self._all: dict[K, R] | None = None
        self._lock = threading.Lock()

    def _row(self, row_id: int) -> R | None:
        if row_id not in self._rows:
            return None
        with self._lock:
            if row_id not in self._read:
                self._read[row_id] = self._validate(row_id)
            return self._read[row_id]

    def _validate(self, row_id: int) -> R | None:
        try:
            return self._model.model_validate(self._rows[row_id], context=self._context)
        except ValidationError as e:
            logger.warning(
                "%s row %s does not fit %s and is left out: %s",
                self._name,
                row_id,
                self._model.__name__,
                "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()),
            )
            return None

    def _every_row(self) -> dict[K, R]:
        if self._all is None:
            rows = {}
            for row_id in self._rows:
                row = self._row(row_id)
                if row is not None:
                    rows[getattr(row, self._id_field)] = row
            self._all = rows
        return self._all

    def __getitem__(self, key: object) -> R:
        row = self._row(key) if isinstance(key, int) and not isinstance(key, bool) else None
        if row is None:
            raise KeyError(key)
        return row

    def __contains__(self, key: object) -> bool:
        return isinstance(key, int) and not isinstance(key, bool) and self._row(key) is not None

    def __iter__(self) -> Iterator[K]:
        return iter(self._every_row())

    def __len__(self) -> int:
        return len(self._every_row())

    def __repr__(self) -> str:
        return f"Table[{self._model.__name__}]({len(self._rows)} rows)"


__all__ = ["Table"]
