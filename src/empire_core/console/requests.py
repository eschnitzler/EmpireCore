"""The request models by command, so the console can read the frames it sends as it reads replies."""

from collections import defaultdict
from collections.abc import Iterator
from functools import cache
from typing import Any

from pydantic import ValidationError

from empire_core.protocol.base import BaseRequest


def request_models(command: str) -> tuple[type[BaseRequest], ...]:
    return _index().get(command, ())


def reply_command(command: str) -> str:
    """The command a request is answered under: its own, unless its model says otherwise."""
    for model in request_models(command):
        if model.response_command:
            return model.response_command
    return command


def parse_request(command: str, payload: dict[str, Any]) -> BaseRequest | None:
    """``payload`` as the request model whose wire keys it carries best; None if none takes it."""

    def fit(model: type[BaseRequest]) -> int:
        keys = {
            field.validation_alias if isinstance(field.validation_alias, str) else name
            for name, field in model.model_fields.items()
        }
        return len(payload.keys() & keys) - len(payload.keys() - keys)

    for model in sorted(request_models(command), key=fit, reverse=True):
        try:
            return model.model_validate(payload)
        except ValidationError:
            continue
    return None


@cache
def _index() -> dict[str, tuple[type[BaseRequest], ...]]:
    # Built on first use: by then the console has imported every area, and with it every model.
    models: dict[str, list[type[BaseRequest]]] = defaultdict(list)
    for model in _subclasses(BaseRequest):
        command = model.__dict__.get("command")
        if isinstance(command, str) and command:
            models[command].append(model)
    return {command: tuple(found) for command, found in models.items()}


def _subclasses(cls: type[BaseRequest]) -> Iterator[type[BaseRequest]]:
    for sub in cls.__subclasses__():
        yield sub
        yield from _subclasses(sub)
