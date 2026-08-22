from handlers.base import BaseHandler, HandlerRegistry, HandlerResult
from voice_control.stt import normalize_transcript


def test_normalize_transcript_accepts_speech():
    result = normalize_transcript("   open firefox please   ")
    assert result.accepted is True
    assert result.text == "open firefox please"


def test_normalize_transcript_rejects_empty():
    result = normalize_transcript("   ")
    assert result.accepted is False
    assert result.reason == "empty transcript"


def test_normalize_transcript_rejects_filler_only():
    result = normalize_transcript("um uh hmm")
    assert result.accepted is False
    assert result.reason == "filler-only transcript"


class _DummyHandler(BaseHandler):
    @property
    def name(self):
        return "dummy"

    @property
    def description(self):
        return "A test handler."

    def tool_parameters(self):
        return {"type": "object", "properties": {}, "required": []}

    def execute(self, **kwargs):
        return HandlerResult(success=True, output="done", handler_name=self.name)


def test_registry_register_and_get():
    reg = HandlerRegistry()
    h = _DummyHandler()
    reg.register(h)
    assert reg.get("dummy") is h
    assert reg.get("nonexistent") is None


def test_registry_ollama_tools_format():
    reg = HandlerRegistry()
    reg.register(_DummyHandler())
    tools = reg.ollama_tools()
    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "dummy"


def test_handler_names():
    reg = HandlerRegistry()
    reg.register(_DummyHandler())
    assert reg.handler_names() == ["dummy"]


def test_web_search_handler_no_query():
    from handlers.web_search_handler import WebSearchHandler
    h = WebSearchHandler()
    result = h.execute(query="")
    assert result.success is False
    assert "No search query" in result.output


def test_edit_file_handler_missing_file():
    from handlers.edit_file_handler import EditFileHandler
    h = EditFileHandler()
    result = h.execute(file_path="/tmp/__nonexistent_voice_mod_test_file__")
    assert result.success is False
    assert "not found" in result.output.lower()


def test_open_app_handler_format():
    from handlers.open_app_handler import OpenAppHandler
    h = OpenAppHandler()
    tool = h.as_ollama_tool()
    assert tool["function"]["name"] == "open_app"
    assert "target" in tool["function"]["parameters"]["properties"]


def test_code_handler_no_prompt():
    from handlers.code_handler import CodeHandler
    h = CodeHandler()
    result = h.execute(prompt="")
    assert result.success is False


def test_parse_text_tool_call_func_parens():
    from voice_control.router import _try_parse_text_tool_call
    reg = HandlerRegistry()
    reg.register(_DummyHandler())
    result = _try_parse_text_tool_call('dummy({"key": "val"})', reg)
    assert result is not None
    name, args = result
    assert name == "dummy"
    assert args == {"key": "val"}


def test_parse_text_tool_call_func_space():
    from voice_control.router import _try_parse_text_tool_call
    reg = HandlerRegistry()
    reg.register(_DummyHandler())
    result = _try_parse_text_tool_call('dummy {"key": "val"}', reg)
    assert result is not None
    name, args = result
    assert name == "dummy"
    assert args == {"key": "val"}


def test_parse_text_tool_call_json_array_with_name():
    from voice_control.router import _try_parse_text_tool_call
    reg = HandlerRegistry()
    reg.register(_DummyHandler())
    text = '[{"type":"function","name":"dummy","arguments":{"a":"b"}}]'
    result = _try_parse_text_tool_call(text, reg)
    assert result is not None
    name, args = result
    assert name == "dummy"
    assert args == {"a": "b"}


def test_parse_text_tool_call_json_array_phi4mini_format():
    from voice_control.router import _try_parse_text_tool_call
    reg = HandlerRegistry()
    reg.register(_DummyHandler())
    text = '[{"type": "dummy", "parameters": {"target": "firefox"}}]'
    result = _try_parse_text_tool_call(text, reg)
    assert result is not None
    name, args = result
    assert name == "dummy"
    assert args == {"target": "firefox"}


def test_parse_text_tool_call_no_match():
    from voice_control.router import _try_parse_text_tool_call
    reg = HandlerRegistry()
    reg.register(_DummyHandler())
    result = _try_parse_text_tool_call("just some random text", reg)
    assert result is None
