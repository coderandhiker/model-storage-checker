# Model Storage Checker

Model Storage Checker is a dependency-free Python foundation for inspecting
locally stored model files. This first layer defines the typed data model,
provider and result contracts, and command-line interface; it does not yet
connect to any model provider.

Requires Python 3.11 or newer.

## Usage

```console
model-storage-checker --help
model-storage-checker --output text providers
model-storage-checker --output json providers
model-storage-checker --output json list --provider ollama
python -m model_storage_checker --output text providers
```

`providers` reports the providers registered in the current build. `list`
requests model records from a named provider. Because this layer registers no
providers, `list` currently exits with a clear `provider_unavailable` error.
Both commands support `text` and machine-readable `json` output.

## Planned providers

Later layers are expected to add provider implementations for Ollama, LM
Studio, and Docker-backed model storage. These integrations are planned only
and are not included in the current package.

## Tests

```console
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
