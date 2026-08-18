from voice_control.config import AppConfig, load_config


def test_app_config_defaults(monkeypatch):
    monkeypatch.delenv("VOICE_MOD_OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("VOICE_MOD_INPUT_DEVICE_INDEX", raising=False)

    config = load_config()

    assert isinstance(config, AppConfig)
    assert config.ollama_model == "phi4-mini:latest"
    assert config.input_device_index is None
    assert config.language == "en"


def test_app_config_env_overrides(monkeypatch):
    monkeypatch.setenv("VOICE_MOD_OLLAMA_MODEL", "llama3")
    monkeypatch.setenv("VOICE_MOD_INPUT_DEVICE_INDEX", "2")
    monkeypatch.setenv("VOICE_MOD_REALTIME_TRANSCRIPTION", "true")

    config = load_config()

    assert config.ollama_model == "llama3"
    assert config.input_device_index == 2
    assert config.realtime_transcription is True
