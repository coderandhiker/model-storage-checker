Resume the same logical layer-5 session and complete the authorized amend. This prompt resolves the ambiguity that caused attempt 2 to revert its changes.

Authoritative backward-compatibility contract:
- Do not change or weaken the existing test `test_ollama.OllamaCliTests.test_empty_inventory_has_clear_text_output`.
- The actual established exact output in this repository is `ollama: ok (0 models)\n`; preserve it byte-for-byte for an explicitly selected Ollama provider.
- The earlier phrase `No Ollama models found.` was descriptive, not an instruction to replace the repository's tested output.
- Preserve analogous existing exact output contracts for any explicitly selected single provider.

Root fix:
- The regression is only that layer 5 appends the unified storage summary and cleanup-candidate section to explicit single-provider text output.
- Route the unified summary section only through the unified/all-provider text reporting path, such as when no explicit `--provider` was selected.
- Do not append unified summary text when the user explicitly selects one provider.
- Keep JSON behavior and the intended all-provider text summary intact.
- Apply the smallest architecture-consistent change and add focused regression coverage only if it strengthens this distinction without replacing existing coverage.

Immutable lineage:
- Session ID: a3def810-4c47-4cbd-9c3b-78fcc833cc4a
- Parent session ID: 4a60b396-7386-40e7-a530-b073988a07f7
- Branch: coderandhiker-v2-add-cleanup-reporting
- Worktree: /Users/chris/dev/copilot-worktrees/model-storage-checker-lineage-run-2-20260922T184143Z/5-cleanup-reporting
- Layer-4 parent: c039b2abc8ad8b498f13104d2b7ffd3410939701
- Current layer-5 commit to amend: 1e4ae08440dab258965feb0617aace51c8077ac1
- Exact final subject: feat: add storage summary and cleanup candidates

Do not alter layers 1-4 and do not create a second layer-5 commit. Amend only the existing layer-5 commit. Production dependencies remain standard library only. Do not launch another Copilot session or perform any push, PR, issue, release, gist, remote export, or publication action.

Use `/Users/chris/.local/share/uv/python/cpython-3.11-macos-aarch64-none/bin/python3.11` and run:
1. `test_ollama.OllamaCliTests.test_empty_inventory_has_clear_text_output`
2. Relevant Ollama, reporting, and CLI tests
3. Full unittest discovery under `tests`

Amend through the configured worktree-local hook. Preserve exact subject, exactly one required Copilot App co-author trailer, and exactly one matching session trailer. Do not add the session trailer manually. Remove `.copilot-hooks/` after the amend and leave the worktree clean.
