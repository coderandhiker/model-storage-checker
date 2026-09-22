# Model Storage Checker

`model-storage-checker` is a Python 3.11+ command-line tool for reporting
locally stored models. It discovers models from local Ollama and LM Studio
services, as well as LM Studio model files on disk.

## Installation

Install from the repository with Python 3.11 or newer:

```console
python -m pip install .
```

For editable development installs:

```console
python -m pip install -e .
```

The runtime package uses only the Python standard library.

## Invocation

Run the installed command or the package module:

```console
model-storage-checker list
python -m model_storage_checker list --provider ollama
```

`list` is currently the only operation. Providers can be selected repeatedly:

```console
model-storage-checker list --provider ollama --provider docker
```

Without `--provider`, all known providers are reported in a stable order.
Unknown provider names and unknown operations are rejected by `argparse`.

### Ollama configuration

Ollama inventory uses the read-only `GET /api/tags` endpoint. By default the
checker connects to `http://127.0.0.1:11434` with a five-second timeout:

```console
model-storage-checker list --provider ollama \
  --ollama-base-url http://localhost:11434 \
  --ollama-timeout 10
```

The base URL must be an absolute HTTP or HTTPS URL, and the timeout must be
greater than zero.

### LM Studio configuration

LM Studio inventory combines the read-only OpenAI-compatible `GET /v1/models`
endpoint with a recursive scan of model roots. The defaults are
`http://127.0.0.1:1234/v1`, a five-second timeout, and
`~/.lmstudio/models`:

```console
model-storage-checker list --provider lm-studio \
  --lm-studio-base-url http://localhost:1234/v1 \
  --lm-studio-timeout 10 \
  --lm-studio-model-root ~/.lmstudio/models
```

Repeat `--lm-studio-model-root` to scan multiple roots. The scan recognizes
GGUF, SafeTensors, BIN, MLX, ONNX, PT, and PTH model files. Each file reports
its exact byte size, absolute path, configured root, relative path, and
extension.

API observations are deduplicated by exact model ID. An API model and a file
are merged only when the API ID exactly equals the file's root-relative path
without its final extension. If multiple matching files exist, each remains a
separate record with its own size and location; API metadata is retained on
each. This avoids merging models based on ambiguous file names.

## Output

Human-readable text is the default:

```console
model-storage-checker list
```

For deterministic, machine-readable output, use JSON:

```console
model-storage-checker list --output json
```

JSON object keys, provider results, records, and record attributes have stable
ordering. The schema includes a version, operation, and provider results.

The command exits with status `0` when every selected provider succeeds, `3`
when any selected provider is unavailable, and `4` when any selected provider
or operation is unsupported. Other provider failures exit with status `1`.
An Ollama service that returns no models is a successful empty inventory.
An unreachable service is reported as `unavailable`; invalid JSON or an
invalid `/api/tags` response is reported as `error`.

LM Studio API and filesystem discovery run independently. If one source fails,
valid records from the other source remain in the result while the provider
status and message identify whether API or filesystem discovery failed. An
unreachable API is `unavailable`; malformed API responses and invalid,
missing, or inaccessible model roots are `error`. Empty successful sources
produce a successful empty inventory.

## Current provider scope

Ollama and LM Studio inventory are supported. Docker is a recognized name but
is explicitly reported as unsupported. Discovery is read-only: no telemetry
capture, model mutation, or container changes are performed.
