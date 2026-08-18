from voice_control.router import parse_router_payload
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


def test_parse_router_payload_parses_command_json():
    routed = parse_router_payload(
        '{"mode":"command","reply":"Opening Firefox.","command_name":"open_app","command_args":{"app":"firefox"}}'
    )

    assert routed.mode == "command"
    assert routed.reply == "Opening Firefox."
    assert routed.command_name == "open_app"
    assert routed.command_args == {"app": "firefox"}


def test_parse_router_payload_falls_back_for_plain_text():
    routed = parse_router_payload("This is not JSON.")

    assert routed.mode == "assistant"
    assert routed.reply == "This is not JSON."
    assert routed.command_args == {}
