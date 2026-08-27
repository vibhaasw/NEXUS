from dispatch.classifier import ClassificationResult
from dispatch.routing_policy import looks_like_local_action, parse_local_action, should_auto_delegate


def test_should_auto_delegate_high_complexity():
    c = ClassificationResult(
        task_type="reasoning",
        complexity="high",
        capabilities_required=["reasoning"],
        simplified_prompt="Explain quantum field theory step by step.",
    )
    assert should_auto_delegate(c) is True


def test_should_not_auto_delegate_low_complexity():
    c = ClassificationResult(
        task_type="fast_lookup",
        complexity="low",
        capabilities_required=["fast"],
        simplified_prompt="What is the capital of France?",
    )
    assert should_auto_delegate(c) is False


def test_should_not_auto_delegate_medium_reasoning():
    c = ClassificationResult(
        task_type="reasoning",
        complexity="medium",
        capabilities_required=["reasoning"],
        simplified_prompt="Explain how Rust ownership works.",
    )
    assert should_auto_delegate(c) is False


def test_should_auto_delegate_medium_code():
    c = ClassificationResult(
        task_type="code",
        complexity="medium",
        capabilities_required=["code"],
        simplified_prompt="Write an async Rust HTTP server.",
    )
    assert should_auto_delegate(c) is True


def test_suggested_provider_alone_does_not_auto_delegate():
    c = ClassificationResult(
        task_type="fast_lookup",
        complexity="low",
        capabilities_required=["fast"],
        simplified_prompt="What is the capital of France?",
        suggested_provider="openai",
    )
    assert should_auto_delegate(c) is False


def test_local_action_parse_open():
    name, args = parse_local_action("open firefox")
    assert name == "open_app"
    assert args["target"].lower() == "firefox"


def test_local_action_parse_open_site_in_browser():
    cases = [
        ("Open youtube in firefox for me", "firefox", "youtube"),
        ("open github with chrome", "chrome", "github"),
        ("launch reddit.com in brave", "brave", "reddit.com"),
        ("open https://example.com in firefox", "firefox", "https://example.com"),
    ]
    for text, app, url in cases:
        parsed = parse_local_action(text)
        assert parsed is not None, text
        name, args = parsed
        assert name == "open_app", text
        assert args["app"].lower() == app.lower(), text
        assert args["url"].lower() == url.lower(), text


def test_local_action_parse_spotify_variants():
    cases = [
        ("open Spotify", "Spotify"),
        ("open the Spotify app", "Spotify"),
        ("open Spotify please", "Spotify"),
        ("can you open Spotify for me", "Spotify"),
        ("launch Spotify application", "Spotify"),
    ]
    for text, expected in cases:
        parsed = parse_local_action(text)
        assert parsed is not None, text
        name, args = parsed
        assert name == "open_app"
        assert args["target"].lower() == expected.lower(), text


def test_local_action_parse_search():
    name, args = parse_local_action("search the web for rust tutorials")
    assert name == "search_web"
    assert "rust" in args["query"]


def test_run_does_not_false_positive_as_open_app():
    assert parse_local_action("run a python script") is None
    assert looks_like_local_action("run a python script") is False
