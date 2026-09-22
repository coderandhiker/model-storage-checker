# Implementation Layer 2: Ollama Model Inventory

You are implementation layer 2 of 5 in local-only run 2 for `coderandhiker/model-storage-checker`. This session is launched directly by the host App as part of logical host-driven orchestration. Do not launch another Copilot CLI or any other Copilot session.

## Assigned identity

- Session ID: `d8d12118-ec2b-4fe1-abdd-9abfa0c8e755`
- Parent session ID: `4a60b396-7386-40e7-a530-b073988a07f7`
- Layer name: `ollama-inventory`
- Branch: `coderandhiker-v2-add-ollama-inventory`
- Base branch: `coderandhiker-v2-bootstrap-model-checker`
- Worktree: `/Users/chris/dev/copilot-worktrees/model-storage-checker-lineage-run-2-20260922T184143Z/2-ollama-inventory`
- Exact commit subject: `feat: add Ollama model inventory`

## Required implementation

Extend the existing checker with a local Ollama inventory provider that:

- Calls the local Ollama `/api/tags` endpoint using Python standard-library networking.
- Supports a configurable base URL and timeout through the established CLI/configuration patterns.
- Maps API data into the existing typed records and provider-result abstractions.
- Produces deterministic JSON and clear text output through the existing output paths.
- Distinguishes provider unavailable, malformed response, and successful empty inventory outcomes.
- Adds focused mock-based tests for successful mapping, configuration, unavailable service, malformed data, and empty results.
- Updates the README only as needed to document Ollama usage, configuration, and outcomes.

Preserve layer 1 behavior and interfaces unless a small compatible refinement is necessary for the Ollama integration.

## Mandatory constraints

- Raw capture remains local. Never print, summarize, copy, commit, or publish telemetry contents.
- Do not push or perform any pull request, issue, release, gist, remote export, or other GitHub write operation.
- Work only in the assigned worktree and assigned branch. Never alter `main`, another branch, another worktree, or any earlier layer commit.
- Before editing, verify the current branch is exactly `coderandhiker-v2-add-ollama-inventory` and its `HEAD` is the expected tip of base branch `coderandhiker-v2-bootstrap-model-checker`, with no layer-2 commits already present. Stop and report failure if the branch or base is not exact.
- Inspect the existing code and tests before editing. Make precise changes limited to this layer.
- Production dependencies must remain Python standard library only.
- Use Python 3.11+ and preserve type safety, explicit errors, deterministic JSON, and clear text output.
- Create exactly one commit for this layer with the exact subject `feat: add Ollama model inventory`.
- The commit message must contain exactly one trailer: `Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>`.
- Do not manually add a `Copilot-Session-Id` trailer. The host-provided `prepare-commit-msg` hook will add exactly one from `COPILOT_AGENT_SESSION_ID`.
- Do not reset, rebase, amend, squash, bypass hooks, or modify earlier commits.
- Run targeted tests and the full standard-library unittest suite when practical.
- All provider discovery is read-only. Never delete, prune, or stop Docker resources or models.
- Leave the worktree clean after the single commit.
- Stop and report failure if the exact commit, test, branch/base, hook-trailer, or cleanliness contract cannot be met.

## Completion contract

Before finishing, verify:

1. The branch and worktree are the assigned ones.
2. This layer produced exactly one new commit on the expected base branch tip.
3. The commit subject is exact and the commit contains exactly one required co-author trailer and exactly one hook-added session-ID trailer.
4. The worktree is clean.
5. No remote or publication action occurred.

In the final response, concisely state the commit hash and subject, files changed, exact test commands and outcomes, and the final cleanliness check. Do not print telemetry.
