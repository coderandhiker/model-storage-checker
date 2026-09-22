# Sanitized Copilot lineage evidence: run 2

This directory is the deterministic, publishable derivative of a private local
capture. The private source remains outside the repository. Raw CLI stdout,
raw transcripts, launcher scripts, runtime packages, and the original capture
directory are intentionally not committed.

## Evidence included

- 10 sanitized OTel JSONL capture files containing 770 records and 403 spans.
- Six logical sessions: one parent orchestrator and five delegated child
  sessions.
- 10 process attempts, including the recorded resume attempts.
- 10 exact explicit user/delegation prompt files copied byte-for-byte only
  after secret scanning.
- 10 compact usage summaries, sanitized driver audit records, normalized
  validation summaries, a public manifest, a redaction report, and artifact
  integrity metadata.
- Approved merged metadata for the five feature PRs (#6 through #10),
  including each base branch and verified head commit. The customer-facing
  evidence branch is `OTEL`; its separate package PR and release remain null.
- A curated companion workbook at
  [`../../docs/lineage/model-storage-checker-lineage-run-2.xlsx`](../../docs/lineage/model-storage-checker-lineage-run-2.xlsx)
  plus a structural safety report. This is not the private raw trace workbook.
- Hash-based preservation checks covering 20 user messages, 163 assistant
  messages, 240 tool messages, and 240 actual tool-call argument/result
  payloads.

The source run used host-driven orchestration. Parent/child relationships are
logical links based on session IDs, process-attempt records, and Git evidence.
They are not claims of operating-system process nesting or W3C `traceparent`
propagation.

## Structural redactions

The current package records 919 redactions or normalizations:

| Category | Count | Treatment |
|---|---:|---|
| `system_instructions` | 163 | Hidden system instruction payloads replaced with hash-addressed markers. |
| `tool_definitions` | 163 | Available tool/function definitions and schemas replaced. |
| `tool_definition_description` | 240 | Definition descriptions attached to tool spans replaced; actual tool names, calls, arguments, and results remain. |
| `available_context_catalog` | 30 | Available skill, custom-agent, and MCP-server catalogs replaced. |
| `sandbox_policy` | 33 | Runtime sandbox policy path payloads replaced. |
| `internal_launcher_runtime` | 154 | Internal launcher fields and non-provenance executable locations removed or normalized. |
| `local_absolute_path` | 86 | Nonessential artifact/code-summary paths normalized to published or repository-relative paths. |
| `unpublished_artifact_path` | 43 | Paths to intentionally omitted logs/transcripts replaced or removed. |
| `stale_intermediate_error` | 7 | Superseded failure/recovery fields removed from verified final records. |

Every entry in `redaction-report.json` includes the category, source file,
JSON path/key, SHA-256 of the original value, and the replacement marker. It
never includes the original redacted value.

The generated validation proves that system/tool-definition payloads changed,
while public user, assistant, tool-message, tool-argument, and tool-result hash
collections remained exact. The expanded secret scan found no credential
matches in the generated evidence.

## Layout

- `otel/`: one valid JSON object per line, preserving trace/span IDs,
  timestamps, resource data, model activity, public messages, and actual tool
  calls.
- `prompts/`: exact explicit orchestrator/delegation prompts.
- `usage/`: compact per-attempt usage summaries with repository-relative code
  paths.
- `validation/`: final and per-layer summaries plus sanitizer preservation
  checks.
- `manifest.json`: normalized repository/session/branch/commit/test/capture
  metadata. Each feature layer includes its merged PR metadata; the package-level
  `pull_request` and `release` fields remain null.
- `publication-metadata.json`: approved public PR overlay validated against
  every feature branch, base branch, and verified commit SHA.
- `driver-audit.jsonl`: sanitized logical process-attempt audit records.
- `redaction-report.json`: structural redaction ledger.
- `artifact-integrity.json`: SHA-256, byte size, and line count for every
  published file except the integrity file itself. Its own canonical content
  hash is recorded under `self_integrity`.
- `validation/workbook-safety.json`: package-only XLSX inspection covering
  macros, external relationships, embedded objects, external formula
  references, relationship types, and package entries without dumping cells.

## Capturing this level of fidelity in another repository

Full-fidelity capture is deliberately opt-in because it records exact user and
assistant messages plus actual tool arguments/results. Keep the raw capture and
helper clone private; commit only sanitizer output.

### 1. Install the helper locally but keep it out of Git

From the target repository:

```console
git clone <lineage-tooling-repository-url> .copilot-lineage-tools
mkdir -p .lineage-private
cat >> .gitignore <<'EOF'
/.copilot-lineage-tools/
/.lineage-private/
github_copilot_traces.xlsx
EOF
```

Ignored files remain available on disk to an agentic workflow. Because normal
search tools often skip ignored paths, prompts and automation should reference
the helper explicitly, for example:

```text
Use .copilot-lineage-tools/tools/lineage/sanitize_telemetry.py and
.copilot-lineage-tools/tools/lineage/build_dashboard.py. Read raw captures only
from .lineage-private/run-N and write publishable output to telemetry/run-N.
```

The sanitized `manifest.json`, OTel JSONL, and dashboard `data.json` can feed
the target repository's own web UI; the included Cytoscape UI is only one
renderer for the aggregate nodes, edges, expansions, filters, and detail
records.

### 2. Enable local full-content OTel capture

Give every logical parent/child session a stable UUID and every process attempt
its own output file:

```console
export PRIVATE_RUN="$PWD/.lineage-private/run-N"
export COPILOT_AGENT_SESSION_ID="$SESSION_ID"
export OTEL_SERVICE_NAME=github-copilot
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
export COPILOT_OTEL_FILE_EXPORTER_PATH="$PRIVATE_RUN/raw/$INVOCATION.jsonl"
export OTEL_RESOURCE_ATTRIBUTES="poc.name=$POC_NAME,poc.run=$RUN,poc.session_id=$SESSION_ID,poc.parent_session_id=$PARENT_SESSION_ID,poc.role=$ROLE,poc.layer=$LAYER,poc.invocation=$INVOCATION"

copilot --output-format=json --no-remote-export --no-auto-update
```

The critical fidelity settings are:

- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` for exact public
  messages and actual tool-call arguments/results.
- `COPILOT_OTEL_FILE_EXPORTER_PATH` for a private local JSONL capture per
  process attempt.
- `COPILOT_AGENT_SESSION_ID` plus `OTEL_RESOURCE_ATTRIBUTES` for logical
  parent/child, layer, role, and invocation linkage.
- `--output-format=json` for machine-readable host-driver observations.
- `--no-remote-export` so raw telemetry stays local.
- `--no-auto-update` (and a pinned CLI version) for reproducibility.

The POC also used `--allow-all-tools`, `--allow-all-paths`, and
`--no-ask-user` inside isolated worktrees. Those permissions are **not**
required for telemetry fidelity and must not be copied into a customer
workflow without an independent security review and equivalent host controls.
`--disable-builtin-mcps` is optional when reducing environmental variance.

### 3. Record host and Git lineage

The host driver should:

1. Write the exact explicit parent/delegation prompts into the private run
   directory.
2. Append sanitized process start/end, exit status, session IDs, attempt names,
   branches, and commit IDs to `driver-audit.jsonl`; record secret environment
   variable names only, never values.
3. Use one capture file per initial/resume attempt.
4. Add the logical Copilot session ID and Copilot co-author trailers to each
   feature commit.
5. Verify the stacked base/head SHA chain and test results before sanitization.

### 4. Enforce the private/public boundary

Never commit raw CLI stdout, transcripts, unredacted OTel, the private run
directory, credentials, or a raw trace workbook such as
`github_copilot_traces.xlsx`. The sanitizer must redact hidden system/developer
instructions, tool definitions/catalogs, sandbox policy payloads, and secrets
before anything is copied into tracked `telemetry/` or UI data.

## Regeneration

Use Python's standard library only:

```console
SOURCE_RUN=/path/to/private/model-storage-checker-lineage-run-2
python3 tools/lineage/sanitize_telemetry.py "$SOURCE_RUN" \
  --output telemetry/run-2 \
  --repo-root . \
  --package-branch OTEL \
  --package-commit 02460aed650fe0384e327bfb04cfccc35652e1f7
python3 tools/lineage/inspect_workbook.py \
  docs/lineage/model-storage-checker-lineage-run-2.xlsx \
  --output telemetry/run-2/validation/workbook-safety.json \
  --repo-root . \
  --expected-sha256 11c81dcba23eea8ce127cec28deddeea14c53a6aae43926a4f8f20fbd645d394
python3 tools/lineage/build_dashboard.py \
  --telemetry-root telemetry/run-2 \
  --output docs/lineage/data.json \
  --repo-root .
```

The sanitizer requires exactly 10 OTel capture files, fails closed if an
explicit prompt contains a secret pattern, and fails if confidential structural
fields or credential patterns remain in generated JSON. When
`telemetry/run-2/publication-metadata.json` exists, it is retained, validated,
and merged into the public manifest automatically.

## Updating approved PR or release metadata

The current overlay records merged, non-draft feature PRs #6 through #10.
The OTEL package PR and release remain null. Update
`publication-metadata.json` only with approved public values:

```json
{
  "pull_requests": {
    "branch-name": {
      "number": 123,
      "url": "https://github.com/owner/repository/pull/123",
      "state": "merged",
      "draft": false,
      "base": "parent-branch",
      "head_sha": "0123456789abcdef0123456789abcdef01234567"
    }
  },
  "release": null
}
```

```console
python3 tools/lineage/sanitize_telemetry.py "$SOURCE_RUN" \
  --output telemetry/run-2 \
  --repo-root . \
  --package-branch OTEL \
  --package-commit 02460aed650fe0384e327bfb04cfccc35652e1f7
python3 tools/lineage/inspect_workbook.py \
  docs/lineage/model-storage-checker-lineage-run-2.xlsx \
  --output telemetry/run-2/validation/workbook-safety.json \
  --repo-root .
python3 tools/lineage/build_dashboard.py \
  --telemetry-root telemetry/run-2 \
  --output docs/lineage/data.json \
  --repo-root .
```

The sanitizer rejects missing feature branches, unknown branches, malformed
GitHub URLs, or base/head values that disagree with the verified lineage. The
dashboard builder auto-loads the retained overlay. Neither tool performs any
GitHub operation.
