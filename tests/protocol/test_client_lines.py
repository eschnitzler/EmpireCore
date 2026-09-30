"""Every request and reply model names the game client code it mirrors."""

import pytest

import empire_core.protocol.models  # noqa: F401  imports every area's models
from empire_core.protocol.base import BaseRequest, BaseResponse

# Models the client has no code for, each with why.
CLIENT_LESS = {
    "AllianceChatLogRequest": "the client never sends acl; its C2S_ALLIANCE_CHAT_LOG constant is unused",
}


def _command_models() -> list[type]:
    def subclasses(cls: type) -> list[type]:
        return [sub for direct in cls.__subclasses__() for sub in (direct, *subclasses(direct))]

    models = {
        model
        for base in (BaseRequest, BaseResponse)
        for model in subclasses(base)
        if "command" in model.__dict__ and model.__module__.startswith("empire_core.")
    }
    return sorted(models, key=lambda model: (model.__module__, model.__qualname__))


MODELS = _command_models()


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__qualname__)
def test_every_command_model_has_a_client_line(model):
    if model.__qualname__ in CLIENT_LESS:
        assert "Client:" not in (model.__doc__ or ""), (
            f"{model.__qualname__} has a Client: line; drop it from CLIENT_LESS"
        )
        return
    assert "Client:" in (model.__doc__ or ""), f"{model.__module__}.{model.__qualname__} has no Client: line"


def test_the_allowlist_names_only_command_models():
    assert set(CLIENT_LESS) <= {model.__qualname__ for model in MODELS}
