You are the fully captured logical parent/orchestrator for a local-only model-storage-checker implementation lineage POC.

This is run 2 for coderandhiker/model-storage-checker. You are not an implementation layer. Do not edit any repository or worktree, do not launch another Copilot CLI, do not run implementation tests, and do not use GitHub write operations. Do not push, create/edit/reopen pull requests, create releases, or publish anything.

The host App session will launch five separately captured implementation Copilot CLI sessions after you exit. Your authoritative responsibility is to record delegation intent by creating five complete child prompt files and one machine-readable delegation plan. This is logical host-driven orchestration rather than OS process nesting or W3C trace propagation.

Run identity and paths:
- Run directory: /Users/chris/Desktop/AMD/model-storage-checker-lineage-run-2-20260922T184143Z
- Initial manifest (read-only to you): /Users/chris/Desktop/AMD/model-storage-checker-lineage-run-2-20260922T184143Z/run-manifest.json
- Delegation plan to create: /Users/chris/Desktop/AMD/model-storage-checker-lineage-run-2-20260922T184143Z/delegation-plan.json
- Canonical clone: /Users/chris/dev/model-storage-checker
- Verified clean origin/main: c445986e1816a1606384d04a48a6bc0bac86eff3
- Host App session ID: b69f2cba-e482-464a-824d-7f1efd452863
- Parent session ID: 4a60b396-7386-40e7-a530-b073988a07f7
- Worktree root: /Users/chris/dev/copilot-worktrees/model-storage-checker-lineage-run-2-20260922T184143Z
- Orchestration mode: host-driven
- Process nesting: false
- Linkage: poc.parent_session_id plus append-only driver-audit.jsonl

The host already preserved three failed nested smoke attempts as preflight evidence. Do not inspect or copy their raw contents or runtime packages. The limitation is that a Copilot CLI running inside the parent tool sandbox could not reliably bootstrap a second Copilot CLI.

Create exactly these five prompt files:
1. /Users/chris/Desktop/AMD/model-storage-checker-lineage-run-2-20260922T184143Z/prompts/layer-1.md
2. /Users/chris/Desktop/AMD/model-storage-checker-lineage-run-2-20260922T184143Z/prompts/layer-2.md
3. /Users/chris/Desktop/AMD/model-storage-checker-lineage-run-2-20260922T184143Z/prompts/layer-3.md
4. /Users/chris/Desktop/AMD/model-storage-checker-lineage-run-2-20260922T184143Z/prompts/layer-4.md
5. /Users/chris/Desktop/AMD/model-storage-checker-lineage-run-2-20260922T184143Z/prompts/layer-5.md

Every child prompt must be complete and self-contained. Include all shared constraints below plus its exact layer identity, session IDs, branch, base branch, worktree, commit subject, and layer-specific requirements.

Shared child constraints:
- The child is one implementation layer in local-only run 2 and must not launch other Copilot sessions.
- Raw capture remains local; never print or publish telemetry contents.
- No push, pull request, issue, release, gist, remote export, or other GitHub write operation.
- Work only in the assigned worktree and branch. Never alter main, another branch, another worktree, or earlier layer commits.
- Verify the assigned branch and expected base before editing. Do not reset, rebase, amend, squash, or bypass hooks.
- Create exactly one commit for the layer, with the exact subject given below.
- Include exactly one `Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>` trailer. Do not add a `Copilot-Session-Id` trailer manually; the host-provided prepare-commit-msg hook adds exactly one from COPILOT_AGENT_SESSION_ID.
- Leave the worktree clean.
- Production dependencies must remain Python standard library only.
- Use Python 3.11+ and preserve type safety, explicit errors, deterministic JSON, and clear text output.
- Inspect existing code and tests before editing. Make precise changes limited to the assigned layer.
- Run targeted tests and the full standard-library unittest suite when practical. Record the exact commands and outcomes in the final response.
- Never delete/prune/stop Docker resources or models. Provider discovery is read-only.
- Stop and report failure if the exact commit/test/cleanliness contract cannot be met.

Layer 1:
- Session ID: fcde51a0-d70c-4ee9-a538-c2f335c28058
- Parent session ID: 4a60b396-7386-40e7-a530-b073988a07f7
- Layer name: bootstrap-model-checker
- Branch: coderandhiker-v2-bootstrap-model-checker
- Base: origin/main at c445986e1816a1606384d04a48a6bc0bac86eff3
- Worktree: /Users/chris/dev/copilot-worktrees/model-storage-checker-lineage-run-2-20260922T184143Z/1-bootstrap-model-checker
- Exact commit subject: feat: bootstrap model storage checker
- Requirements: Python 3.11+ src-layout package; pyproject/setuptools console entry point; typed records, provider result, and error abstractions; argparse CLI; text and JSON output; explicit unavailable and unsupported behavior; stdlib unittest coverage; .gitignore; concise README. No provider implementation yet.

Layer 2:
- Session ID: d8d12118-ec2b-4fe1-abdd-9abfa0c8e755
- Parent session ID: 4a60b396-7386-40e7-a530-b073988a07f7
- Layer name: ollama-inventory
- Branch: coderandhiker-v2-add-ollama-inventory
- Base: coderandhiker-v2-bootstrap-model-checker
- Worktree: /Users/chris/dev/copilot-worktrees/model-storage-checker-lineage-run-2-20260922T184143Z/2-ollama-inventory
- Exact commit subject: feat: add Ollama model inventory
- Requirements: local Ollama `/api/tags` provider; configurable base URL and timeout; typed mapping; distinct unavailable, malformed, and empty outcomes; mock-based tests; focused README update.

Layer 3:
- Session ID: 3794ecb9-b919-444e-ac7b-34686c5b17d5
- Parent session ID: 4a60b396-7386-40e7-a530-b073988a07f7
- Layer name: lm-studio-inventory
- Branch: coderandhiker-v2-add-lm-studio-inventory
- Base: coderandhiker-v2-add-ollama-inventory
- Worktree: /Users/chris/dev/copilot-worktrees/model-storage-checker-lineage-run-2-20260922T184143Z/3-lm-studio-inventory
- Exact commit subject: feat: add LM Studio model inventory
- Requirements: OpenAI-compatible model-list API plus recursive on-disk model discovery with configurable roots; correct sizes, metadata, and stable deduplication; distinct API and filesystem errors; tempdir/mock tests; focused README update.

Layer 4:
- Session ID: c20d130e-f890-431d-aee8-32801bad8b31
- Parent session ID: 4a60b396-7386-40e7-a530-b073988a07f7
- Layer name: docker-inventory
- Branch: coderandhiker-v2-add-docker-inventory
- Base: coderandhiker-v2-add-lm-studio-inventory
- Worktree: /Users/chris/dev/copilot-worktrees/model-storage-checker-lineage-run-2-20260922T184143Z/4-docker-inventory
- Exact commit subject: feat: add Docker image and container inventory
- Requirements: Docker CLI only; argument arrays with no shell interpolation; machine-readable JSON template output; every image and all containers; cleanup-relevant metadata and clearly labeled optional AI heuristics; distinct missing CLI, daemon, permission, timeout, malformed, and empty outcomes; mocked tests; focused README update. Never mutate Docker resources.

Layer 5:
- Session ID: a3def810-4c47-4cbd-9c3b-78fcc833cc4a
- Parent session ID: 4a60b396-7386-40e7-a530-b073988a07f7
- Layer name: cleanup-reporting
- Branch: coderandhiker-v2-add-cleanup-reporting
- Base: coderandhiker-v2-add-docker-inventory
- Worktree: /Users/chris/dev/copilot-worktrees/model-storage-checker-lineage-run-2-20260922T184143Z/5-cleanup-reporting
- Exact commit subject: feat: add storage summary and cleanup candidates
- Requirements: unified reporting across Ollama, LM Studio, Docker images, and Docker containers; text and JSON summaries; provider/type totals; cleanup-oriented advisory candidates with transparent conservative rules; focused tests and docs. Never delete, prune, or stop anything.

Create delegation-plan.json as valid JSON with:
- schema_version, run, repository, parent_session_id, host_app_session_id
- orchestration object with mode `host-driven`, process_nesting false, and linkage `poc.parent_session_id+driver-audit`
- ordered children array with layer, layer_name, session_id, parent_session_id, branch, base_branch, worktree, prompt_path, commit_subject, and status `delegated`
- shared_constraints summary
- limitation summary for the failed nested-process approach
- publication object showing all remote/publication actions false

Do not change run-manifest.json. After creating and validating all six delegation artifacts, report only their paths and a concise confirmation. Do not include their full contents in your final response.
