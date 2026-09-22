# Model Storage Checker

Model Storage Checker is a dependency-free Python tool for inspecting locally
stored model files. It includes an Ollama inventory provider using Ollama's
local HTTP API and an LM Studio provider using its local API and model
directories.

Requires Python 3.11 or newer.

## Usage

```console
model-storage-checker --help
model-storage-checker --output text providers
model-storage-checker --output json providers
model-storage-checker --output json list --provider ollama
model-storage-checker --ollama-base-url http://localhost:11434 --ollama-timeout 3 list --provider ollama
model-storage-checker --output json list --provider lm-studio
model-storage-checker --lm-studio-base-url http://localhost:1234 --lm-studio-timeout 3 list --provider lm-studio
model-storage-checker --lm-studio-model-root /Volumes/models/lm-studio list --provider lm-studio
python -m model_storage_checker --output text providers
```

`providers` reports the providers registered in the current build. `list`
requests model records from a named provider. Both commands support `text` and
machine-readable `json` output.

## Ollama

The Ollama provider requests `GET /api/tags` from
`http://127.0.0.1:11434` by default. Use `--ollama-base-url` to target another
Ollama endpoint and `--ollama-timeout` to change the short request timeout.
The inventory includes each model's name, digest (as its identifier), size,
modified time, and Ollama details when present.

An unreachable Ollama service produces a `provider_unavailable` error. A
reachable service with an invalid response produces a `provider_error`. A
valid response with no models succeeds and prints `No models found.` (or
`{"models": []}` with JSON output).

## LM Studio

The LM Studio provider requests the documented OpenAI-compatible
`GET /v1/models` endpoint at `http://127.0.0.1:1234` by default. Use
`--lm-studio-base-url` to target another server and `--lm-studio-timeout` to
change the short request timeout.

The provider also recursively inventories model artifacts under
`~/.lmstudio/models`, so downloaded models remain visible for cleanup while
the server is stopped. Use `--lm-studio-model-root PATH` to replace that
default; repeat the option to inventory multiple locations. Each filesystem
record includes its model directory, aggregate byte size, and individual file
paths and sizes. API and filesystem records are merged when their identifiers
match uniquely.

An unavailable API falls back to an observable filesystem inventory when
model files exist. Malformed API responses and filesystem access errors are
reported as `provider_error`; if neither the API nor disk can provide an
inventory, the provider reports `provider_unavailable`. A valid empty API
response combined with an existing empty model directory is a successful
empty inventory.

## Tests

```console
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
