# Model Storage Checker

Model Storage Checker is a dependency-free Python tool for inspecting locally
stored model files. It inventories Ollama, LM Studio, and Docker, and produces
a unified storage report with advisory cleanup candidates.

Requires Python 3.11 or newer.

## Installation

Install from a checkout with pip:

```console
python3.11 -m pip install .
model-storage-checker --help
```

No production packages beyond the Python standard library are required. You
can also run without installing by setting `PYTHONPATH=src`:

```console
PYTHONPATH=src python3.11 -m model_storage_checker report
```

## Usage

```console
model-storage-checker --help
model-storage-checker --output text providers
model-storage-checker --output json providers
model-storage-checker report
model-storage-checker --output json report
model-storage-checker report --largest-first --min-size 1073741824
model-storage-checker report --provider docker --resource image
model-storage-checker report --provider docker --candidates-only
model-storage-checker --output json list --provider ollama
model-storage-checker --ollama-base-url http://localhost:11434 --ollama-timeout 3 list --provider ollama
model-storage-checker --output json list --provider lm-studio
model-storage-checker --lm-studio-base-url http://localhost:1234 --lm-studio-timeout 3 list --provider lm-studio
model-storage-checker --lm-studio-model-root /Volumes/models/lm-studio list --provider lm-studio
model-storage-checker --output json list --provider docker
model-storage-checker --docker-timeout 10 list --provider docker
```

`providers` reports the providers registered in the current build. `list`
requests records from one named provider. `report` runs all providers by
default and groups storage by provider and resource type. Every command
supports `text` and machine-readable `json` output.

The report includes item counts, known-size counts, total bytes, human-readable
IEC sizes, three largest items per group, cleanup candidate counts, provider
errors, and successful results from providers that remain available. A partial
provider failure therefore still produces a valid report and exits
successfully when at least one provider succeeds.

Report filters can be combined:

- Repeat `--provider NAME` or `--resource TYPE` to select multiple values.
- `--min-size BYTES` excludes records with a smaller or unknown size.
- `--largest-first` sorts records by descending known size.
- `--candidates-only` keeps only advisory cleanup candidates.

Without filters, records use a deterministic provider/resource/name order.
Unknown-size records remain visible when `--min-size` is zero.

## JSON reports

```console
model-storage-checker --output json report > inventory.json
model-storage-checker --output json report \
  --provider lm-studio --provider docker \
  --candidates-only --largest-first
```

The JSON contract has `schema_version: 1` and deterministic ordering. It
contains `providers_requested`, `providers_succeeded`, applied `filters`,
aggregate `summary`, enriched raw provider `records`, top-level `warnings`, and
structured `errors`. Each record retains its identifier, name, exact
`size_bytes`, path, and provider metadata, and adds `resource_type` and a
`cleanup_candidate` assessment. Candidate assessments include all reasons,
whether a heuristic was used, and
`automatically_safe_to_delete: false`.

## Provider matrix

| Provider | Inventory source | Resource types | Size represented | Cleanup candidate support |
|---|---|---|---|---|
| Ollama | Local `GET /api/tags` | `model` | API-reported model bytes | None without explicit cleanup metadata |
| LM Studio | Local `GET /v1/models` and configured model directories | `model` | Aggregate artifact bytes for filesystem-backed records | Heuristic duplicate filesystem/API identities; reason is labeled heuristic |
| Docker | Read-only Docker CLI listings | `image`, `container` | Image virtual bytes; container writable bytes | Images explicitly reported as dangling; containers explicitly reported as stopped |

Docker image totals can include shared layers and therefore are inventory sums,
not guaranteed reclaimable bytes. API-only model records and some Docker
records may have unknown sizes; reports expose `known_size_count` so totals are
not mistaken for complete disk usage.

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

## Docker

The Docker provider uses the `docker` CLI to inventory every local image and
every container, including stopped containers. It runs read-only
`docker image ls` and `docker container ls` commands with Go-template JSON
output; it never deletes, prunes, starts, stops, or otherwise changes Docker
resources. Use `--docker-executable PATH` to select a Docker CLI and
`--docker-timeout` to change the command timeout.

Image records include repository, tag, full image ID, created time, virtual
size, shared size when Docker reports it, dangling status, digest, labels, and
other listing metadata. Container records include full container ID, name,
image, state, status, created time, writable and virtual size, and an explicit
`running` boolean. The `local_ai_classification` metadata is clearly marked as
heuristic and recognizes common Ollama, LocalAI, vLLM, and llama.cpp names;
unclassified images and containers are still included.

A missing Docker CLI, unavailable daemon, or permission denial produces a
distinct `provider_unavailable` result. Timeouts, other command failures, and
malformed output produce `provider_error`, with a machine-readable reason in
the error details. A successful inventory with no images or containers is an
empty success.

## Cleanup safety

Cleanup assessment is read-only and advisory. A candidate label never means
that deletion is automatically safe: dangling images may still be needed by
workflows, stopped containers may retain important writable data or be
intended for restart, and duplicate model identities can refer to distinct
artifacts. The tool does not delete, prune, remove, stop, start, or otherwise
modify resources, and it does not print copy-paste destructive commands.
Review dependencies, backups, retention requirements, shared storage, and
provider-specific state before taking any action outside this tool.

## Tests

```console
PYTHONPATH=src python3.11 -m unittest discover -s tests -v
```
