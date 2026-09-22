# Implementation Layer 4: Docker Image and Container Inventory

You are implementation layer 4 of 5 in local-only run 2 for `coderandhiker/model-storage-checker`. This session is launched directly by the host App as part of logical host-driven orchestration. Do not launch another Copilot CLI or any other Copilot session.

## Assigned identity

- Session ID: `c20d130e-f890-431d-aee8-32801bad8b31`
- Parent session ID: `4a60b396-7386-40e7-a530-b073988a07f7`
- Layer name: `docker-inventory`
- Branch: `coderandhiker-v2-add-docker-inventory`
- Base branch: `coderandhiker-v2-add-lm-studio-inventory`
- Worktree: `/Users/chris/dev/copilot-worktrees/model-storage-checker-lineage-run-2-20260922T184143Z/4-docker-inventory`
- Exact commit subject: `feat: add Docker image and container inventory`

## Required implementation

Extend the existing checker with read-only Docker inventory:

- Use the Docker CLI only; do not add an SDK dependency.
- Invoke subprocesses with explicit argument arrays and no shell interpolation.
- Request machine-readable Docker JSON template output and parse it strictly.
- Inventory every image and all containers, including stopped containers.
- Include cleanup-relevant metadata such as identifiers, references/names, sizes where Docker reports them, state/status, creation information, and image relationships.
- If AI-related classification is provided, label it clearly as an optional heuristic and keep the underlying complete Docker inventory available regardless of classification.
- Distinguish missing Docker CLI, unavailable daemon, permission denied, timeout, malformed output, and successful empty inventory outcomes.
- Add focused mocked subprocess tests for argument safety, all inventory mappings, each error category, malformed and empty output, and optional heuristic labeling.
- Update the README only as needed to document Docker inventory, read-only behavior, and failure outcomes.

Docker discovery must never mutate resources. Do not invoke commands that remove, prune, stop, kill, restart, create, pull, or otherwise change Docker images, containers, volumes, networks, or daemon state.

## Mandatory constraints

- Raw capture remains local. Never print, summarize, copy, commit, or publish telemetry contents.
- Do not push or perform any pull request, issue, release, gist, remote export, or other GitHub write operation.
- Work only in the assigned worktree and assigned branch. Never alter `main`, another branch, another worktree, or any earlier layer commit.
- Before editing, verify the current branch is exactly `coderandhiker-v2-add-docker-inventory` and its `HEAD` is the expected tip of base branch `coderandhiker-v2-add-lm-studio-inventory`, with no layer-4 commits already present. Stop and report failure if the branch or base is not exact.
- Inspect the existing code and tests before editing. Make precise changes limited to this layer.
- Production dependencies must remain Python standard library only.
- Use Python 3.11+ and preserve type safety, explicit errors, deterministic JSON, and clear text output.
- Create exactly one commit for this layer with the exact subject `feat: add Docker image and container inventory`.
- The commit message must contain exactly one trailer: `Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>`.
- Do not manually add a `Copilot-Session-Id` trailer. The host-provided `prepare-commit-msg` hook will add exactly one from `COPILOT_AGENT_SESSION_ID`.
- Do not reset, rebase, amend, squash, bypass hooks, or modify earlier commits.
- Run targeted tests and the full standard-library unittest suite when practical.
- Never delete, prune, stop, or otherwise mutate Docker resources or models. Provider discovery is read-only.
- Leave the worktree clean after the single commit.
- Stop and report failure if the exact commit, test, branch/base, hook-trailer, read-only, or cleanliness contract cannot be met.

## Completion contract

Before finishing, verify:

1. The branch and worktree are the assigned ones.
2. This layer produced exactly one new commit on the expected base branch tip.
3. The commit subject is exact and the commit contains exactly one required co-author trailer and exactly one hook-added session-ID trailer.
4. The worktree is clean.
5. No Docker mutation, remote, or publication action occurred.

In the final response, concisely state the commit hash and subject, files changed, exact test commands and outcomes, and the final cleanliness check. Do not print telemetry.
