# Model Storage Checker

`model-storage-checker` is a Python 3.11+ command-line foundation for reporting
locally stored models. This bootstrap release defines the provider interfaces
and output contract; it does not yet discover models.

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

## Current provider scope

Ollama, LM Studio, and Docker are recognized names but are explicitly reported
as unsupported in this bootstrap layer. No discovery, telemetry capture, model
mutation, container changes, or remote communication is performed.
