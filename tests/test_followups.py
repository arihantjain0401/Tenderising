from tenderising.chat import agent


class _FakeProvider:
    def __init__(self, content):
        self._content = content

    def chat(self, messages, tools):
        return {"content": self._content, "tool_calls": []}


def test_parse_hints_json_array():
    assert agent._parse_hints('["a", "b", "c"]') == ["a", "b", "c"]


def test_parse_hints_array_embedded_in_prose():
    assert agent._parse_hints('Here you go: ```json\n["one", "two", "three"]\n```') == [
        "one",
        "two",
        "three",
    ]


def test_parse_hints_line_fallback():
    assert agent._parse_hints("1. first\n2. second\n3. third") == ["first", "second", "third"]


def test_suggest_followups_uses_provider():
    p = _FakeProvider('["q1", "q2", "q3"]')
    assert agent.suggest_followups("solar tenders", [], "5 matches", provider=p) == ["q1", "q2", "q3"]


def test_suggest_followups_empty_on_error():
    class _Boom:
        def chat(self, messages, tools):
            raise RuntimeError("no model")

    assert agent.suggest_followups("q", [], "a", provider=_Boom()) == []
