# Model Storage Checker sample application

The application is the workload used to generate the prompt-to-PR telemetry
evidence documented in [`README.md`](README.md). It is not required to
understand or reuse the lineage capture approach.

`model-storage-checker` is a Python 3.11+ command-line tool for reporting
locally stored models and related runtime storage. It discovers models from
local Ollama and LM Studio services, LM Studio model files on disk, and Docker
images and containers.

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

### Docker configuration

Docker inventory uses only the Docker CLI and performs two read-only queries:
`docker image ls` for every image and `docker container ls --all` for every
container, including stopped containers. Both commands request JSON template
output. Image records include IDs, repository references, digests, creation
details, and reported sizes. Container records include IDs, names, state,
status, creation details, reported writable-layer sizes, and their image
relationships. No Docker SDK or daemon mutation is used.

Each Docker CLI query has a ten-second default timeout:

```console
model-storage-checker list --provider docker --docker-timeout 20
```

`--docker-ai-heuristic` optionally annotates every Docker record with a clearly
marked heuristic classification. It does not filter the inventory; all images
and containers remain present regardless of the label.

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
ordering. The schema includes a version, operation, original provider results,
a storage summary, and advisory cleanup candidates. Provider errors and any
partial records remain visible in both output formats.

The storage summary reports record counts and sizes across all providers,
grouped by provider and resource type (`model`, Docker `image`, or Docker
`container`). A complete `total_size_bytes` is `null` whenever any contributing
record has an unknown size; `known_size_bytes` and `unknown_size_count` show
the available evidence without treating unknown values as zero. Docker image
and container sizes are provider-reported values and may overlap, so the
summary is not a claim about uniquely reclaimable disk space.

### Cleanup candidates

Cleanup candidates are **advisory only**. The checker never deletes models,
prunes images, removes or stops containers, or performs any other mutation.
Every candidate includes its rule, reported metadata evidence, and an explicit
`heuristic` classification. The conservative rules currently surface only:

- Docker images whose repository and tag are both reported as `<none>`.
- Docker containers whose state is reported as `exited` or `dead`.

These facts can make a resource worth reviewing, but do not prove that it is
unused or safe to remove. Running containers, tagged images, and model records
are not candidates. Incomplete metadata does not produce a candidate.

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

Docker reports a missing CLI, unavailable daemon, permission denial, and
timeout as distinct `unavailable` outcomes. A failed CLI query or malformed
JSON/template record is an `error`. Successful commands with no images or
containers produce a successful empty inventory. Docker discovery never
removes, prunes, stops, restarts, creates, or otherwise changes resources.

## Current provider scope

Ollama, LM Studio, and Docker inventory are supported. Discovery is read-only:
no telemetry capture, model mutation, or Docker resource changes are
performed.
