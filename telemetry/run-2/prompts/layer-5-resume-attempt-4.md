Resume the same logical layer-5 session and complete the authorized amend. Attempt 3 reached the targeted test but the tool sandbox aborted the UV-managed Python path with exit code 134, so it reverted cleanly without changing the commit.

Use `/opt/homebrew/bin/python3.14` for all child-side tests in this attempt. It is a Python 3.11+ compatible runtime accessible to the tool sandbox. The host will independently validate the final result with Python 3.11.

Apply the previously clarified root fix:
- Preserve the existing exact test and explicit Ollama output `ollama: ok (0 models)\n`.
- Preserve analogous existing explicit single-provider output contracts.
- Show the new unified storage summary and cleanup-candidate text only in the unified/all-provider path, such as when no explicit `--provider` is selected.
- Do not append unified summary text to an explicitly selected provider response.
- Keep intended all-provider text and JSON reporting behavior.
- Make the smallest architecture-consistent change and add focused coverage if useful.

Lineage and commit contract:
- Session ID: a3def810-4c47-4cbd-9c3b-78fcc833cc4a
- Parent session ID: 4a60b396-7386-40e7-a530-b073988a07f7
- Branch: coderandhiker-v2-add-cleanup-reporting
- Layer-4 parent: c039b2abc8ad8b498f13104d2b7ffd3410939701
- Current layer-5 commit to amend: 1e4ae08440dab258965feb0617aace51c8077ac1
- Final subject: feat: add storage summary and cleanup candidates
- Amend only layer 5; do not alter layers 1-4 and do not create a second layer-5 commit.
- Retain exactly one required Copilot App co-author trailer and one hook-added matching session trailer.
- Do not bypass hooks or add the session trailer manually.

Run with `/opt/homebrew/bin/python3.14`:
1. The exact failing Ollama test.
2. Relevant Ollama, reporting, and CLI tests.
3. Full unittest discovery under tests.

Remove `.copilot-hooks/` after the successful amend and leave the worktree clean. Do not launch another Copilot session or perform any push, PR, issue, release, gist, remote export, telemetry commit, or publication action.
