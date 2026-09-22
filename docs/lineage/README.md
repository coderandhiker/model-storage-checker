# Offline lineage dashboard

This dashboard visualizes the sanitized evidence in `telemetry/run-2/` as:

> origin prompt → parent orchestrator → five logical child sessions → process
> attempts → OTel traces → model/tool activity → commits → stacked branches
> and live feature PRs → package PR/release placeholders

The graph labels each evidence source as `captured in OTel`, `driver audit`,
`Git commit/trailer`, or `planned/live GitHub metadata`. It also states the
host-driven, non-W3C orchestration limitation in the interface.

## Companion workbook

[`model-storage-checker-lineage-run-2.xlsx`](model-storage-checker-lineage-run-2.xlsx)
is the curated, publishable workbook for this evidence package. It contains six
worksheets: the first summary worksheet (currently named `Sheet1`), `Lineage`,
`Captures`, `Pull Requests`, `Redactions`, and `Validation`.

The workbook is a simple local OOXML package: no macros, formulas, external
links, hyperlinks, embedded objects, drawings, media, or unexpected
relationships/package entries. Its SHA-256 is
`8f92fc4226afdfa638383093afaa63aae06401a4289cb0853aaf4a03bd3a8f72`;
the deterministic structural report is
[`../../telemetry/run-2/validation/workbook-safety.json`](../../telemetry/run-2/validation/workbook-safety.json).
It is distinct from any private raw trace workbook, which must remain outside
the tracked package.

## Serve locally

Browsers block `fetch()` for local `file://` pages, so use any basic static
HTTP server from the repository root:

```console
python3 -m http.server --directory docs/lineage 8000
```

Then open <http://127.0.0.1:8000/>.

The dashboard has no runtime CDN or package-manager dependency. Cytoscape.js
3.30.4 and its MIT license are pinned under `vendor/`; source URL, version, and
SHA-256 are recorded in `vendor/README.md`.

## Reusing in another repository or UI

Clone the lineage helper into an ignored local subdirectory such as
`.copilot-lineage-tools/`, keep raw captures in an ignored
`.lineage-private/`, and explicitly point the agent or automation at those
paths. Ignoring the helper prevents accidental publication but does not remove
it from the local workspace; explicit paths remain available to the agent even
when normal searches skip ignored files.

Commit only the sanitized `telemetry/run-N/` outputs and the UI artifacts your
repository needs. A custom web UI can consume `data.json` directly: it contains
aggregate nodes/edges, on-demand expansions, filters, provenance, status, and
master-detail payloads. The exact capture environment, OTel variables, CLI
flags, driver responsibilities, and security boundary are documented in
[`../../telemetry/run-2/README.md`](../../telemetry/run-2/README.md#capturing-this-level-of-fidelity-in-another-repository).

## Interaction guide

- Select a node to inspect its sanitized evidence, status, and provenance.
- Double-click a trace/model/tool aggregate, or select it and choose
  **Expand selected**, to reveal its detailed nodes.
- Choose **Collapse selected** to return to the aggregate view.
- Filter by layer or session, and search by prompt/session/tool/commit text.
- Use **Fit** to frame visible nodes and **Reset** to restore the initial view.
- With graph focus, press <kbd>Enter</kbd> or <kbd>Space</kbd> to expand,
  <kbd>Escape</kbd> to collapse, <kbd>F</kbd> to fit, or <kbd>/</kbd> to focus
  search.
- Follow the selected-node breadcrumbs to navigate the primary evidence path.

Long prompt, message, command, tool, and source-code fields are inserted with
DOM `textContent`, never interpreted as HTML.

## Rebuild data

After regenerating `telemetry/run-2/`, run:

```console
python3 tools/lineage/inspect_workbook.py \
  docs/lineage/model-storage-checker-lineage-run-2.xlsx \
  --output telemetry/run-2/validation/workbook-safety.json \
  --repo-root .
python3 tools/lineage/build_dashboard.py \
  --telemetry-root telemetry/run-2 \
  --output docs/lineage/data.json \
  --repo-root .
```

The builder automatically loads the approved
`telemetry/run-2/publication-metadata.json` overlay. An alternate approved file
can be supplied with `--publication-metadata`; the format and validation rules
are documented in `telemetry/run-2/README.md`. The builder performs no network
writes.
