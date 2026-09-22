# Model Storage Checker

Model Storage Checker is a dependency-free Python tool for inspecting locally
stored model files. It includes an Ollama inventory provider using Ollama's
local HTTP API.

Requires Python 3.11 or newer.

## Usage

```console
model-storage-checker --help
model-storage-checker --output text providers
model-storage-checker --output json providers
model-storage-checker --output json list --provider ollama
model-storage-checker --ollama-base-url http://localhost:11434 --ollama-timeout 3 list --provider ollama
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

## Tests

```console
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
