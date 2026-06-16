#!/usr/bin/env bash
# check_mjs_syntax.sh — run node --check over all skills/*/workflow.mjs files.
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

while IFS= read -r -d '' mjs; do
    rel="${mjs#"$REPO/"}"
    if node --check "$mjs" 2>/dev/null; then
        echo "PASS  $rel"
    else
        echo "FAIL  $rel"
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

if [ "$failures" -gt 0 ]; then
    exit 1
fi
exit 0
