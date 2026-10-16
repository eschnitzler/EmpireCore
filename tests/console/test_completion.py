from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from empire_core.client.client import EmpireClient
from empire_core.console.completion import CommandCompleter, ConsoleCompleter, NamespaceCompleter, signature_at


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


def command_texts(text, commands=None, arguments=None):
    completer = CommandCompleter(
        lambda: commands or {"filter": "only these commands", "theme": "switch the theme", "grep": "search"},
        arguments or {},
    )
    document = Document(text, len(text))
    return [c.text for c in completer.get_completions(document, CompleteEvent())]


def test_commands_complete_by_name():
    assert command_texts(":fi") == ["filter"]
    assert sorted(command_texts(":")) == ["filter", "grep", "theme"]


def test_command_arguments_complete():
    arguments = {"theme": lambda: ["dark", "light"]}
    assert command_texts(":theme l", arguments=arguments) == ["light"]
    assert command_texts(":grep x", arguments=arguments) == []


def test_python_and_commands_share_one_completer():
    namespace = {"my_value": 1}
    completer = ConsoleCompleter(NamespaceCompleter(namespace), CommandCompleter(lambda: {"quit": "exit"}, {}))

    def texts(text):
        return [c.text for c in completer.get_completions(Document(text, len(text)), CompleteEvent())]

    assert "my_value" in texts("my_v") and texts(":q") == ["quit"]


def test_the_docstring_of_a_completion_is_kept():
    namespace = {"client": EmpireClient(username="u", password="p")}
    completer = NamespaceCompleter(namespace)
    list(completer.get_completions(Document("client.castle.get_al", 20), CompleteEvent()))
    assert "castles" in completer.docs("get_all")
    assert completer.docs("nothing_like_it") == ""
