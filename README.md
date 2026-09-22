# Model Storage Checker

`model-storage-checker` is a Python 3.11+ command-line tool for reporting
locally stored models. It discovers models from a local Ollama service and
defines shared interfaces for additional providers.

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

## Current provider scope

Ollama inventory is supported. LM Studio and Docker are recognized names but
are explicitly reported as unsupported. Discovery is read-only and intended
for a local Ollama endpoint: no telemetry capture, model mutation, or container
changes are performed.
