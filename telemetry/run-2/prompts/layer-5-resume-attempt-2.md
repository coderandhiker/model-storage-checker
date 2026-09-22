Resume the existing logical layer-5 implementation session and correct the single backward-compatibility regression by amending only the current layer-5 commit.

Identity and immutable lineage:
- Session ID: a3def810-4c47-4cbd-9c3b-78fcc833cc4a
- Parent session ID: 4a60b396-7386-40e7-a530-b073988a07f7
- Branch: coderandhiker-v2-add-cleanup-reporting
- Worktree: /Users/chris/dev/copilot-worktrees/model-storage-checker-lineage-run-2-20260922T184143Z/5-cleanup-reporting
- Layer-4 parent commit: c039b2abc8ad8b498f13104d2b7ffd3410939701
- Existing layer-5 commit to amend: 1e4ae08440dab258965feb0617aace51c8077ac1
- Exact commit subject after amend: feat: add storage summary and cleanup candidates

This is explicit authorization to amend only the existing layer-5 commit. Do not alter, reset, rebase, amend, or rewrite layers 1-4. Do not create a second layer-5 commit.

Root regression:
- The full Python 3.11 suite ran 49 tests; only `test_ollama.OllamaCliTests.test_empty_inventory_has_clear_text_output` failed.
- The new unified storage summary and cleanup-candidate text is appended indiscriminately to an explicitly selected single-provider response.
- Preserve the established exact provider-specific empty text output, including `No Ollama models found.` and analogous existing provider contracts.
- Show the new unified storage summary/cleanup-candidate section only in the intended unified or all-provider reporting path, not for an explicitly selected single provider.
- Fix the root CLI/reporting routing behavior rather than weakening or deleting the existing test. Add focused regression coverage if needed.

Execution constraints:
- Inspect the existing CLI and reporting architecture and make the smallest correct change.
- Production dependencies remain Python standard library only.
- Never delete, prune, stop, or otherwise mutate models, containers, or images.
- Do not launch another Copilot session.
- Do not push, publish, create/edit a pull request, issue, release, gist, or use any GitHub write operation.
- Raw capture remains local.

Validation commands must use the existing Python 3.11 interpreter:
`/Users/chris/.local/share/uv/python/cpython-3.11-macos-aarch64-none/bin/python3.11`

Run:
1. The exact previously failing test.
2. Relevant Ollama, reporting, and CLI tests.
3. The full standard-library unittest suite.

Commit contract:
- Amend the existing layer-5 commit so the branch remains exactly one commit above layer 4.
- Preserve exact subject `feat: add storage summary and cleanup candidates`.
- Include exactly one `Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>` trailer.
- Do not manually add `Copilot-Session-Id`; the worktree-local prepare-commit-msg hook must leave exactly one `Copilot-Session-Id: a3def810-4c47-4cbd-9c3b-78fcc833cc4a`.
- Do not bypass hooks.
- Remove the untracked `.copilot-hooks/` directory after the successful amend.
- Leave the worktree clean.

Report the focused and full test commands/results, amended commit SHA, and clean status. Stop and report failure if the exact amend, tests, trailers, parent commit, or cleanliness contract cannot be met.
