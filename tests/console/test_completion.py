from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from empire_core.client.client import EmpireClient
from empire_core.console.completion import NamespaceCompleter, signature_at


def completions(namespace, text):
    document = Document(text, len(text))
    return [c.text for c in NamespaceCompleter(namespace).get_completions(document, CompleteEvent())]


def test_completes_client_services_and_methods():
    namespace = {"client": EmpireClient(username="u", password="p")}
    assert "castle" in completions(namespace, "client.ca")
    assert "get_movements" in completions(namespace, "client.movements.get_m")


def test_completes_names_in_the_namespace():
    assert "my_value" in completions({"my_value": 1}, "my_v")


def test_signature_inside_a_call():
    namespace = {"client": EmpireClient(username="u", password="p")}
    text = "client.castle.get_resources("
    assert "castle_id" in signature_at(namespace, text, 0, len(text))


def test_no_signature_outside_a_call():
    assert signature_at({}, "1 + 1", 0, 5) == ""


class Hostile:
    def __getattr__(self, name):
        raise RuntimeError("boom")


def test_completer_errors_are_swallowed():
    assert completions({"bad": Hostile()}, "bad.") == []
