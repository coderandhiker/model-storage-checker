Resume the existing layer-1 implementation session in the same worktree and finish the original contract.

The implementation files remain staged and the previous process exited without a commit only because the host-provided prepare-commit-msg hook was outside the tool sandbox and could not be executed. The host has now placed the same untracked hook at `.copilot-hooks/prepare-commit-msg`, configured `core.hooksPath` to that directory, and configured `.copilot-hooks/` as excluded from Git.

Do not launch another Copilot session. Do not push, publish, or use GitHub write operations. Do not reset, rebase, amend, squash, or rewrite anything.

1. Verify the staged implementation still satisfies the complete layer-1 prompt and that `.copilot-hooks/` is not staged.
2. Run the targeted tests and full standard-library unittest suite again.
3. Create exactly one commit with exact subject `feat: bootstrap model storage checker`.
4. Include exactly one `Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>` trailer.
5. Do not add `Copilot-Session-Id` manually; the local hook must add exactly one matching `fcde51a0-d70c-4ee9-a538-c2f335c28058`.
6. Remove the untracked `.copilot-hooks/` directory after the successful commit and leave the worktree clean.

Stop and report failure if any part of the original commit, tests, trailers, or cleanliness contract cannot be met.
