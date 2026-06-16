#!/usr/bin/env bash
# check_mjs_syntax.sh — validate every skills/*/workflow.mjs in the WORKFLOW-TOOL
# dialect: `export const meta = {...}` + a BARE body (top-level await/return,
# injected globals). Raw `node --check` is WRONG here because top-level `return`
# (the artifact) is illegal in a plain module, so we wrap the body in an async
# function before checking. Also rejects any stray `export` beyond meta (the
# `export function run()` wrapper that the Workflow tool refuses to launch).
# Prints PASS/FAIL per file; exits non-zero if any file fails.
# Requires: node (v18+). Exits 0 with a clear message if node is absent.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"

if ! command -v node &>/dev/null; then
    echo "SKIP: node not found on PATH — MJS syntax check requires Node.js"
    exit 0
fi

failures=0
checked=0
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

while IFS= read -r -d '' mjs; do
    rel="${mjs#"$REPO/"}"

    # Reject a second `export` (e.g. `export function run`) — bare body only.
    if [ "$(grep -c '^[[:space:]]*export ' "$mjs")" -gt 1 ]; then
        echo "FAIL  $rel  (stray 'export' beyond meta — must be a bare body, not a run() wrapper)"
        failures=$((failures + 1)); checked=$((checked + 1)); continue
    fi

    # Wrap the body in an async function so top-level return is valid, then check.
    # Exactly one `export const meta` per file (guaranteed by the stray-export
    # check above), so a global substitution is safe and BSD/GNU-sed portable.
    probe="$tmp/probe.mjs"
    {
        echo "async function __wf(){"
        sed 's/export const meta/const meta/' "$mjs"
        echo "}"
    } > "$probe"

    if node --check "$probe" 2>/dev/null; then
        echo "PASS  $rel"
    else
        echo "FAIL  $rel  (body not valid JS in the Workflow async context)"
        failures=$((failures + 1))
    fi
    checked=$((checked + 1))
done < <(find "$REPO/skills" -name "workflow.mjs" -print0 | sort -z)

if [ "$checked" -eq 0 ]; then
    echo "WARN: no workflow.mjs files found under $REPO/skills"
    exit 0
fi

echo ""
echo "Checked $checked file(s); $failures failure(s)."
[ "$failures" -gt 0 ] && exit 1
exit 0
