import types
from app import llm


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Msg:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


class _FakeStream:
    def __init__(self, msg):
        self._msg = msg
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def get_final_message(self):
        return self._msg


class _FakeClient:
    """First turn: ask to read 'risks'. Second turn: emit final text."""
    def __init__(self):
        self.calls = 0
        self.messages = types.SimpleNamespace(stream=self._stream)
    def _stream(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return _FakeStream(_Msg(
                [_Block(type="tool_use", id="t1", name="read_section",
                        input={"section": "risks"})],
                "tool_use"))
        return _FakeStream(_Msg([_Block(type="text", text="DONE: saw risks")], "end_turn"))


def test_run_tool_loop_reads_then_finishes(monkeypatch):
    monkeypatch.setattr(llm, "_anthropic_client", lambda: _FakeClient())
    reads = []

    def reader(section: str) -> str:
        reads.append(section)
        return "## Risks\nvendor lock-in"

    out = llm.run_tool_loop(
        system="write it",
        user="write the risks section",
        model="claude-haiku-4-5",
        read_section=reader,
        max_tokens=2000,
    )
    assert reads == ["risks"]
    assert "DONE" in out
