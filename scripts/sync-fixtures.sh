#!/usr/bin/env bash
# sync-fixtures.sh — Copy canonical conformance fixtures from apcore spec repo.
#
# Usage:
#   ./scripts/sync-fixtures.sh              # auto-discover from sibling or $APCORE_SPEC_REPO
#   ./scripts/sync-fixtures.sh /path/to/apcore
#
# This script copies conformance/fixtures/*.json from the apcore protocol
# spec repo into tests/conformance/fixtures/ so that CI can run conformance
# tests without access to the sibling spec repo.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEST="$REPO_ROOT/tests/conformance/fixtures"

# --- Locate source ---
find_source() {
    # 1. Explicit argument
    if [ -n "${1:-}" ] && [ -d "$1/conformance/fixtures" ]; then
        echo "$1/conformance/fixtures"
        return
    fi

    # 2. $APCORE_SPEC_REPO env var
    if [ -n "${APCORE_SPEC_REPO:-}" ] && [ -d "$APCORE_SPEC_REPO/conformance/fixtures" ]; then
        echo "$APCORE_SPEC_REPO/conformance/fixtures"
        return
    fi

    # 3. Sibling directory
    local sibling="$REPO_ROOT/../apcore/conformance/fixtures"
    if [ -d "$sibling" ]; then
        echo "$sibling"
        return
    fi

    echo ""
}

SOURCE="$(find_source "${1:-}")"

if [ -z "$SOURCE" ]; then
    echo "Error: Cannot find apcore spec repo." >&2
    echo "" >&2
    echo "Fix one of:" >&2
    echo "  1. Pass the path:  $0 /path/to/apcore" >&2
    echo "  2. Set \$APCORE_SPEC_REPO" >&2
    echo "  3. Clone apcore as a sibling of this repo" >&2
    exit 1
fi

SOURCE="$(cd "$SOURCE" && pwd)"

# --- Copy fixtures ---
mkdir -p "$DEST"
cp "$SOURCE"/*.json "$DEST/"

echo "Synced fixtures from: $SOURCE"
echo "                  to: $DEST"
echo ""

# Show what changed (if inside a git repo)
if command -v git &>/dev/null && git -C "$REPO_ROOT" rev-parse --git-dir &>/dev/null; then
    DIFF="$(git -C "$REPO_ROOT" diff --stat -- tests/conformance/fixtures/)"
    if [ -n "$DIFF" ]; then
        echo "Changes:"
        echo "$DIFF"
    else
        echo "No changes (fixtures already up to date)."
    fi
fi
