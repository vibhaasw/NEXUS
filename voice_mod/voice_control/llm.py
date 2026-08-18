from __future__ import annotations

from dataclasses import dataclass

from ollama import Client, ResponseError

from voice_control.config import AppConfig


@dataclass(slots=True)
class LlmResponse:
    content: str


class OllamaRouterClient:
    def __init__(self, config: AppConfig) -> None:
        kwargs = {}
        if config.ollama_host:
            kwargs["host"] = config.ollama_host
        self._client = Client(**kwargs)
        self._model = config.ollama_model

    @property
    def model_name(self) -> str:
        return self._model

    def healthcheck(self) -> None:
        try:
            self._client.show(self._model)
        except ConnectionError as exc:
            raise RuntimeError(
                "Could not connect to Ollama. Start the local Ollama service first, then retry."
            ) from exc
        except ResponseError as exc:
            raise RuntimeError(
                f"Ollama can be reached, but the model `{self._model}` is not available. Pull or rename the model."
            ) from exc

    def route(self, system_prompt: str, user_text: str) -> LlmResponse:
        try:
            response = self._client.chat(
                model=self._model,
                format="json",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
            )
        except ConnectionError as exc:
            raise RuntimeError("Could not connect to Ollama. Make sure the local Ollama service is running.") from exc
        except ResponseError as exc:
            raise RuntimeError(f"Ollama request failed: {exc}") from exc

        content = response.message.content if response.message else ""
        return LlmResponse(content=content or "")
