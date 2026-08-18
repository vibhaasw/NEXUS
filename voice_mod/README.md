# Voice Mod

Local push-to-talk voice control prototype built with `RealtimeSTT` and Ollama.

## What it does

- Captures one microphone utterance at a time.
- Transcribes speech with `RealtimeSTT`.
- Sends the transcript to a local Ollama model, defaulting to `phi4-mini:latest`.
- Prints the transcript, detected mode, and model response.
- Prints structured command intents instead of executing them.

## Setup

```bash
cd /home/vibhaasw/voice_mod
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you already have the required packages in another Python environment, you can use that instead.

`RealtimeSTT` needs optional runtime packages for this project. They are already included in `requirements.txt`, but if you installed pieces manually before, make sure these are present:

```bash
python -m pip install faster-whisper silero-vad
```

## Run

```bash
cd /home/vibhaasw/voice_mod
python -m voice_control.main
```

Or after installing the package:

```bash
voice-mod
```

## Configuration

Environment variables:

- `VOICE_MOD_OLLAMA_MODEL` default: `phi4-mini:latest`
- `OLLAMA_HOST` optional custom Ollama host
- `VOICE_MOD_LANGUAGE` default: `en`
- `VOICE_MOD_STT_MODEL` default: `tiny`
- `VOICE_MOD_STT_ENGINE` default: `faster_whisper`
- `VOICE_MOD_DEVICE` default: `cpu`
- `VOICE_MOD_COMPUTE_TYPE` default: `default`
- `VOICE_MOD_INPUT_DEVICE_INDEX` optional mic device index
- `VOICE_MOD_POST_SPEECH_SILENCE` default: `0.6`
- `VOICE_MOD_MIN_RECORDING_LENGTH` default: `0.4`
- `VOICE_MOD_REALTIME_TRANSCRIPTION` default: `false`
- `VOICE_MOD_DEBUG` default: `false`

## Behavior

1. Press Enter to start recording.
2. Press Enter again to stop.
3. Review the transcript and routed response in the terminal.

## Troubleshooting

- If startup says `faster_whisper` is missing, install `faster-whisper`.
- If startup says `silero_vad` is missing, install `silero-vad`.
- Keep Ollama available locally before running the app. On Linux this usually means the Ollama service or `ollama serve` must already be running.
- `ollama ps` being empty is normal when no model is currently loaded. The model is loaded on the first request.
- If the model name is wrong, set `VOICE_MOD_OLLAMA_MODEL=phi4-mini:latest`.
- If microphone detection is noisy on Linux, set `VOICE_MOD_INPUT_DEVICE_INDEX` to the correct input device.
- ALSA and JACK warnings can appear on Linux even when one microphone backend still works; they matter only if recording never starts.

## Next steps

The current prototype is intentionally safe: command-like requests are classified and printed, but no local actions are executed yet.
