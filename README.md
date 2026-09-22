# End-to-End Copilot Traceability with OpenTelemetry

This `OTEL` branch is a reference implementation for capturing and publishing
evidence that connects an original prompt to the code and pull requests it
produced:

> prompt → orchestrator → delegated sessions → process attempts → OTel traces
> → model/tool activity → commits → pull requests → merge into `main`

The sample application in this repository is incidental. It exists because a
real code change was needed to produce realistic evidence. Its implementation
and usage documentation has moved to [`readme-app.md`](readme-app.md).

## What this evidence lets you answer

| Question | Evidence |
|---|---|
| What did the human ask for? | Exact explicit prompt files under `telemetry/run-2/prompts/` |
| Which Copilot session handled it? | Stable session IDs in the manifest, driver audit, and OTel resource attributes |
| Which work was delegated? | Parent/child session IDs, layer metadata, and exact delegation prompts |
| How many attempts or resumes occurred? | One OTel file plus host audit events for each process attempt |
| Which models and tools were used? | Sanitized OTel spans preserving model activity and actual tool calls, arguments, results, errors, IDs, and timing |
| What code was produced? | Git commits, trees, subjects, and Copilot/session trailers |
| Which PR published each change? | Branch, base branch, PR URL/number, and verified head SHA |
| Did the complete stack reach `main`? | Merged PR state plus verification that every feature head is an ancestor of the final `main` SHA |
| Was confidential runtime context removed? | Structural redaction ledger, secret scan, validation summary, and artifact integrity manifest |

## Explore this captured run

The fastest way to understand the result is the offline lineage dashboard:

```console
git switch OTEL
python3 -m http.server --directory docs/lineage 8000
```

Open <http://127.0.0.1:8000/>.

The graph starts with aggregate nodes so it remains readable. Select a node for
provenance and details; expand trace, model, or tool groups only when needed.
The primary path links the original prompt to the parent orchestrator, five
logical child sessions, ten process attempts, captured traces, feature commits,
merged PRs #6–#10, and the customer-facing `OTEL` branch.

Key artifacts:

- [`docs/lineage/index.html`](docs/lineage/index.html): offline interactive
  dashboard;
- [`docs/lineage/data.json`](docs/lineage/data.json): normalized graph and
  master-detail data;
- [`telemetry/run-2/manifest.json`](telemetry/run-2/manifest.json): normalized
  session, capture, Git, test, branch, and PR lineage;
- [`telemetry/run-2/otel/`](telemetry/run-2/otel/): sanitized OTel JSONL, one
  file per process attempt;
- [`telemetry/run-2/prompts/`](telemetry/run-2/prompts/): exact explicit parent
  and delegation prompts;
- [`telemetry/run-2/driver-audit.jsonl`](telemetry/run-2/driver-audit.jsonl):
  host-observed process and session lifecycle;
- [`telemetry/run-2/publication-metadata.json`](telemetry/run-2/publication-metadata.json):
  approved PR metadata tied to verified commit SHAs;
- [`telemetry/run-2/redaction-report.json`](telemetry/run-2/redaction-report.json):
  every structural redaction with category, JSON path, replacement marker, and
  SHA-256 of the removed value;
- [`telemetry/run-2/artifact-integrity.json`](telemetry/run-2/artifact-integrity.json):
  SHA-256, byte size, and line counts for the published evidence;
- [`telemetry/run-2/README.md`](telemetry/run-2/README.md): detailed notes for
  this specific captured run.

## Correlation contract

End-to-end traceability depends on carrying a small set of identifiers through
every stage. Choose names appropriate for your environment, but keep the
relationships stable.

| Identifier | Purpose |
|---|---|
| `run_id` | Groups all evidence from one end-to-end request |
| `session_id` | Identifies one logical Copilot session |
| `parent_session_id` | Connects delegated work to its logical parent |
| `invocation` | Distinguishes initial, retry, and resume process attempts |
| `role` | Labels orchestrator, delegated worker, reviewer, or other roles |
| `layer` | Orders dependent branches/PRs when work is stacked |
| `trace_id` / `span_id` | Connects model and tool activity inside an OTel capture |
| `commit_sha` | Connects a completed session to immutable Git evidence |
| `head_sha` | Proves a PR published the expected commit |
| `merge_sha` | Proves the approved PR stack reached its final branch |

The critical joins are:

1. exact prompt file → `session_id`;
2. child `parent_session_id` → parent `session_id`;
3. process attempt → OTel file through `session_id` + `invocation`;
4. model/tool spans → process attempt through OTel resource attributes;
5. session → commit through a commit trailer and recorded `commit_sha`;
6. commit → PR through branch name and exact `head_sha`;
7. PR → final merge through merged state and ancestry from each `head_sha` to
   the final `main` SHA.

## Set this up in your own repository

### 1. Establish a private/public boundary first

Full-content telemetry can contain prompts, assistant responses, source code,
commands, file paths, and tool arguments/results. Keep raw capture material
outside the publishable tree.

One practical layout is:

```text
your-repository/
├── .copilot-lineage-tools/   # ignored local helper clone
├── .lineage-private/         # ignored raw prompts, OTel, stdout, audits
├── telemetry/run-N/          # sanitized publishable evidence
└── docs/lineage/             # publishable dashboard and local assets
```

Add the private paths to `.gitignore` before the first capture:

```gitignore
/.copilot-lineage-tools/
/.lineage-private/
github_copilot_traces.xlsx
```

An ignored helper remains available to the agent when referenced explicitly;
it is merely excluded from normal Git tracking and many default searches.

### 2. Assign IDs before launching Copilot

Generate a stable `run_id` for the complete workflow and a stable `session_id`
for each logical parent or delegated session. Generate a distinct `invocation`
name for each initial, retry, or resume process.

The host that launches Copilot should know:

```text
run_id
session_id
parent_session_id
role
layer
invocation
branch
base_branch
```

Do not derive these relationships later from timestamps or process IDs.
Explicit correlation fields are deterministic and reviewable.

### 3. Save exact explicit prompts

Before launching each process, write the exact human or delegation prompt to
the private run directory:

```text
.lineage-private/run-N/prompts/orchestrator.md
.lineage-private/run-N/prompts/layer-1.md
.lineage-private/run-N/prompts/layer-2.md
```

These are explicit user/delegation prompts, not hidden system or developer
instructions. Secret-scan each prompt before copying it into the publishable
package. Preserve its exact bytes and record its SHA-256.

### 4. Capture one OTel stream per process attempt

Set the capture environment independently for every Copilot invocation:

```console
export PRIVATE_RUN="$PWD/.lineage-private/run-N"
export COPILOT_AGENT_SESSION_ID="$SESSION_ID"
export OTEL_SERVICE_NAME=github-copilot
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
export COPILOT_OTEL_FILE_EXPORTER_PATH="$PRIVATE_RUN/raw/$INVOCATION.jsonl"
export OTEL_RESOURCE_ATTRIBUTES="lineage.run_id=$RUN_ID,lineage.session_id=$SESSION_ID,lineage.parent_session_id=$PARENT_SESSION_ID,lineage.role=$ROLE,lineage.layer=$LAYER,lineage.invocation=$INVOCATION"

copilot --output-format=json --no-remote-export --no-auto-update
```

The important settings are:

- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` captures exact
  message and tool-call content. Treat the resulting files as confidential.
- `COPILOT_OTEL_FILE_EXPORTER_PATH` writes a local JSONL stream. Use a distinct
  file for every process attempt.
- `COPILOT_AGENT_SESSION_ID` gives the Copilot process a stable logical
  identity.
- `OTEL_RESOURCE_ATTRIBUTES` carries the parent/child and attempt correlation
  contract into every record.
- `--no-remote-export` keeps raw telemetry local.
- `--no-auto-update` plus a pinned CLI version improves reproducibility.

Permissive execution flags such as `--allow-all-tools`, `--allow-all-paths`,
or `--no-ask-user` are not required for telemetry fidelity. Do not copy them
into a customer environment without a separate security decision.

### 5. Record the host-observed lifecycle

OTel describes activity inside a process; a host audit connects separate
processes and retries. Append JSONL records for events such as:

```json
{
  "event": "process_started",
  "run_id": "run-N",
  "session_id": "child-session-id",
  "parent_session_id": "parent-session-id",
  "role": "delegated-worker",
  "layer": 2,
  "invocation": "layer-2-initial",
  "prompt_path": "prompts/layer-2.md",
  "telemetry_path": "raw/layer-2-initial.jsonl"
}
```

Also record process completion, exit status, retry/resume decisions, branch,
base branch, and the final commit SHA. Record secret environment variable names
only—never their values.

### 6. Carry session identity into Git

When a logical session produces a commit, make the relationship explicit:

```text
feat: implement the requested layer

Copilot-Session-Id: <session-id>
Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>
```

Record the commit SHA, parent SHA, tree SHA, branch, base branch, and tests.
For stacked work, verify that each layer's parent commit and PR base match the
layer below it.

### 7. Record PR and merge facts

After publication approval, record only public GitHub metadata:

```json
{
  "number": 123,
  "url": "https://github.com/owner/repository/pull/123",
  "state": "merged",
  "draft": false,
  "base": "parent-branch",
  "head_sha": "0123456789abcdef0123456789abcdef01234567"
}
```

Before declaring the lineage complete:

1. require the PR's live head SHA to equal the recorded feature commit;
2. record the bottom-to-top PR order;
3. record the final merge operation and final `main` SHA;
4. verify every feature `head_sha` is an ancestor of that final SHA.

That last ancestry check connects the original prompt to code that actually
landed, rather than merely to a branch or an open PR.

### 8. Sanitize into a publishable derivative

This branch includes a Python-standard-library reference toolchain:

```console
python3 tools/lineage/sanitize_telemetry.py \
  .lineage-private/run-N \
  --output telemetry/run-N \
  --repo-root . \
  --package-branch OTEL

python3 tools/lineage/build_dashboard.py \
  --telemetry-root telemetry/run-N \
  --output docs/lineage/data.json \
  --repo-root .
```

Reuse the structural redaction, secret scanning, preservation hashing, JSONL
handling, and integrity code. Adapt the manifest normalization and expected
capture/layer counts to your own workflow; this captured run intentionally
validates its known five-layer, ten-attempt shape.

The sanitizer must remove:

- messages whose role is `system` or `developer`;
- system/developer prompt attributes and events;
- available tool/function definitions, schemas, catalogs, and descriptions;
- sandbox and launcher policy payloads;
- credentials, authorization headers, cookies, private keys, tokens, and
  credential-bearing URLs.

It should preserve:

- explicit user/delegation prompts;
- assistant responses;
- actual tool invocation names;
- actual tool arguments, results, errors, IDs, and timing;
- trace/span IDs and resource attributes;
- source code and commands, subject to your publication policy.

Record every redaction with category, count, JSON path/key, source file,
replacement marker, and SHA-256 of the original value—never the original
confidential value.

### 9. Validate before publishing

At minimum, automate these gates:

- parse every generated JSON and JSONL record;
- prove no system/developer-role content or tool-definition/schema payload
  remains;
- compare aggregate hashes to prove allowed user/assistant/tool-call evidence
  survived unchanged;
- scan the complete prospective tracked tree for credentials;
- verify every artifact-integrity hash, size, and line count;
- enforce GitHub's per-file size limit;
- verify prompt → session → attempt → trace → commit → PR → merge joins;
- serve the dashboard over HTTP and test first render, path traversal, and
  progressive expansion;
- inspect the final Git diff for raw captures, transcripts, runtime packages,
  or unrelated files.

Publish only after all gates pass.

## Security and evidence boundaries

| Keep private | Safe to publish after validation |
|---|---|
| Raw OTel captures | Structurally sanitized OTel JSONL |
| Raw CLI stdout and transcripts | Exact explicit prompts that pass secret scanning |
| Hidden system/developer instructions | Hash-addressed redaction markers |
| Tool definitions and schemas | Actual tool calls, arguments, results, and errors |
| Credentials and auth configuration | Public branch, commit, PR, and merge metadata |
| Private trace workbooks | Curated workbook with structural safety validation |
| Internal launcher/runtime details | Normalized host audit and manifest |

The correct boundary is semantic, not keyword-based. A user prompt containing
the word “instructions” is not automatically confidential; a nested
system-prompt field serialized inside a JSON string is.

## Known limitation

This proof of concept demonstrates **host-driven logical lineage**. Separate
Copilot processes are connected through stable session IDs, parent IDs,
invocation metadata, host audit records, and Git/GitHub evidence.

It does not claim:

- operating-system parent/child process nesting;
- W3C `traceparent` propagation between separate Copilot sessions;
- that OTel alone proves PR or merge lineage without the Git/GitHub joins.

Those limitations are explicit in the manifest and dashboard so the evidence
does not overstate what was captured.
