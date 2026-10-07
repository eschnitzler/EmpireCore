"""
A game-data table: rows keyed by id, each validated the first time it is read.

Loading the game data then costs no row validation at all: a table holds the items rows as the
file has them, trimmed to the columns its model reads, and validates a row when it is asked for.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

K = TypeVar("K")
R = TypeVar("R", bound=BaseModel)


class Table(Mapping[K, R], Generic[K, R]):
    """
    One items table by id, read-only.

    Reading a row by id (``table[Building.KEEP_L1]``, ``table.get(171)``, ``171 in table``)
    validates that row alone. Iterating, ``len()`` or comparing validates every row once, and keys
    come back as the rows' ids: the enum member, or the plain int of an id the enum lacks. A row
    that does not fit its model is left out, as if the table did not have it.
    """

    __slots__ = ("_all", "_id_field", "_model", "_read", "_rows")

    def __init__(self, model: type[R], id_field: str, rows: Mapping[int, dict[str, Any]]) -> None:
        self._model = model
        self._id_field = id_field
        self._rows = rows
        self._read: dict[int, R | None] = {}
        self._all: dict[K, R] | None = None

    def _row(self, row_id: int) -> R | None:
        if row_id in self._read:
            return self._read[row_id]
        source = self._rows.get(row_id)
        row = None
        if source is not None:
            try:
                row = self._model.model_validate(source)
            except ValueError:
                row = None
        self._read[row_id] = row
        return row

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
