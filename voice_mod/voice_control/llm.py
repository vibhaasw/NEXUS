from __future__ import annotations

from ollama import Client, ResponseError

from voice_control.config import AppConfig


def create_ollama_client(config: AppConfig) -> Client:
    kwargs = {}
    if config.ollama_host:
        kwargs["host"] = config.ollama_host
    return Client(**kwargs)


def healthcheck(client: Client, model: str) -> None:
    try:
        client.show(model)
    except ConnectionError as exc:
        raise RuntimeError(
            "Could not connect to Ollama. Start the local Ollama service first, then retry."
        ) from exc
    except ResponseError as exc:
        raise RuntimeError(
            f"Ollama can be reached, but the model `{model}` is not available. "
            f"Pull it with `ollama pull {model}`."
        ) from exc
