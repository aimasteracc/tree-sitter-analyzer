#!/usr/bin/env bash
# Install local git hooks that block destructive operations on protected branches.
#
# Pain-05: the repo previously had NO local branch-guard hook. Server-side
# protection in .github/workflows/branch-protection.yml only covers `main` and
# can't stop a local `git push --force` from clobbering the autonomous-dev
# branch where 24/7 dogfood work happens.
#
# Run once per clone:  ./scripts/install-git-hooks.sh
# Idempotent — overwrites any existing pre-push hook with the same name.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOK_PATH="$REPO_ROOT/.git/hooks/pre-push"

cat > "$HOOK_PATH" <<'HOOK'
#!/usr/bin/env bash
# Pre-push branch-guard (pain-05).
#
# Blocks:
#   - any push to a protected branch with --force / --force-with-lease
#   - any push that deletes a protected branch (push :branch / --delete)
#
# Protected list — keep in sync with .github/workflows/branch-protection.yml.
# Override per-push:  GUARD=OFF git push ...   (only when you mean it)
PROTECTED_BRANCHES=(
    "main"
    "master"
    "feat/autonomous-dev"
    "feat/consolidated"
)

if [[ "${GUARD:-}" == "OFF" ]]; then
    echo "branch-guard: GUARD=OFF — bypass requested, allowing push" >&2
    exit 0
fi

remote="$1"
url="$2"

# Each line on stdin is: <local_ref> <local_sha> <remote_ref> <remote_sha>
zero="0000000000000000000000000000000000000000"
while read -r local_ref local_sha remote_ref remote_sha; do
    # Strip refs/heads/ prefix
    branch="${remote_ref#refs/heads/}"
    is_protected=0
    for p in "${PROTECTED_BRANCHES[@]}"; do
        if [[ "$branch" == "$p" ]]; then
            is_protected=1
            break
        fi
    done
    [[ $is_protected -eq 0 ]] && continue

    # Deletion (local sha is all zeros)
    if [[ "$local_sha" == "$zero" ]]; then
        echo "branch-guard: REFUSING to delete protected branch '$branch'." >&2
        echo "branch-guard: If you really need to, run:  GUARD=OFF git push $remote :$branch" >&2
        exit 1
    fi

    # Non-fast-forward (force push) — remote_sha not reachable from local_sha
    if [[ "$remote_sha" != "$zero" ]]; then
        if ! git merge-base --is-ancestor "$remote_sha" "$local_sha" 2>/dev/null; then
            echo "branch-guard: REFUSING force-push to protected branch '$branch'." >&2
            echo "branch-guard: Local is not a fast-forward of the remote." >&2
            echo "branch-guard: If you really need to, run:  GUARD=OFF git push --force ..." >&2
            exit 1
        fi
    fi
done

exit 0
HOOK

chmod +x "$HOOK_PATH"

echo "✓ Installed pre-push branch-guard hook at:"
echo "  $HOOK_PATH"
echo ""
echo "Protected branches: main, master, feat/autonomous-dev, feat/consolidated"
echo "Override (escape hatch):  GUARD=OFF git push ..."
