# Implementation Layer 5: Storage Summary and Cleanup Candidates

You are implementation layer 5 of 5 in local-only run 2 for `coderandhiker/model-storage-checker`. This session is launched directly by the host App as part of logical host-driven orchestration. Do not launch another Copilot CLI or any other Copilot session.

## Assigned identity

- Session ID: `a3def810-4c47-4cbd-9c3b-78fcc833cc4a`
- Parent session ID: `4a60b396-7386-40e7-a530-b073988a07f7`
- Layer name: `cleanup-reporting`
- Branch: `coderandhiker-v2-add-cleanup-reporting`
- Base branch: `coderandhiker-v2-add-docker-inventory`
- Worktree: `/Users/chris/dev/copilot-worktrees/model-storage-checker-lineage-run-2-20260922T184143Z/5-cleanup-reporting`
- Exact commit subject: `feat: add storage summary and cleanup candidates`

## Required implementation

Complete the checker with unified reporting across Ollama, LM Studio, Docker images, and Docker containers:

- Provide coherent text and deterministic JSON summaries using the existing records and provider-result abstractions.
- Include totals grouped by provider and record/resource type, with size totals where sizes are known.
- Represent unknown sizes explicitly rather than treating them as zero.
- Produce cleanup-oriented advisory candidates using transparent, conservative, deterministic rules.
- Clearly report the rule and evidence for every candidate, distinguish heuristics from facts, and avoid unsafe claims when metadata is incomplete.
- Keep all recommendations advisory only. Do not add any deletion, pruning, stopping, or mutation operation.
- Preserve provider errors and partial results in unified reports rather than silently discarding them.
- Add focused tests covering aggregation, provider/type totals, unknown sizes, deterministic text and JSON, partial failures, conservative candidate rules, non-candidates, and advisory labeling.
- Update the README with concise summary and cleanup-candidate documentation, emphasizing that the tool is read-only.

Preserve all existing provider-specific behavior.

## Mandatory constraints

- Raw capture remains local. Never print, summarize, copy, commit, or publish telemetry contents.
- Do not push or perform any pull request, issue, release, gist, remote export, or other GitHub write operation.
- Work only in the assigned worktree and assigned branch. Never alter `main`, another branch, another worktree, or any earlier layer commit.
- Before editing, verify the current branch is exactly `coderandhiker-v2-add-cleanup-reporting` and its `HEAD` is the expected tip of base branch `coderandhiker-v2-add-docker-inventory`, with no layer-5 commits already present. Stop and report failure if the branch or base is not exact.
- Inspect the existing code and tests before editing. Make precise changes limited to this layer.
- Production dependencies must remain Python standard library only.
- Use Python 3.11+ and preserve type safety, explicit errors, deterministic JSON, and clear text output.
- Create exactly one commit for this layer with the exact subject `feat: add storage summary and cleanup candidates`.
- The commit message must contain exactly one trailer: `Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>`.
- Do not manually add a `Copilot-Session-Id` trailer. The host-provided `prepare-commit-msg` hook will add exactly one from `COPILOT_AGENT_SESSION_ID`.
- Do not reset, rebase, amend, squash, bypass hooks, or modify earlier commits.
- Run targeted tests and the full standard-library unittest suite when practical.
- Never delete, prune, stop, or otherwise mutate Docker resources or models. Provider discovery and cleanup reporting are strictly read-only.
- Leave the worktree clean after the single commit.
- Stop and report failure if the exact commit, test, branch/base, hook-trailer, read-only, or cleanliness contract cannot be met.

## Completion contract

Before finishing, verify:

1. The branch and worktree are the assigned ones.
2. This layer produced exactly one new commit on the expected base branch tip.
3. The commit subject is exact and the commit contains exactly one required co-author trailer and exactly one hook-added session-ID trailer.
4. The worktree is clean.
5. No resource mutation, remote, or publication action occurred.

In the final response, concisely state the commit hash and subject, files changed, exact test commands and outcomes, and the final cleanliness check. Do not print telemetry.
