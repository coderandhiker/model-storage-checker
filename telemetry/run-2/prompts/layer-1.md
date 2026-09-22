# Implementation Layer 1: Bootstrap Model Storage Checker

You are implementation layer 1 of 5 in local-only run 2 for `coderandhiker/model-storage-checker`. This session is launched directly by the host App as part of logical host-driven orchestration. Do not launch another Copilot CLI or any other Copilot session.

## Assigned identity

- Session ID: `fcde51a0-d70c-4ee9-a538-c2f335c28058`
- Parent session ID: `4a60b396-7386-40e7-a530-b073988a07f7`
- Layer name: `bootstrap-model-checker`
- Branch: `coderandhiker-v2-bootstrap-model-checker`
- Base branch: `origin/main`
- Required base commit: `c445986e1816a1606384d04a48a6bc0bac86eff3`
- Worktree: `/Users/chris/dev/copilot-worktrees/model-storage-checker-lineage-run-2-20260922T184143Z/1-bootstrap-model-checker`
- Exact commit subject: `feat: bootstrap model storage checker`

## Required implementation

Bootstrap a Python 3.11+ model storage checker with:

- A src-layout package.
- A `pyproject.toml` using setuptools and defining a console entry point.
- Typed record, provider-result, and error abstractions suitable for later provider layers.
- An argparse CLI with clear text output and deterministic JSON output.
- Explicit behavior for unavailable and unsupported providers or operations.
- Standard-library `unittest` coverage.
- A suitable `.gitignore`.
- A concise README covering installation, invocation, output modes, and the current unsupported-provider scope.

Do not implement Ollama, LM Studio, or Docker discovery in this layer. Establish clean interfaces that later layers can extend without speculative complexity.

## Mandatory constraints

- Raw capture remains local. Never print, summarize, copy, commit, or publish telemetry contents.
- Do not push or perform any pull request, issue, release, gist, remote export, or other GitHub write operation.
- Work only in the assigned worktree and assigned branch. Never alter `main`, another branch, another worktree, or any earlier layer commit.
- Before editing, verify the current branch is exactly `coderandhiker-v2-bootstrap-model-checker`, `HEAD` is based directly on `origin/main`, and the base commit is exactly `c445986e1816a1606384d04a48a6bc0bac86eff3`. Stop and report failure if any identity or base check fails.
- Inspect the existing code and tests before editing. Make precise changes limited to this layer.
- Production dependencies must remain Python standard library only. Build tooling may use the declared setuptools backend, but runtime code must not add third-party dependencies.
- Use Python 3.11+ and preserve type safety, explicit errors, deterministic JSON, and clear text output.
- Create exactly one commit for this layer with the exact subject `feat: bootstrap model storage checker`.
- The commit message must contain exactly one trailer: `Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>`.
- Do not manually add a `Copilot-Session-Id` trailer. The host-provided `prepare-commit-msg` hook will add exactly one from `COPILOT_AGENT_SESSION_ID`.
- Do not reset, rebase, amend, squash, bypass hooks, or modify earlier commits.
- Run targeted tests and the full standard-library unittest suite when practical.
- Provider discovery is read-only. Never delete, prune, or stop Docker resources or models.
- Leave the worktree clean after the single commit.
- Stop and report failure if the exact commit, test, branch/base, hook-trailer, or cleanliness contract cannot be met.

## Completion contract

Before finishing, verify:

1. The branch and worktree are the assigned ones.
2. This layer produced exactly one new commit based on the required base.
3. The commit subject is exact and the commit contains exactly one required co-author trailer and exactly one hook-added session-ID trailer.
4. The worktree is clean.
5. No remote or publication action occurred.

In the final response, concisely state the commit hash and subject, files changed, exact test commands and outcomes, and the final cleanliness check. Do not print telemetry.
